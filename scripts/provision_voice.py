"""
Point a Vapi number at this service — repeatably, and in a reviewable diff.

Configuring a voice agent is a dozen fields across four dashboard screens, and
the ones that matter most are the ones easiest to get silently wrong: the
language enforcement, the tool URLs, and the secret every tool is signed with.
Done by clicking, none of that is reviewable and nobody can tell afterwards what
the assistant was actually configured to do. So it is a script.

Idempotent: it finds the assistant by name and updates it rather than making a
second one, so running it twice is the same as running it once.

    python scripts/provision_voice.py --dry-run          # show, send nothing
    python scripts/provision_voice.py --language hi
    python scripts/provision_voice.py --language ta --attach-number

WHAT IT DELIBERATELY DOES NOT DO

- **No recording.** `artifactPlan.recordingEnabled` is set to False explicitly
  rather than left to Vapi's default, because "we never turned it on" and "we
  turned it off" are different claims and only one of them survives someone
  changing the default. See `src.voice.RECORDING_POLICY`.
- **No outbound.** Nothing here dials anybody. The number is published and
  people ring it.
- **`prepare_application` is not registered as a tool at all.** Eleven fields
  read down a phone line is worse than every alternative, and leaving it out of
  the assistant means the model cannot reach for it even if it wants to.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agent import TOOL_SCHEMAS                                   # noqa: E402
from src.config import get_settings                                  # noqa: E402
from src.i18n import LANGUAGES                                       # noqa: E402
from src.voice import ALLOWED, NATIVE, RECORDING_POLICY              # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
logger = logging.getLogger("provision-voice")

API = "https://api.vapi.ai"
ASSISTANT_NAME = "Yojna Setu — inbound"

# Deepgram via Vapi reaches these; Sarvam behind `custom-voice` reaches the rest.
# See docs/SPIKE-voice-vapi.md — this is the binding constraint on the channel,
# not a detail. Naming it here means `--language ml` fails loudly at the command
# line rather than quietly producing an assistant that answers in English.
VAPI_DEEPGRAM_STT = {"en", "hi", "bn", "mr", "ta", "te", "kn", "ur"}
VAPI_ELEVENLABS_TTS = {"en", "hi", "ta"}


# ---------------------------------------------------------------------------
# What the assistant is told
#
# Short, because a long prompt is a slow first token, and every constraint here
# is one the deterministic side already enforces — the prompt is a second belt,
# never the only one. A model that ignores all of it still cannot make the
# matcher return a scheme the person does not qualify for.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Yojna Setu, answering the phone to somebody asking what government help
they are entitled to.

SPEAK {language_name} unless the caller switches, then follow them.

WHO IS ON THE LINE

Often somebody who has been turned away from an office before, or who has been
told by a middleman that this costs money. They may be on a bad line, in a
noisy room, on a borrowed phone. Assume intelligence and assume no familiarity:
they know their own life exactly, and they have never used a service like this.

Be warm and brief. Short sentences, one idea each. Never more than one question
in a turn. This is a conversation, not a form being read out.

HOW TO TALK

- Acknowledge what they just said before you ask the next thing. "Got it" is
  enough. Somebody who answers three questions and hears nothing back assumes
  the line is dead.
- Never re-ask something they have already told you, in this call or a previous
  one. If you already know it, say so: "You told me you are in Bihar."
- If they go quiet, ask if they are still there before repeating yourself.
- If they ramble, let them finish. People explain their situation because it is
  the only part they are sure about.
- Never read out a long list. Three schemes at most, then ask if they want more.
- Do not say you are searching, looking, or checking. Just answer when you have
  it.

NUMBERS AND ANSWERS

- When you send an answer to answer_question, send DIGITS for anything numeric.
  If they say their age in words, in any language, convert it: "बीस" is 20,
  "chalees" is 40. Send 20, not the word.
- Amounts the same way: send the number, not "two lakh".
- If you genuinely could not hear them, ask again. Never guess an answer and
  never record one they did not give.

WHAT DECIDES ELIGIBILITY — AND IT IS NOT YOU

- Never say whether somebody qualifies from your own reading of anything. Call
  check_scheme_eligibility and report exactly what it returns, including the
  conditions it could not check. Telling a person they qualify when they do not
  sends them on a journey they cannot afford.
- Never invent a number. Every amount, rate and count comes from a tool.
- Run the interview with next_question and answer_question. Ask what it gives
  you, in their language, and send back what they said. If they would rather
  not answer, send "skip" — and tell them it costs them nothing, because it
  does not: an unanswered question can never rule a scheme out.
- If we do not hold something, say so plainly and offer the office that will.
  Use find_offices. "I do not know" is a better answer than a guess.
- When you read out a scheme's published FAQ and they are not speaking English,
  say you are translating it first.

WHAT YOU MUST NEVER DO

- Never ask for an Aadhaar number, a bank account number, a card number, a PIN,
  a password or an OTP. Never read one aloud. If they begin to say one, stop
  them kindly: we never need it, and any call that asks for it is not us. This
  is the fraud they are most likely to meet, and a real service that asks the
  same questions teaches them the scam is normal.
- Never offer to fill the form during the call. Say you will send it to their
  WhatsApp on this number.
- Never promise money, approval, or a date.
- Never ask them to pay anybody. Applying is free.

Calls are not recorded, and you can tell them so if they ask.
"""


def _tool(name: str, base: str, secret: str) -> dict:
    """One tool, described to the model exactly as the web describes it.

    The descriptions come from `agent.TOOL_SCHEMAS` rather than being written
    again here. They are how a model decides which question it is being asked,
    and two copies would drift — at which point the phone and the website would
    start reaching for different tools on the same sentence.
    """
    schema = next((s for s in TOOL_SCHEMAS if s["name"] == name), None)
    if schema is None:
        schema = _NATIVE_SCHEMAS[name]

    return {
        "type": "function",
        "function": {
            "name": schema["name"],
            "description": schema["description"],
            "parameters": schema["parameters"],
        },
        "server": {
            "url": f"{base}/api/voice/tools/{name}",
            # The same string `src.voice.verify_request` checks. Without it every
            # call to us is a 403 and the assistant simply goes quiet, which the
            # dashboard reports as "assistant did not respond" and which is
            # otherwise a genuinely hard afternoon.
            "secret": secret,
            # 20 is the provider's maximum and it is here for the cold start,
            # not the query. The tools answer in milliseconds once the
            # container is awake; the free plan spins down after 15 minutes
            # idle and takes about 50 seconds to come back, and the first tool
            # call of the first call after a quiet spell pays that. Ten seconds
            # guaranteed it failed.
            "timeoutSeconds": 20,
        },
    }


#: The two that have no web equivalent, so no schema in `agent.py` to borrow.
_NATIVE_SCHEMAS = {
    "next_question": {
        "name": "next_question",
        "description": (
            "Ask for the single most useful next question to put to this caller. "
            "Call it at the start of the conversation and after every answer. It "
            "chooses from what the remaining schemes actually restrict on, so the "
            "second question depends on the first. Ask the caller what it returns, "
            "in their language. When it says finished, stop asking and call "
            "find_schemes."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    "resume_from_web": {
        "name": "resume_from_web",
        "description": (
            "Carry over a session the caller started on the website. If they "
            "mention they were just on the site, or already answered questions "
            "there, ask whether they have a code beginning YS and send exactly "
            "what they say. Everything they told the website is then known and "
            "must not be asked again. If it asks you to retry, you misheard the "
            "code — ask for it one character at a time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string",
                         "description": "What the caller said, verbatim"},
            },
            "required": ["code"],
        },
    },
    "answer_faq": {
        "name": "answer_faq",
        "description": (
            "Read the scheme's OWN published answer to a question about it — how "
            "long it takes, whether you can apply online, what the loan covers. "
            "Use it for anything about how a scheme works, after another tool has "
            "given you the slug. It quotes the government's published text and "
            "returns nothing when the question is not covered; when that happens, "
            "say we do not know and offer find_offices. Never answer from your own "
            "knowledge instead. If it sets say_it_is_a_translation, tell the "
            "caller you are translating the published answer before you read it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string",
                         "description": "The scheme's slug from another tool"},
                "question": {"type": "string",
                             "description": "What the caller asked, in English"},
            },
            "required": ["slug", "question"],
        },
    },
    "answer_question": {
        "name": "answer_question",
        "description": (
            "Record what the caller said to the question you just asked. Send "
            "their answer in their own words; it will be interpreted. Send "
            "'skip' if they would rather not say. If it comes back asking to "
            "retry, you misheard — ask the same question again rather than "
            "moving on."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string",
                                "description": "The id next_question returned"},
                "answer": {"type": "string",
                           "description": "What the caller said, verbatim"},
            },
            "required": ["question_id", "answer"],
        },
    },
}


def build(language: str, base: str, secret: str) -> dict:
    """The whole assistant, as one payload worth reading before it is sent."""
    name = LANGUAGES.get(language, {}).get("name", language)

    return {
        "name": ASSISTANT_NAME,
        "firstMessage": _GREETING.get(language, _GREETING["en"]),
        "firstMessageMode": "assistant-speaks-first",

        # Transcription. `nova-3` is the only Deepgram model Vapi exposes with
        # Tamil; Hindi is on more, but pinning one model keeps the two languages
        # behaving the same way.
        "transcriber": {
            "provider": "deepgram",
            "model": "nova-3",
            "language": language,
        },

        # Speech. Flash v2.5 because it is the only ElevenLabs model where Vapi
        # says language ENFORCEMENT works — without it a sentence containing an
        # English scheme name drags the whole utterance back to English
        # phonology, which is the normal sentence here, not the edge case.
        "voice": {
            "provider": "11labs",
            "model": "eleven_flash_v2_5",
            "voiceId": "sarah",
            "language": language,
        },

        "model": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.3,
            "messages": [{
                "role": "system",
                "content": SYSTEM_PROMPT.format(language_name=name),
            }],
            "tools": [_tool(tool, base, secret) for tool in _TOOL_ORDER],
        },

        # Not recorded. Stated, not defaulted — see the module docstring.
        "artifactPlan": {"recordingEnabled": RECORDING_POLICY != "none"},

        # Everything that is not a tool call: status updates, end of call.
        "server": {"url": f"{base}/api/voice/events", "secret": secret},

        # A phone call that has gone quiet for this long has gone wrong. Better
        # to end it than to bill someone's international minutes for silence.
        "silenceTimeoutSeconds": 30,
        "maxDurationSeconds": 900,
    }


#: Tier 1 first — the interview leads, because it is the piece that makes a call
#: better than the website rather than a worse copy of it.
_TOOL_ORDER = [
    "resume_from_web", "next_question", "answer_question",
    "find_schemes", "check_scheme_eligibility", "find_offices", "answer_faq",
    "lookup_scheme", "search_schemes", "price_loan", "corpus_stats",
]

_GREETING = {
    "en": "Hello, this is Yojna Setu. I can tell you which government schemes "
          "you are entitled to. May I ask you a few short questions?",
    "hi": "नमस्ते, मैं योजना सेतु हूँ। मैं आपको बता सकती हूँ कि आप किन सरकारी "
          "योजनाओं के हक़दार हैं। क्या मैं आपसे कुछ छोटे सवाल पूछ सकती हूँ?",
    "ta": "வணக்கம், இது யோஜ்னா சேது. நீங்கள் எந்த அரசுத் திட்டங்களுக்குத் "
          "தகுதியானவர் என்று நான் சொல்ல முடியும். சில சிறிய கேள்விகள் கேட்கலாமா?",
}


def _existing(client: httpx.Client) -> dict | None:
    response = client.get("/assistant")
    response.raise_for_status()
    for item in response.json():
        if item.get("name") == ASSISTANT_NAME:
            return item
    return None


def run(language: str, base: str, attach: bool, dry_run: bool) -> int:
    settings = get_settings()

    if not settings.vapi_api_key:
        logger.error("VAPI_API_KEY is not set")
        return 1
    if not settings.vapi_webhook_secret:
        logger.error("VAPI_WEBHOOK_SECRET is not set — every tool call would 403")
        return 1

    if language not in VAPI_DEEPGRAM_STT:
        logger.error(
            "Vapi's Deepgram transcriber does not list %s. Covered: %s. "
            "The rest need the Sarvam custom transcriber — see "
            "docs/SPIKE-voice-vapi.md.",
            language, ", ".join(sorted(VAPI_DEEPGRAM_STT)))
        return 1
    if language not in VAPI_ELEVENLABS_TTS:
        logger.error(
            "ElevenLabs Flash v2.5 does not speak %s. Covered: %s. "
            "The rest need the Sarvam custom-voice bridge — see "
            "docs/SPIKE-voice-vapi.md.",
            language, ", ".join(sorted(VAPI_ELEVENLABS_TTS)))
        return 1

    if base.startswith("http://") or "localhost" in base:
        logger.error("%s is not reachable from Vapi. Deploy first, or tunnel.", base)
        return 1

    payload = build(language, base.rstrip("/"), settings.vapi_webhook_secret)

    if dry_run:
        # The secret is the one thing that must not be printed — this output is
        # the kind of thing that ends up pasted into a pull request.
        shown = json.loads(json.dumps(payload).replace(
            settings.vapi_webhook_secret, "<VAPI_WEBHOOK_SECRET>"))
        print(json.dumps(shown, indent=2, ensure_ascii=False))
        logger.info("Dry run — nothing sent. %d tools, recording=%s",
                    len(payload["model"]["tools"]), RECORDING_POLICY)
        return 0

    headers = {"Authorization": f"Bearer {settings.vapi_api_key}"}
    with httpx.Client(base_url=API, headers=headers, timeout=30) as client:
        current = _existing(client)

        # Anything chosen in the dashboard STAYS chosen.
        #
        # This script builds a whole assistant, so a re-run to fix a prompt or
        # a tool used to silently revert the transcriber, the model and the
        # voice to whatever is written here — undoing an afternoon of somebody
        # tuning latency and picking a voice that sounds like a person. Those
        # three are the operator's call, not this file's; the tools, the prompt
        # and the recording policy are this file's, because they are what the
        # code has to agree with.
        if current:
            for owned_by_the_dashboard in ("transcriber", "model", "voice"):
                live = current.get(owned_by_the_dashboard)
                if not live:
                    continue
                if owned_by_the_dashboard == "model":
                    # Except its tools and prompt, which must track the code.
                    live = {**live,
                            "tools": payload["model"]["tools"],
                            "messages": payload["model"]["messages"]}
                    logger.info("Keeping dashboard model %s/%s",
                                live.get("provider"), live.get("model"))
                else:
                    logger.info("Keeping dashboard %s: %s",
                                owned_by_the_dashboard,
                                live.get("voiceId") or live.get("model") or
                                live.get("provider"))
                payload[owned_by_the_dashboard] = live
        if current:
            response = client.patch(f"/assistant/{current['id']}", json=payload)
            action = "updated"
        else:
            response = client.post("/assistant", json=payload)
            action = "created"

        if response.status_code >= 300:
            logger.error("Assistant %s failed (%s): %s", action,
                         response.status_code, response.text[:600])
            return 1

        assistant_id = response.json().get("id")
        logger.info("Assistant %s: %s (%s, %d tools)", action, assistant_id,
                    language, len(payload["model"]["tools"]))

        if attach:
            if not settings.vapi_phone_number_id:
                logger.error("VAPI_PHONE_NUMBER_ID is not set — nothing to attach to")
                return 1
            attached = client.patch(
                f"/phone-number/{settings.vapi_phone_number_id}",
                json={"assistantId": assistant_id},
            )
            if attached.status_code >= 300:
                logger.error("Could not attach the number (%s): %s",
                             attached.status_code, attached.text[:400])
                return 1
            number = attached.json().get("number", "")
            logger.info("Number %s now answers with this assistant", number)
            if number.startswith("+1"):
                logger.warning(
                    "%s is a US number. A caller in India pays international "
                    "rates to reach it, and many prepaid plans bar ISD outright "
                    "— so this is a demo path, not the published helpline. See "
                    "docs/SPIKE-voice-vapi.md.", number)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="hi",
                        help="Call language: hi, ta, en … (default: hi)")
    parser.add_argument("--base", default="",
                        help="Public base URL of this service "
                             "(default: WEBHOOK_BASE_URL)")
    parser.add_argument("--attach-number", action="store_true",
                        help="Point VAPI_PHONE_NUMBER_ID at this assistant")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the payload and send nothing")
    args = parser.parse_args()

    base = args.base or get_settings().webhook_base_url
    return run(args.language, base, args.attach_number, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
