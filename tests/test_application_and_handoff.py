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

    def test_a_stated_mode_beats_the_keyword_sweep(self):
        """A URL is not evidence of an online route.

        An offline procedure that links to the form you must print contains
        "http", so the sweep called it "both" and the page told someone they
        could apply from home when the same document said to go to the office.
        The scheme states its mode in a heading; that heading is the answer.
        """
        text = ("**Offline**\n\n**Step 1:** Visit the office of the "
                "[authority](https://fisheries.py.gov.in/sub-offices).")
        assert application.detect_mode(text) == "offline"

    def test_both_modes_stated_is_both(self):
        text = "**Online**\n\n**Step 1:** Register.\n\n**Offline**\n\n**Step 1:** Visit."
        assert application.detect_mode(text) == "both"


class TestStepsSurviveTranslation:
    """The translated records arrive in a different shape to the English ones.

    myScheme's machine translation puts every step on one line and mangles the
    bold markers, so a Hindi "how to apply" was rendering as a single numbered
    item containing the whole procedure and a scattering of literal asterisks.
    """

    ENGLISH = (
        "**Offline**\n\n"
        "**Step 1:** Visit the office of the concerned authority.\n"
        "**Step 1:** Request the hard copy of the prescribed format.\n"
        "**Step 2:** Fill in all the mandatory fields.\n"
        "**Step 3:** Submit the form with the documents.\n"
    )
    #: The same record as Hindi: one line, `**` broken into `* * `, and some
    #: labels with no markers left at all.
    HINDI = (
        "**Offline**\n\n"
        "* * चरण 1: * * इच्छुक आवेदक को कार्यालय में जाना चाहिए। "
        "* * चरण 1: * * हार्ड कॉपी का अनुरोध करना चाहिए। "
        "चरण 2: सभी अनिवार्य क्षेत्रों को भरें। "
        "चरण 3: दस्तावेजों के साथ जमा करें।"
    )

    def test_english_splits_into_one_item_per_step(self):
        assert len(application.parse_list(self.ENGLISH)) == 4

    def test_hindi_splits_the_same_way(self):
        """The label is the only boundary here — there are no newlines."""
        assert len(application.parse_list(self.HINDI)) == 4

    def test_the_two_languages_agree(self):
        assert len(application.parse_list(self.ENGLISH)) == \
            len(application.parse_list(self.HINDI))

    def test_no_asterisks_reach_the_reader(self):
        """`* * चरण 1: * *` was printed verbatim, mid-sentence."""
        for item in application.parse_list(self.HINDI):
            assert "*" not in item, item

    def test_the_step_label_is_not_printed(self):
        """The renderer numbers the list. Printing the label too gives
        "1. Step 1: …", and where the source repeats a number — this corpus has
        schemes with two "Step 1"s — a list that contradicts its own numbering.
        """
        items = application.parse_list(self.ENGLISH)
        assert not any(i.startswith("Step ") for i in items), items
        assert items[0] == "Visit the office of the concerned authority."

    def test_the_mode_heading_is_not_a_step(self):
        """It is a property of the procedure, and `detect_mode` already has it."""
        assert "Offline" not in application.parse_list(self.ENGLISH)

    def test_two_mode_headings_are_kept_as_separators(self):
        """One heading is this document's mode. Two are the boundary between
        two different procedures, and dropping those would merge them."""
        text = ("**Online**\n\n**Step 1:** Register on the portal.\n\n"
                "**Offline**\n\n**Step 1:** Visit the office.\n")
        items = application.parse_list(text)
        assert "Online" in items and "Offline" in items

    def test_a_scheme_with_only_a_mode_yields_no_steps(self):
        """185 schemes publish nothing but "**Online**". Reporting one step
        called "Online" was a count of one where the truth is none — the pack
        says so with its own note instead."""
        assert application.parse_list("**Online**") == []
        assert application.detect_mode("**Online**") == "online"

    def test_a_link_split_by_translation_still_resolves(self):
        """Translation leaves `[text] (url)` with a space, which is no longer a
        link — so the brackets reached the page around the only words in the
        sentence a person might want to click."""
        item = application.parse_list(
            "**Step 1:** Visit the [authority] (https://x.gov.in) office.")[0]
        assert "[" not in item and "]" not in item
        assert "https://x.gov.in" in item

    @pytest.mark.parametrize("raw,expected", [
        # `_MANGLED_BOLD` turns the translated `* * * *` into `****`, which the
        # paired-bold pass does not match because it is not a pair.
        ("**** The interested applicant should visit the office.",
         "The interested applicant should visit the office."),
        # A blockquote survives both the bullet and the bold pass untouched.
        ("> Note: carry the original documents.",
         "Note: carry the original documents."),
        # And the one that hid: `&gt;` is not a `>` until html.unescape has
        # run, so stripping markers before it left 2,058 English steps still
        # starting with a blockquote that did not exist yet when the strip ran.
        ("&gt; Repayment of Loan: the first instalment falls due in month four.",
         "Repayment of Loan: the first instalment falls due in month four."),
        ("__Submit the form at the counter.__",
         "Submit the form at the counter."),
    ])
    def test_no_markdown_marker_reaches_the_reader(self, raw, expected):
        """They arrive as punctuation in the middle of an instruction somebody
        is trying to follow."""
        assert application.parse_list(raw) == [expected]

    def test_a_number_in_prose_is_not_mistaken_for_a_step(self):
        """The label pattern is deliberately narrow: a word, a small number, a
        colon. Prose that merely contains a figure must not be chopped up."""
        text = "Carry a photocopy of ration card 12345 and two photographs."
        assert application.parse_list(text) == [text]


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
