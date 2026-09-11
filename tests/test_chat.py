"""
Conversational engine tests.

The chat is the whole product now, so the things that must never break are:
one question at a time, always with tappable options, never a dead end, and the
language following the user without them having to ask.
"""

from __future__ import annotations

import pytest

from src.chat import PLACES, parse_amount, turn
from src.i18n import LANGUAGES, detect_language, t


# ---------------------------------------------------------------------------
# Amount parsing — people do not type "120000"
# ---------------------------------------------------------------------------

class TestAmountParsing:
    def test_plain_number(self):
        assert parse_amount("120000") == 120_000

    def test_with_separators_and_symbol(self):
        assert parse_amount("₹1,20,000") == 120_000

    @pytest.mark.parametrize("text,expected", [
        ("1.4 lakh", 140_000), ("1.4 lac", 140_000), ("50L", 5_000_000),
        ("2 crore", 20_000_000), ("80 thousand", 80_000), ("50k", 50_000),
    ])
    def test_scaled_words(self, text, expected):
        assert parse_amount(text) == expected

    def test_multi_part_sums(self):
        """'my husband earns 2 lakh and I earn 80 thousand' -> 2.8 lakh."""
        assert parse_amount("2 lakh and 80 thousand") == 280_000

    def test_unreadable_returns_none(self):
        assert parse_amount("no idea") is None
        assert parse_amount("") is None


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

class TestLanguage:
    @pytest.mark.parametrize("text,lang", [
        ("मुझे सिलाई की दुकान खोलनी है", "hi"),
        ("আমি একটি দোকান খুলতে চাই", "bn"),
        ("எனக்கு ஒரு கடை வேண்டும்", "ta"),
    ])
    def test_script_detection(self, text, lang):
        assert detect_language(text) == lang

    def test_ascii_is_not_guessed(self):
        assert detect_language("I want a tailoring shop") is None

    def test_scripted_languages_are_complete(self):
        """The guided conversation is written in five languages, and each of
        those must be whole — a half-translated script is worse than none."""
        from src.i18n import STRINGS
        scripted = [c for c, meta in LANGUAGES.items() if meta.get("scripted")]
        assert len(scripted) == 5
        for key, entry in STRINGS.items():
            for code in scripted:
                assert entry.get(code), f"{key} missing {code}"

    def test_no_language_ever_yields_a_blank(self):
        """The other eight fall back to English rather than to emptiness.

        This is the honest state of things: the interface speaks thirteen
        languages, the scripted flow five, and the model-backed assistant
        answers in whichever the person writes in. What must never happen is a
        blank line where a question should be."""
        from src.i18n import STRINGS, t
        for key in STRINGS:
            for code in LANGUAGES:
                assert t(key, code).strip(), f"{key} blank in {code}"

    def test_every_offered_language_matches_a_myscheme_translation(self):
        """We only offer languages the government itself publishes scheme text
        in. Translating our buttons into a language whose schemes we could only
        show in English would be a hollow kind of support."""
        official = {"en", "hi", "ta", "bn", "mr", "te", "gu", "kn", "ml",
                    "pa", "or", "as", "ur"}
        assert set(LANGUAGES) <= official

    def test_unknown_key_falls_back_to_itself(self):
        assert t("no_such_key", "hi") == "no_such_key"


# ---------------------------------------------------------------------------
# The conversation
# ---------------------------------------------------------------------------

class TestConversation:
    @pytest.mark.asyncio
    async def test_opens_with_a_greeting_and_options(self):
        r = await turn(None)
        assert len(r["messages"]) == 2          # greeting, then one question
        assert len(r["chips"]) >= 6             # never a bare text prompt
        assert r["done"] is False

    @pytest.mark.asyncio
    async def test_opening_does_not_assume_the_person_wants_money(self):
        """The failure this replaced: it opened with "what do you need the money
        for?" and offered a business or a course.

        Most of the corpus is not money — a pension, a house, a scholarship, a
        widow's allowance. Being asked about project cost is how someone who
        needs a roof concludes this product is not for them and leaves."""
        r = await turn(None)
        greeting = r["messages"][0]["text"].lower()
        question = r["messages"][1]["text"].lower()
        assert "money" not in question
        values = {c["value"] for c in r["chips"]}
        assert {"housing", "pension", "health", "study"} <= values
        # The greeting should name more than credit.
        assert any(word in greeting for word in ("pension", "scholarship", "housing"))

    @pytest.mark.asyncio
    async def test_welfare_need_never_asks_about_project_cost(self):
        """Someone wanting a pension is never asked what their project costs."""
        r = await turn(None)
        sid = r["session_id"]
        asked = []
        for message in ["pension", "SC", "ballia"]:
            r = await turn(sid, message)
            asked.append(r["step"])
        assert "cost" not in asked and "income" not in asked
        assert r["done"] is True
        assert any(c["kind"] == "matches" for c in r["cards"])

    @pytest.mark.asyncio
    async def test_credit_need_still_reaches_the_loan_engine(self):
        r = await turn(None)
        sid = r["session_id"]
        for message in ["business", "120000", "280000", "SC", "female", "ballia"]:
            r = await turn(sid, message)
        assert r["done"] is True
        assert [c["kind"] for c in r["cards"]].count("scheme") == 3

    @pytest.mark.asyncio
    async def test_hindi_is_detected_from_the_first_message(self):
        """Nobody should have to pick a language before they can ask."""
        r = await turn(None, "मुझे सिलाई की दुकान खोलनी है")
        assert r["language"] == "hi"
        assert r["step"] == "cost"

    @pytest.mark.asyncio
    async def test_every_step_offers_chips(self):
        r = await turn(None)
        sid = r["session_id"]
        for message in ["business", "120000", "280000", "SC", "female"]:
            r = await turn(sid, message)
            if not r["done"]:
                assert r["chips"], f"step {r['step']} left the user with no options"

    @pytest.mark.asyncio
    async def test_unparseable_answer_re_asks_with_options(self):
        """Never a dead end."""
        r = await turn(None)
        sid = r["session_id"]
        r = await turn(sid, "asdfghjkl")
        assert r["step"] == "need"              # did not advance
        assert r["chips"]                       # options still offered
        assert len(r["messages"]) == 2          # apology, then the question again

    @pytest.mark.asyncio
    async def test_full_run_produces_cards(self):
        r = await turn(None)
        sid = r["session_id"]
        for message in ["business", "120000", "280000", "SC", "female", "ballia"]:
            r = await turn(sid, message)
        assert r["done"] is True
        kinds = [c["kind"] for c in r["cards"]]
        assert kinds.count("scheme") == 3
        assert "compare" in kinds
        assert "partners" in kinds
        assert "notice" in kinds

    @pytest.mark.asyncio
    async def test_cheapest_scheme_is_first_and_badged(self):
        r = await turn(None)
        sid = r["session_id"]
        for m in ["business", "120000", "280000", "SC", "female", "ballia"]:
            r = await turn(sid, m)
        schemes = [c for c in r["cards"] if c["kind"] == "scheme"]
        assert schemes[0]["best"] is True
        assert schemes[0]["name"] == "Micro Finance Scheme"
        assert all(s["best"] is False for s in schemes[1:])

    @pytest.mark.asyncio
    async def test_out_of_category_gets_a_referral_not_a_wall(self):
        r = await turn(None)
        sid = r["session_id"]
        for m in ["business", "120000", "280000", "OBC", "male", "ballia"]:
            r = await turn(sid, m)
        assert r["done"] is True
        notices = [c for c in r["cards"] if c["kind"] == "notice"]
        assert any("NBCFDC" in c["body"] for c in notices)

    @pytest.mark.asyncio
    async def test_restart_clears_the_answers(self):
        r = await turn(None)
        sid = r["session_id"]
        await turn(sid, "business")
        r = await turn(sid, "", restart=True)
        assert r["step"] == "need"

    @pytest.mark.asyncio
    async def test_free_text_purpose_is_understood(self):
        """'I want to open a tailoring shop' should not need a chip tap."""
        r = await turn(None)
        sid = r["session_id"]
        r = await turn(sid, "I want to open a small tailoring shop")
        assert r["step"] == "cost"

    @pytest.mark.asyncio
    async def test_places_are_all_routable(self):
        for place in PLACES:
            r = await turn(None)
            sid = r["session_id"]
            for m in ["business", "120000", "280000", "SC", "female", place["id"]]:
                r = await turn(sid, m)
            assert r["done"] is True, f"{place['id']} did not complete"


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

class TestWhatsAppRendering:
    """WhatsApp has no cards, so everything is one text message — and its markup
    is not Markdown. Getting that wrong shows literal asterisks to someone who
    may already be reading with difficulty."""

    def test_bold_becomes_single_asterisks(self):
        from src.whatsapp_brain import to_whatsapp_markup
        assert to_whatsapp_markup("**Micro Finance Scheme**") == "*Micro Finance Scheme*"

    def test_markdown_furniture_is_stripped(self):
        from src.whatsapp_brain import to_whatsapp_markup
        out = to_whatsapp_markup("## Heading\n- one\n- two\n[myScheme](https://x.in)")
        assert "#" not in out
        assert out.count("•") == 2
        assert "https://x.in" in out and "[" not in out

    def test_messages_are_clipped_to_one_whatsapp_message(self):
        from src.whatsapp_brain import _clip, MAX_MESSAGE_CHARS
        long = "\n".join(f"line {i} of a very long reply" for i in range(200))
        clipped = _clip(long)
        assert len(clipped) <= MAX_MESSAGE_CHARS + 1
        assert clipped.endswith("…")

    def test_cards_render_without_their_labels(self):
        from src.whatsapp_brain import render_cards
        text = render_cards([
            {"kind": "eligibility", "name": "Widow Pension", "verdict": "NOT_MATCHED",
             "unmet": ["caste"], "unknown": []},
            {"kind": "scheme", "best": True, "name": "Micro Finance Scheme",
             "rate": 6.5, "loan": "₹1,08,000", "instalment": "₹10,801",
             "instalment_count": 11, "interest": "₹12,568"},
        ])
        assert "❌ *Widow Pension*" in text
        assert "caste" in text
        assert "₹10,801 × 11" in text
        assert "cheapest" in text

    def test_language_defaults_to_english_until_a_script_appears(self):
        from src.whatsapp_brain import remember_language, _CONTEXT
        phone = "whatsapp:+910000000000"
        _CONTEXT.pop(phone, None)
        assert remember_language(phone, "hello") == "en"
        assert remember_language(phone, "मुझे पेंशन चाहिए") == "hi"
        # And it stays switched, even when the next message is just a digit.
        assert remember_language(phone, "2") == "hi"

    def test_a_bare_number_picks_the_option_it_stood_for(self):
        from src.whatsapp_brain import remember_options, resolve_numbered_choice
        phone = "whatsapp:+910000000001"
        remember_options(phone, [{"value": "business"}, {"value": "pension"}])
        assert resolve_numbered_choice(phone, "2") == "pension"
        # An amount is not a menu choice.
        assert resolve_numbered_choice(phone, "2 lakh") == "2 lakh"
        assert resolve_numbered_choice(phone, "9") == "9"
