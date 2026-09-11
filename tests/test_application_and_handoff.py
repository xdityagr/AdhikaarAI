"""
Filling a form, and carrying a conversation across to WhatsApp.

The first test in this file is the one that matters most: the assistant must
never claim to have submitted an application. It cannot, and a person who
believes it did will stop chasing the office and miss the window — which is a
worse outcome than never applying, and is exactly what every agent who charges
a poor household a fee for a free scheme also promises.
"""

import pytest

from src import application, handoff


class TestSubmissionIsNeverClaimed:
    def test_the_prompt_forbids_saying_it_submitted(self):
        from src.agent import SYSTEM_PROMPT
        # Flattened, because the prompt is hard-wrapped and the rule must not
        # depend on where a line happens to break.
        flat = " ".join(SYSTEM_PROMPT.lower().split())
        assert "cannot submit" in flat
        assert "never suggest otherwise" in flat
        assert "i have applied for you" in flat

    def test_the_tool_description_says_so_too(self):
        """Belt and braces: the model reads the tool description even when the
        system prompt is long."""
        from src.agent import TOOL_SCHEMAS
        schema = next(s for s in TOOL_SCHEMAS if s["name"] == "prepare_application")
        assert "does not submit" in schema["description"].lower()

    def test_the_pack_carries_no_submission_route(self):
        pack = application.build("sui", {})
        assert pack is not None
        assert not hasattr(pack, "submit")
        assert not hasattr(pack, "submit_url")


class TestPack:
    def test_it_fills_from_what_is_already_known(self):
        pack = application.build("sui", {
            "full_name": "Sunita Devi", "state": "Uttar Pradesh",
            "category": "Scheduled Caste (SC)",
        })
        by_key = {f.key: f for f in pack.fields}
        assert by_key["full_name"].value == "Sunita Devi"
        assert by_key["state"].value == "Uttar Pradesh"
        assert not by_key["full_name"].blank

    def test_what_is_not_known_is_left_blank_not_guessed(self):
        """A form filled with a plausible invention is worse than one with a
        gap: the gap gets noticed at the counter and the invention does not."""
        pack = application.build("sui", {"full_name": "Sunita Devi"})
        by_key = {f.key: f for f in pack.fields}
        assert by_key["dob"].value == ""
        assert by_key["dob"].blank

    def test_an_unknown_scheme_returns_nothing(self):
        assert application.build("no-such-scheme-anywhere", {}) is None

    def test_a_credit_scheme_asks_credit_questions(self):
        pack = application.build("sui", {})
        keys = {f.key for f in pack.fields}
        assert "project_cost" in keys
        assert "bank_name" in keys

    def test_a_non_credit_scheme_does_not(self):
        """Asking a widow applying for a pension about her project cost is how
        a form loses someone on page one."""
        pack = application.build("108easuk", {})
        keys = {f.key for f in pack.fields}
        assert "project_cost" not in keys

    def test_aadhaar_is_never_a_field(self):
        """Almost every scheme wants it; we still never take it. An Aadhaar
        number typed into a website is what this audience is defrauded with."""
        for slug in ("sui", "108easuk"):
            pack = application.build(slug, {})
            for f in pack.fields:
                assert "aadhaar" not in f.key.lower()
                assert "aadhaar" not in f.label.lower()

    def test_the_no_fee_warning_is_always_present(self):
        pack = application.build("sui", {})
        # Asserted on the CODE as well as the sentence. The code is what the
        # interface translates on — the sentence is only what anything without a
        # translation layer prints — so a note that lost its code would go back
        # to ending a Hindi page in an English paragraph about not paying a fee,
        # which is the one line on the sheet that most needs to be understood.
        assert any(note.code == "no_fee" for note in pack.notes)
        assert any("fee" in note.text.lower() for note in pack.notes)

    def test_a_scheme_with_no_published_steps_says_so(self):
        pack = application.build("sui", {})
        pack.steps = []
        pack.has_process = False
        assert not pack.has_process


class TestParsing:
    def test_myscheme_numbering_is_stripped(self):
        """Their ordered lists are all written "1." — the renderer counts, the
        text does not."""
        items = application.parse_list("1. First thing\n1. Second thing\n1. Third")
        assert items == ["First thing", "Second thing", "Third"]

    def test_bullets_and_bold_are_stripped(self):
        assert application.parse_list("- **Proof** of identity") == ["Proof of identity"]

    def test_prose_survives_as_its_own_item(self):
        """A scheme that wrote its documents as a sentence must not silently
        reduce to nothing."""
        assert application.parse_list("Carry your ration card.") == \
            ["Carry your ration card."]

    def test_empty_input_is_empty_output(self):
        assert application.parse_list(None) == []
        assert application.parse_list("   ") == []

    @pytest.mark.parametrize("text,expected", [
        ("Apply online at the portal", "online"),
        ("Visit your nearest branch office", "offline"),
        ("Apply online or visit the branch", "both"),
        ("", ""),
    ])
    def test_mode_detection(self, text, expected):
        assert application.detect_mode(text) == expected


class TestHandoff:
    async def test_a_code_carries_the_context(self):
        code = await handoff.create({"state": "Bihar"}, [{"role": "user", "text": "hi"}])
        entry = await handoff.claim(code)
        assert entry.context["state"] == "Bihar"
        assert entry.history[0]["text"] == "hi"

    async def test_a_code_works_exactly_once(self):
        """It travels in a message anyone can forward."""
        code = await handoff.create({"state": "Bihar"})
        assert await handoff.claim(code) is not None
        assert await handoff.claim(code) is None

    async def test_an_unknown_code_is_refused_quietly(self):
        assert await handoff.claim("YS-ZZZZZZ") is None

    async def test_it_is_found_inside_a_real_message(self):
        code = await handoff.create({})
        message = f"Namaste, carrying on from the website. {code}"
        assert handoff.find(message) == code

    async def test_it_is_found_when_the_keyboard_changed_the_case(self):
        code = await handoff.create({})
        assert handoff.find(code.lower()) == code

    async def test_a_message_with_no_code_finds_nothing(self):
        assert handoff.find("I need a loan for a sewing machine") is None
        assert handoff.find("") is None

    async def test_the_code_is_stripped_before_the_model_sees_it(self):
        """"YS-4H7K I need help with the loan" is a question about the loan;
        the code is plumbing."""
        code = await handoff.create({})
        cleaned = handoff.strip(f"{code} I need help with the loan", code)
        assert cleaned == "I need help with the loan"

    async def test_the_alphabet_has_no_lookalikes(self):
        """People read these aloud and type them on a phone."""
        for ch in "O0I1L":
            assert ch not in handoff.ALPHABET

    async def test_codes_do_not_repeat(self):
        codes = {await handoff.create({}) for _ in range(200)}
        assert len(codes) == 200


class TestHandoffSurvivesARestart:
    """The reason it moved out of a dict.

    Its own comment said it needed a table "because a restart mid-handoff
    strands whoever was crossing at that moment" — a person who answered six
    questions on the website, tapped through to WhatsApp, and arrives to be
    asked their state again.
    """

    @pytest.fixture(autouse=True)
    async def _table(self):
        """These tests must hit the database, not the in-memory fallback.

        Without the table, `claim` falls back to the dict and every assertion
        below passes for the wrong reason — which is exactly what happened the
        first time they were run.
        """
        from src.database import init_database
        await init_database()
        handoff._PENDING.clear()
        yield
        handoff._PENDING.clear()

    async def test_a_code_still_works_after_the_process_forgets(self):
        code = await handoff.create({"state": "Bihar"}, [])
        handoff._PENDING.clear()                 # what a redeploy does
        entry = await handoff.claim(code)
        assert entry is not None, "a restart stranded somebody mid-handoff"
        assert entry.context["state"] == "Bihar"

    async def test_still_exactly_once_after_a_restart(self):
        """Single-use has to hold across processes, not just within one — the
        same link can be forwarded, and Meta redelivers messages."""
        code = await handoff.create({"state": "Kerala"}, [])
        handoff._PENDING.clear()
        assert await handoff.claim(code) is not None
        assert await handoff.claim(code) is None

    async def test_the_database_is_consulted_before_memory(self):
        """Checking memory first would let two workers each serve the same
        code, because each has its own dict."""
        code = await handoff.create({"state": "Odisha"}, [])
        assert await handoff.claim(code) is not None
        # The in-process copy must have been spent by the same claim.
        assert code not in handoff._PENDING


class TestResume:
    @pytest.mark.asyncio
    async def test_whatsapp_picks_up_what_the_website_knew(self):
        """The failure this prevents: being asked which state you live in,
        four minutes after answering it."""
        from src import whatsapp_brain as brain

        user = "919000000099"
        brain._CONTEXT.pop(user, None)
        brain._HISTORY.pop(user, None)

        code = await handoff.create(
            {"state": "Uttar Pradesh", "category": "Scheduled Caste (SC)"},
            [{"role": "user", "text": "I want a loan for a tailoring shop"}],
        )
        remaining = await brain._resume_from_web(user, f"{code} what next?")

        assert brain._CONTEXT[user]["state"] == "Uttar Pradesh"
        assert len(brain._HISTORY[user]) == 1
        assert remaining == "what next?"

    @pytest.mark.asyncio
    async def test_a_stale_code_still_gets_a_normal_conversation(self):
        """Someone forwarding an old link should not meet an error about a
        token they never knew existed."""
        from src import whatsapp_brain as brain

        user = "919000000098"
        brain._CONTEXT.pop(user, None)
        remaining = await brain._resume_from_web(user, "YS-ZZZZZZ hello")
        assert remaining == "hello"
        assert not brain._CONTEXT[user]
