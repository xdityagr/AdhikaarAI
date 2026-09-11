"""
Document identification tests.

The classifier itself needs a vision model and a network, so what is tested here
is everything around it — the reconciliation against a scheme's published list,
and the behaviour when there is no model at all, which is the state a cold
free-tier instance is in and the state this machine is in.

The governing rule: this feature is allowed to be wrong. It ticks a checkbox the
person can untick. So the tests assert that a failure degrades to a usable
checklist and never to an exception, an empty page, or a claim about eligibility.
"""

from __future__ import annotations

import pytest

from src import documents
from src.application import Document, parse_list


REQUIREMENTS = [
    "A copy of the Ration card or voter identity card or any proof of residence",
    "Caste certificate issued by the competent authority",
    "Bank passbook first page showing the IFSC",
    "Two passport size photographs",
]


class TestReconciliation:
    def test_it_finds_the_line_a_document_satisfies(self):
        assert documents.match_to_requirement("Ration card", REQUIREMENTS) == 0
        assert documents.match_to_requirement("Caste certificate", REQUIREMENTS) == 1
        assert documents.match_to_requirement("Bank passbook", REQUIREMENTS) == 2

    def test_it_matches_through_prose_not_equality(self):
        """The corpus writes requirements as sentences, so "Voter ID (EPIC)" has
        to reach "or voter identity card or any proof of residence"."""
        assert documents.match_to_requirement("Voter ID (EPIC)", REQUIREMENTS) == 0

    def test_a_document_the_scheme_did_not_ask_for_returns_none(self):
        """Worth saying out loud rather than dropping — it is how someone learns
        they are carrying something they do not need."""
        assert documents.match_to_requirement("PAN card", REQUIREMENTS) is None

    def test_no_requirements_matches_nothing(self):
        assert documents.match_to_requirement("Ration card", []) is None


class TestDegradingWithoutAModel:
    @pytest.mark.asyncio
    async def test_it_says_so_rather_than_failing(self, monkeypatch):
        monkeypatch.setattr(documents, "is_available", lambda: False)
        found = await documents.identify(b"\xff\xd8\xff", "image/jpeg")
        assert found.unclear is True
        assert found.label is None
        assert found.note                      # tells the person what to do

    @pytest.mark.asyncio
    async def test_an_empty_image_is_not_an_exception(self):
        found = await documents.identify(b"", "image/jpeg")
        assert found.unclear is True
        assert found.label is None

    @pytest.mark.asyncio
    async def test_a_model_failure_degrades_to_tick_it_yourself(self, monkeypatch):
        """A model outage must not take away a checklist that works by hand."""
        monkeypatch.setattr(documents, "is_available", lambda: True)

        def explode(*args, **kwargs):
            raise RuntimeError("no network")

        monkeypatch.setattr("langchain_google_genai.ChatGoogleGenerativeAI", explode)
        found = await documents.identify(b"\xff\xd8\xff", "image/jpeg")
        assert found.unclear is True
        assert "yourself" in found.note.lower()


class TestTheModelsReplyIsNeverTrustedRaw:
    @pytest.mark.parametrize("reply,expected", [
        ("Ration card", "Ration card"),
        ("ration card", "Ration card"),
        ("- Aadhaar card", "Aadhaar card"),
        ("Aadhaar", "Aadhaar card"),
        ("UNKNOWN", None),
        ("unknown, the image is blurred", None),
        ("", None),
        ("I think this might be a photograph of a cat", None),
    ])
    def test_replies_are_mapped_onto_known_labels(self, reply, expected):
        """A label we did not offer cannot match anything on a checklist, so the
        reply is mapped back onto the closed list or discarded."""
        assert documents._normalise(reply) == expected

    def test_every_known_label_normalises_to_itself(self):
        for label, _ in documents.KNOWN_DOCUMENTS:
            assert documents._normalise(label) == label


class TestTheReplyShape:
    """A multimodal turn returns `.content` as a LIST of content blocks, not a
    string. The first version assumed a string, threw `'list' object has no
    attribute 'strip'`, and the catch-all turned it into "that could not be read
    just now" — so the feature was completely broken and looked merely unlucky.
    Graceful degradation hid a total failure, which is the risk of a broad catch.
    """

    class _Reply:
        def __init__(self, content):
            self.content = content

    def test_a_plain_string_reply(self):
        assert documents._reply_text(self._Reply("Ration card")) == "Ration card"

    def test_a_list_of_content_blocks(self):
        reply = self._Reply([{"type": "text", "text": "Ration card"}])
        assert documents._reply_text(reply) == "Ration card"

    def test_a_list_of_bare_strings(self):
        assert documents._reply_text(self._Reply(["Ration card"])) == "Ration card"

    def test_an_empty_reply_is_a_string_not_a_crash(self):
        assert documents._reply_text(self._Reply([])) == ""
        assert documents._reply_text(self._Reply(None)) == ""

    def test_the_shapes_all_normalise_to_the_same_label(self):
        for content in ("Ration card", [{"type": "text", "text": "Ration card"}],
                        ["Ration card"]):
            text = documents._reply_text(self._Reply(content))
            assert documents._normalise(text) == "Ration card"


class TestHeldIsATriState:
    def test_nobody_asked_is_not_missing(self):
        """`None` must never render as "you do not have this". Someone who has
        not been through the checklist has not told us they are short."""
        doc = Document(text="Ration card")
        assert doc.held is None
        assert doc.held is not False

    def test_the_pack_carries_what_the_person_said(self):
        from src import application
        held = {"Caste certificate issued by the competent authority": True}
        docs = [Document(text=item, held=held.get(item)) for item in REQUIREMENTS]
        assert docs[1].held is True
        assert docs[0].held is None

    def test_prose_survives_as_one_requirement(self):
        """Already true of parse_list, asserted here because the checklist is
        now keyed on the exact requirement text — if the split changed, every
        stored tick would silently stop matching."""
        assert parse_list("Carry your ration card.") == ["Carry your ration card."]
