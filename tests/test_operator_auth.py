"""
The operator panel is not a public database of poor households.

This is the first authentication in the codebase and the only guarded surface in
the API, so what is tested here is not "does login work" — it is the two things
that make the panel defensible at all:

  1. every route under /api/operator requires a live session, enforced by a
     dependency rather than by a check somebody has to remember to write
  2. the login route says the same thing, and takes the same path, whether the
     password was wrong or the account does not exist

The first is asserted by walking the router, so a route added in a hurry without
the dependency fails the build rather than quietly serving somebody's caseload.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src import auth
from src.database import (
    create_operator, create_organisation, find_operator_by_email,
    get_connection, init_database,
)
from src.main import app
from src.operator_api import SESSION_COOKIE, current_operator, router

PASSWORD = "a-long-enough-passphrase"

#: The only routes reachable without a live session, and why each one is.
#:
#:   login   there is no session yet; that is the point of it
#:   logout  the session may already have expired, and somebody clicking
#:           "sign out" on a stale tab must get a clean result rather than a
#:           401 that leaves them looking signed in. It reads the cookie
#:           directly and deletes whatever it names, which is safe because
#:           deleting a session you hold the token for is exactly what signing
#:           out is.
#:
#: Anything else added to this set is a route serving somebody's welfare
#: application to an anonymous caller, so the list is meant to be hard to grow.
NO_SESSION_REQUIRED = {"/api/operator/login", "/api/operator/logout"}


@pytest.fixture(autouse=True)
async def _db():
    await init_database()
    yield


@pytest.fixture
async def operator():
    """An active operator in a real organisation."""
    org, oid = uuid.uuid4().hex, uuid.uuid4().hex
    email = f"{uuid.uuid4().hex[:8]}@example.org"
    db = await get_connection()
    try:
        await create_organisation(db, org, "Test CSC", "CSC", "Bihar", "Patna")
        await create_operator(db, oid, org, email, "A Worker",
                              auth.hash_password(PASSWORD), "operator")
    finally:
        await db.close()
    return {"operator_id": oid, "organisation_id": org, "email": email}


@pytest.fixture
def client():
    return TestClient(app)


class TestEveryRouteIsGuarded:
    """Walked from the router, not listed by hand.

    A hand-written list is a list somebody forgets to add to. This reads what
    is actually registered, so the test grows itself.
    """

    def test_the_router_has_routes(self):
        assert [r for r in router.routes], "no routes registered"

    @pytest.mark.parametrize(
        "path",
        sorted({r.path for r in router.routes if r.path not in NO_SESSION_REQUIRED}),
    )
    def test_it_depends_on_current_operator(self, path):
        route = next(r for r in router.routes if r.path == path)
        guarded = any(
            d.call is current_operator
            or getattr(d.call, "__name__", "") == "check"   # requires(...)
            for d in route.dependant.dependencies
        )
        assert guarded, (
            f"{path} does not require a session. Every route in this file is a "
            f"view of somebody's welfare application."
        )

    @pytest.mark.parametrize("method,path", [
        ("get", "/api/operator/me"),
        ("get", "/api/operator/health"),
        ("post", "/api/operator/accounts"),
        ("post", "/api/operator/organisations"),
        ("post", "/api/operator/password"),
    ])
    def test_unauthenticated_is_401(self, client, method, path):
        """The behaviour, as well as the wiring."""
        call = getattr(client, method)
        response = call(path, json={}) if method == "post" else call(path)
        assert response.status_code == 401, response.text

    def test_a_made_up_cookie_is_not_a_session(self, client):
        """`chat.get_session` accepts any id the client sends and creates it.
        That is harmless for an anonymous chat and would be a catastrophe
        here, so it is checked explicitly."""
        client.cookies.set(SESSION_COOKIE, "not-a-real-token")
        assert client.get("/api/operator/me").status_code == 401


class TestSigningIn:
    async def test_the_right_password_opens_a_session(self, client, operator):
        response = client.post("/api/operator/login",
                               json={"email": operator["email"],
                                     "password": PASSWORD})
        assert response.status_code == 200, response.text
        assert response.json()["operator_id"] == operator["operator_id"]
        assert SESSION_COOKIE in response.cookies

    async def test_the_cookie_then_works(self, client, operator):
        client.post("/api/operator/login",
                    json={"email": operator["email"], "password": PASSWORD})
        me = client.get("/api/operator/me")
        assert me.status_code == 200
        assert me.json()["email"] == operator["email"]

    async def test_the_wrong_password_does_not(self, client, operator):
        response = client.post("/api/operator/login",
                               json={"email": operator["email"],
                                     "password": "wrong-but-long-enough"})
        assert response.status_code == 401
        assert SESSION_COOKIE not in response.cookies

    async def test_an_unknown_address_says_exactly_the_same_thing(
            self, client, operator):
        """Saying which one was wrong turns the login form into a tool for
        finding out which NGO workers have accounts here."""
        wrong = client.post("/api/operator/login",
                            json={"email": operator["email"],
                                  "password": "wrong-but-long-enough"})
        unknown = client.post("/api/operator/login",
                              json={"email": "nobody@example.org",
                                    "password": "wrong-but-long-enough"})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"]

    async def test_the_email_is_not_case_sensitive(self, client, operator):
        response = client.post("/api/operator/login",
                               json={"email": operator["email"].upper(),
                                     "password": PASSWORD})
        assert response.status_code == 200

    async def test_the_cookie_is_httponly_and_samesite(self, client, operator):
        response = client.post("/api/operator/login",
                               json={"email": operator["email"],
                                     "password": PASSWORD})
        header = response.headers["set-cookie"].lower()
        assert "httponly" in header, "a script on the page could read it"
        assert "samesite=lax" in header, "it would ride on a cross-site POST"


class TestSigningOut:
    async def test_it_ends_the_session_on_the_server(self, client, operator):
        """Clearing the cookie alone leaves a working token in the database for
        anybody who copied it — which is the whole reason sessions are held
        server-side rather than signed into the cookie."""
        login = client.post("/api/operator/login",
                            json={"email": operator["email"],
                                  "password": PASSWORD})
        token = login.cookies[SESSION_COOKIE]

        client.post("/api/operator/logout")

        # Present the same token again, as a copy of it would.
        client.cookies.set(SESSION_COOKIE, token)
        assert client.get("/api/operator/me").status_code == 401


class TestLockout:
    async def test_enough_wrong_guesses_stops_the_account(self, client, operator):
        for _ in range(auth.MAX_FAILURES):
            client.post("/api/operator/login",
                        json={"email": operator["email"], "password": "nope-nope-nope"})
        response = client.post("/api/operator/login",
                               json={"email": operator["email"], "password": "nope-nope-nope"})
        assert response.status_code == 429

    async def test_even_the_right_password_waits(self, client, operator):
        """Otherwise the lockout is decorative: it would stop the guessing and
        let the guess through the moment it landed."""
        for _ in range(auth.MAX_FAILURES):
            client.post("/api/operator/login",
                        json={"email": operator["email"], "password": "nope-nope-nope"})
        response = client.post("/api/operator/login",
                               json={"email": operator["email"], "password": PASSWORD})
        assert response.status_code == 429

    async def test_getting_it_right_first_clears_the_count(self, client, operator):
        """Somebody who mistypes twice and then succeeds must not be two
        mistakes away from a lockout tomorrow."""
        for _ in range(3):
            client.post("/api/operator/login",
                        json={"email": operator["email"], "password": "nope-nope-nope"})
        client.post("/api/operator/login",
                    json={"email": operator["email"], "password": PASSWORD})

        db = await get_connection()
        try:
            row = await find_operator_by_email(db, operator["email"])
        finally:
            await db.close()
        assert row[7] == 0, "the failure counter was not reset"


class TestRoles:
    async def test_an_operator_cannot_create_accounts(self, client, operator):
        """There is no self-signup and no lateral promotion. An account is
        permission to read other people's welfare applications."""
        client.post("/api/operator/login",
                    json={"email": operator["email"], "password": PASSWORD})
        response = client.post("/api/operator/accounts", json={
            "email": "new@example.org", "name": "New", "password": PASSWORD})
        assert response.status_code == 403

    async def test_an_admin_can(self, client):
        org, oid = uuid.uuid4().hex, uuid.uuid4().hex
        email = f"{uuid.uuid4().hex[:8]}@example.org"
        db = await get_connection()
        try:
            await create_organisation(db, org, "HQ", "NGO")
            await create_operator(db, oid, org, email, "Boss",
                                  auth.hash_password(PASSWORD), "admin")
        finally:
            await db.close()

        client.post("/api/operator/login",
                    json={"email": email, "password": PASSWORD})
        response = client.post("/api/operator/accounts", json={
            "email": f"{uuid.uuid4().hex[:8]}@example.org",
            "name": "New Worker", "password": PASSWORD})
        assert response.status_code == 201, response.text
        # Created in the admin's own organisation unless another is named.
        assert response.json()["organisation_id"] == org

    async def test_a_short_password_is_refused(self, client):
        org, oid = uuid.uuid4().hex, uuid.uuid4().hex
        email = f"{uuid.uuid4().hex[:8]}@example.org"
        db = await get_connection()
        try:
            await create_organisation(db, org, "HQ", "NGO")
            await create_operator(db, oid, org, email, "Boss",
                                  auth.hash_password(PASSWORD), "admin")
        finally:
            await db.close()
        client.post("/api/operator/login",
                    json={"email": email, "password": PASSWORD})
        response = client.post("/api/operator/accounts", json={
            "email": "x@example.org", "name": "X", "password": "short"})
        assert response.status_code == 422


class TestPasswords:
    def test_the_same_password_hashes_differently_every_time(self):
        """A shared salt would make the hashes a rainbow table's problem."""
        assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)

    def test_a_hash_verifies(self):
        assert auth.verify_password(PASSWORD, auth.hash_password(PASSWORD))

    def test_a_wrong_password_does_not(self):
        assert not auth.verify_password("other", auth.hash_password(PASSWORD))

    def test_the_parameters_travel_with_the_hash(self):
        """So the cost can be raised later without a migration: an old hash
        still says how it was made."""
        stored = auth.hash_password(PASSWORD)
        assert stored.startswith(f"scrypt${auth._SCRYPT_N}$")

    @pytest.mark.parametrize("broken", ["", "not-a-hash", "scrypt$1$2",
                                        "bcrypt$a$b$c$d$e", None])
    def test_an_unreadable_hash_fails_closed(self, broken):
        """A truncated or hand-edited row must not turn a bad password into a
        500 — or, far worse, into a pass."""
        assert not auth.verify_password(PASSWORD, broken)


class TestSessionTokens:
    def test_the_database_never_holds_the_token(self):
        """A leaked operator_sessions table must not be a set of live logins."""
        token = auth.new_session_token()
        assert auth.token_fingerprint(token) != token
        assert token not in auth.token_fingerprint(token)

    def test_tokens_are_not_guessable(self):
        assert len({auth.new_session_token() for _ in range(200)}) == 200

    def test_an_expired_session_is_expired(self):
        assert auth.is_expired("2020-01-01T00:00:00+00:00")

    def test_a_live_session_is_not(self):
        assert not auth.is_expired(auth.session_expiry())

    @pytest.mark.parametrize("bad", [None, "", "not a date"])
    def test_an_unreadable_expiry_counts_as_expired(self, bad):
        """Fail closed: a row we cannot read the clock on is not a live login."""
        assert auth.is_expired(bad)
