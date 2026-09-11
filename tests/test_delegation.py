"""
A citizen hands their case over, and can take it back.

This is what makes storing a profile defensible. `profile.ts` promises a
person's answers live on their own phone and go no further; the operator panel
needs them on a server so somebody at a counter can fill a form. The only
honest bridge is that the citizen hands it over themselves and can end it
whenever they like — so these tests are mostly about the ending.

Four properties, and each has a way of being quietly wrong:

  1. no operator can create a case      — there is no route, and that is checked
  2. one case, one operator             — two counters filing one application is
                                          a rejected application
  3. revocation needs nothing but the code, and is immediate
  4. closing ends the consent, not just the task
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src import auth, delegation
from src.database import (
    create_operator, create_organisation, get_connection, init_database,
)
from src.main import app
from src.operator_api import SESSION_COOKIE

PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(autouse=True)
async def _db():
    await init_database()
    yield


async def _make_operator(role: str = "operator") -> dict:
    org, oid = uuid.uuid4().hex, uuid.uuid4().hex
    email = f"{uuid.uuid4().hex[:8]}@example.org"
    db = await get_connection()
    try:
        await create_organisation(db, org, "Counter", "CSC")
        await create_operator(db, oid, org, email, "Worker",
                              auth.hash_password(PASSWORD), role)
    finally:
        await db.close()
    return {"operator_id": oid, "organisation_id": org, "email": email}


@pytest.fixture
def client():
    return TestClient(app)


def _sign_in(client: TestClient, operator: dict) -> None:
    response = client.post("/api/operator/login",
                           json={"email": operator["email"],
                                 "password": PASSWORD})
    assert response.status_code == 200, response.text


CONTEXT = {"state": "Bihar", "caste": "sc", "family_income": "120000"}


class TestOnlyTheCitizenCreatesACase:
    def test_there_is_no_operator_route_that_creates_one(self):
        """The absence IS the design. An operator who could mint a case could
        put anybody's household in the panel without their knowing."""
        paths = {r.path for r in app.routes}
        creators = {p for p in paths
                    if "operator" in p and p.endswith("/cases")}
        # /api/operator/cases exists only as a GET list; the POST that creates
        # one lives on the citizen's router and takes no session.
        for path in creators:
            route = next(r for r in app.routes if r.path == path)
            assert "POST" not in route.methods, (
                f"{path} accepts POST — an operator must not be able to create "
                f"a case on somebody's behalf"
            )

    def test_the_citizen_route_needs_no_account(self, client):
        """They have none and will not be given one."""
        response = client.post("/api/cases/offer",
                               json={"context": CONTEXT, "language": "hi"})
        assert response.status_code == 200, response.text
        assert response.json()["code"].startswith(delegation.PREFIX + "-")


class TestClaiming:
    async def test_an_operator_can_take_an_offered_case(self, client):
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]

        response = client.post("/api/operator/cases/claim", json={"code": code})
        assert response.status_code == 200, response.text
        assert response.json()["context"] == CONTEXT

    async def test_claiming_requires_a_session(self, client):
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        assert client.post("/api/operator/cases/claim",
                           json={"code": code}).status_code == 401

    async def test_a_second_operator_is_refused(self, client):
        """Two people filing the same application is a rejected application."""
        first, second = await _make_operator(), await _make_operator()
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]

        _sign_in(client, first)
        assert client.post("/api/operator/cases/claim",
                           json={"code": code}).status_code == 200

        _sign_in(client, second)
        response = client.post("/api/operator/cases/claim", json={"code": code})
        assert response.status_code == 409
        assert "already helping" in response.json()["detail"]

    async def test_the_holder_may_present_it_again(self, client):
        """Not an error — an operator coming back to a case they hold."""
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        assert client.post("/api/operator/cases/claim",
                           json={"code": code}).status_code == 200
        assert client.post("/api/operator/cases/claim",
                           json={"code": code}).status_code == 200

    async def test_each_refusal_says_which_one_it_was(self, client):
        """An operator with a person in front of them needs to know whether to
        retype it, ask for a new one, or stop."""
        operator = await _make_operator()
        _sign_in(client, operator)
        response = client.post("/api/operator/cases/claim",
                               json={"code": "YC-ZZZZZZ"})
        assert response.status_code == 404
        assert "Check the letters" in response.json()["detail"]

    async def test_a_handoff_code_is_not_a_case_code(self, client):
        """The two share an alphabet and nothing else. A citizen who pastes a
        YS- code at a counter gets a clear refusal."""
        operator = await _make_operator()
        _sign_in(client, operator)
        response = client.post("/api/operator/cases/claim",
                               json={"code": "YS-ABC234"})
        assert response.status_code == 404


class TestRevoking:
    async def test_the_code_alone_is_enough(self, client):
        """The person revoking may be on a borrowed phone, or may be a daughter
        helping her mother. Holding the code is the same evidence that granting
        it was."""
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        assert client.post("/api/cases/revoke",
                           json={"code": code}).status_code == 200

    async def test_a_revoked_case_cannot_be_claimed(self, client):
        operator = await _make_operator()
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        client.post("/api/cases/revoke", json={"code": code})

        _sign_in(client, operator)
        response = client.post("/api/operator/cases/claim", json={"code": code})
        assert response.status_code == 404
        assert "withdrawn" in response.json()["detail"]

    async def test_revoking_a_claimed_case_takes_it_away(self, client):
        """Immediately, and from an operator who is holding it open."""
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        case_id = client.post("/api/operator/cases/claim",
                              json={"code": code}).json()["case_id"]
        assert client.get(f"/api/operator/cases/{case_id}").status_code == 200

        client.post("/api/cases/revoke", json={"code": code})

        assert client.get(f"/api/operator/cases/{case_id}").status_code == 410

    async def test_it_leaves_the_caseload(self, client):
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        client.post("/api/operator/cases/claim", json={"code": code})
        assert len(client.get("/api/operator/cases").json()) == 1

        client.post("/api/cases/revoke", json={"code": code})
        assert client.get("/api/operator/cases").json() == []

    async def test_revoking_an_unknown_code_says_the_same_thing(self, client):
        """A revocation route that reports "no such case" enumerates cases for
        anybody who types codes at it."""
        real = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        a = client.post("/api/cases/revoke", json={"code": real})
        b = client.post("/api/cases/revoke", json={"code": "YC-ZZZZZZ"})
        assert a.status_code == b.status_code == 200
        assert a.json() == b.json()


class TestReadingACase:
    async def test_only_the_holder_may_read_it(self, client):
        """Consent was given to a person at a counter, not to their employer."""
        holder, other = await _make_operator(), await _make_operator()
        _sign_in(client, holder)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        case_id = client.post("/api/operator/cases/claim",
                              json={"code": code}).json()["case_id"]

        _sign_in(client, other)
        response = client.get(f"/api/operator/cases/{case_id}")
        assert response.status_code == 404, (
            "a 403 would confirm the case exists to anybody who guesses an id")

    async def test_a_colleague_in_the_same_organisation_may_not_either(self, client):
        holder = await _make_operator()
        db = await get_connection()
        try:
            colleague_id = uuid.uuid4().hex
            email = f"{uuid.uuid4().hex[:8]}@example.org"
            await create_operator(db, colleague_id, holder["organisation_id"],
                                  email, "Colleague",
                                  auth.hash_password(PASSWORD), "operator")
        finally:
            await db.close()

        _sign_in(client, holder)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        case_id = client.post("/api/operator/cases/claim",
                              json={"code": code}).json()["case_id"]

        _sign_in(client, {"email": email})
        assert client.get(f"/api/operator/cases/{case_id}").status_code == 404

    async def test_the_list_does_not_carry_the_answers(self, client):
        """A screenful of households on a shared counter monitor is not a list,
        it is a leak."""
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        client.post("/api/operator/cases/claim", json={"code": code})

        listed = client.get("/api/operator/cases").json()
        assert listed and listed[0]["context"] is None

    async def test_the_language_travels_with_the_case(self, client):
        """An operator who speaks to them in the wrong language has undone most
        of the point of this product."""
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT, "language": "ta"}).json()["code"]
        claimed = client.post("/api/operator/cases/claim", json={"code": code})
        assert claimed.json()["language"] == "ta"


class TestClosing:
    async def test_closing_ends_the_access(self, client):
        """An operator who finished the job three months ago should not still
        be able to read a household's income."""
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        case_id = client.post("/api/operator/cases/claim",
                              json={"code": code}).json()["case_id"]

        assert client.post(f"/api/operator/cases/{case_id}/close").status_code == 200
        assert client.get("/api/operator/cases").json() == []

    async def test_a_closed_case_cannot_be_reclaimed(self, client):
        operator = await _make_operator()
        _sign_in(client, operator)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        case_id = client.post("/api/operator/cases/claim",
                              json={"code": code}).json()["case_id"]
        client.post(f"/api/operator/cases/{case_id}/close")

        response = client.post("/api/operator/cases/claim", json={"code": code})
        assert response.status_code == 409
        assert "already been filed" in response.json()["detail"]

    async def test_somebody_else_cannot_close_your_case(self, client):
        holder, other = await _make_operator(), await _make_operator()
        _sign_in(client, holder)
        code = client.post("/api/cases/offer",
                           json={"context": CONTEXT}).json()["code"]
        case_id = client.post("/api/operator/cases/claim",
                              json={"code": code}).json()["case_id"]

        _sign_in(client, other)
        assert client.post(
            f"/api/operator/cases/{case_id}/close").status_code == 404


class TestCodes:
    def test_the_alphabet_is_readable_aloud(self):
        """Shared with handoff.py precisely because this one is read across a
        desk: no O/0, no I/1/L."""
        for confusable in "O0I1L":
            assert confusable not in delegation.ALPHABET

    @pytest.mark.parametrize("typed,expected", [
        ("yc-abc234", "YC-ABC234"),
        ("  YC-ABC234  ", "YC-ABC234"),
        ("my code is YC-ABC234 thanks", "YC-ABC234"),
        ("ABC234", "YC-ABC234"),          # just the six characters
    ])
    def test_it_reads_what_people_actually_type(self, typed, expected):
        assert delegation.normalise(typed) == expected

    @pytest.mark.parametrize("typed", ["", "YC-", "YC-ABC", "YC-ABC23O",
                                       "hello", None])
    def test_and_refuses_what_is_not_a_code(self, typed):
        assert delegation.normalise(typed) is None

    def test_codes_do_not_repeat(self):
        assert len({delegation.new_code() for _ in range(500)}) == 500
