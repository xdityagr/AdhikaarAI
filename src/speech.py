"""
Turning speech into text, so people can talk instead of type.

This matters more here than it looks. Typing Devanagari, Tamil or Odia on a
phone keyboard is slow enough that people give up and type romanised English,
or give up entirely — and the person this product is for may not read
comfortably in any script. Speaking is the natural input, and it is the same
input on WhatsApp (a voice note) and on the website (hold to talk).

TWO ENGINES, AND THE MEASUREMENTS THAT PUT THEM IN THIS ORDER

Both were run over the same synthesised Hindi, Tamil and Bengali sentences and
scored against the known text:

                            Hindi    Tamil    Bengali
    Sarvam saarika:v2.5     98.8%    100%     100%
    Deepgram, named lang    89.9%    100%      98.6%
    Deepgram, `multi`       81.5%      0%       0%

The zeroes are the important part, and they are not noise. Deepgram's
multilingual model heard the Tamil correctly and then wrote it out in
DEVANAGARI — "नान तमिलनाकल व सिक्कुम विधवई" — and did the same to Bengali. The
words are roughly right and the script is wrong, so the text is useless to the
reader and to our own language detection.

That mattered because `multi` was what we fell back to whenever the language
was not already known, which on WhatsApp is every first voice note. A Tamil
speaker's opening message could never have worked.

So: Sarvam first, because it is more accurate AND it detects the language
itself rather than being told. Deepgram second, and only ever with a named
language — never `multi` when we have a better option.

They also cover different gaps, which is why both stay:

    Sarvam only    : Malayalam, Odia   (Deepgram has neither)
    Deepgram only  : Assamese, Urdu    (Sarvam has neither)

Between them all thirteen app languages are covered. Neither alone manages it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)

SARVAM_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_MODEL = "saarika:v2.5"

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEEPGRAM_MODEL = "nova-3"

# Our language code -> Sarvam's. Confirmed against the API, one call per code.
# Odia is the trap: Sarvam spells it `od-IN`, not the ISO `or-IN` used
# everywhere else in this codebase, and the wrong one is a 400.
SARVAM_CODES = {
    "en": "en-IN", "hi": "hi-IN", "bn": "bn-IN", "mr": "mr-IN",
    "ta": "ta-IN", "te": "te-IN", "gu": "gu-IN", "kn": "kn-IN",
    "ml": "ml-IN", "pa": "pa-IN", "or": "od-IN",
}

# Sarvam has no Assamese or Urdu; these two are the reason Deepgram stays.
DEEPGRAM_LANGUAGES = {
    "en", "hi", "bn", "mr", "te", "ta", "gu", "kn", "pa", "as", "ur",
}

# Every language the pair can handle. Nothing outside this set is transcribed
# by naming it — it goes to Sarvam's own detection instead.
SUPPORTED_LANGUAGES = set(SARVAM_CODES) | DEEPGRAM_LANGUAGES

# Sarvam's "work it out yourself", and the reason a first voice note now works.
AUTODETECT = "unknown"

# Deepgram's equivalent, kept only as the last resort when Sarvam is down and
# we have no idea what language this is. It mangles the script for every Indian
# language except Hindi, so a result from it is marked unclear on purpose.
DEEPGRAM_MULTILINGUAL = "multi"

# Voice notes are short. A minute of audio that takes longer than this to come
# back is a failure, not a slow success.
TIMEOUT = httpx.Timeout(45.0, connect=10.0)

# Below this, we would rather ask someone to repeat themselves than act on a
# guess — acting on a misheard income figure is worse than asking again.
MIN_CONFIDENCE = 0.45


@dataclass
class Transcript:
    text: str = ""
    confidence: float = 0.0
    """The language actually spoken, in OUR codes. When we did not know it
    going in, this is what the engine detected — and it is worth keeping: a
    Tamil voice note is how we learn to answer in Tamil."""
    language: str = ""
    """Which engine produced this, for the logs when a transcript looks wrong."""
    provider: str = ""
    """False when the audio could not be transcribed at all."""
    ok: bool = False
    """True when we heard something but not clearly enough to act on."""
    unclear: bool = False


def is_available() -> bool:
    settings = get_settings()
    return bool(settings.sarvam_api_key or settings.deepgram_api_key)


def language_is_supported(language: Optional[str]) -> bool:
    return bool(language) and language in SUPPORTED_LANGUAGES


def _our_code(sarvam_code: str) -> str:
    """Sarvam's `hi-IN` back to our `hi` — and `od-IN` back to `or`."""
    for ours, theirs in SARVAM_CODES.items():
        if theirs == sarvam_code:
            return ours
    return (sarvam_code or "").split("-")[0]


async def transcribe(
    audio: bytes,
    content_type: str = "audio/ogg",
    language: Optional[str] = None,
) -> Transcript:
    """Audio in, words out, with whichever engine can do this language best.

    `language` is what the interface already believes, and it is a hint, not an
    instruction: pass None and Sarvam will work it out, which is what happens
    on someone's first voice note. When it IS known, naming it still helps —
    a Tamil speaker saying a half-English scheme name is better served by
    "this is Tamil" than by detection.
    """
    settings = get_settings()
    attempts = _plan(language, settings)

    if not attempts:
        logger.error("No speech provider configured — cannot transcribe")
        return Transcript()

    for engine, code in attempts:
        result = await engine(audio, content_type, code)
        if result.ok:
            return result

    return Transcript()


def _plan(language: Optional[str], settings) -> list[tuple]:
    """Which engines to try, in order, for this language.

    Written out rather than inlined because the ordering is the whole design
    and it is easy to break silently: put Deepgram's `multi` anywhere but last
    and Tamil starts coming back in Devanagari again.
    """
    sarvam_ready = bool(settings.sarvam_api_key)
    deepgram_ready = bool(settings.deepgram_api_key)
    attempts: list[tuple] = []

    # 1. Sarvam, when it knows this language — or when nobody does yet, since
    #    detecting it is strictly better than assuming English.
    if sarvam_ready and (language is None or language in SARVAM_CODES):
        attempts.append((_sarvam, SARVAM_CODES.get(language or "", AUTODETECT)))

    # 2. Deepgram with the language NAMED. This is Assamese and Urdu's only
    #    route, and a good fallback everywhere else.
    if deepgram_ready and language in DEEPGRAM_LANGUAGES:
        attempts.append((_deepgram, language))

    # 3. Sarvam's detection, for a language Deepgram named but Sarvam might
    #    still hear better — and for when step 2 simply failed.
    if sarvam_ready and language not in (None, "") and language not in SARVAM_CODES:
        attempts.append((_sarvam, AUTODETECT))

    # 4. Last resort only. See the module docstring for what this does to
    #    Tamil; it is here so that a Sarvam outage degrades instead of dying.
    if deepgram_ready and not attempts:
        attempts.append((_deepgram, DEEPGRAM_MULTILINGUAL))

    return attempts


def _bare_mime(content_type: str) -> str:
    """`audio/ogg; codecs=opus` -> `audio/ogg`.

    Sarvam allows `audio/ogg` and matches the string EXACTLY, so the codec
    parameter is a 400 — and WhatsApp always sends the parameter. Every voice
    note was rejected before it was ever listened to, and the person got "I
    could not make out that voice note", which blamed them for our own header.
    """
    return (content_type or "audio/ogg").split(";")[0].strip().lower()


async def _sarvam(audio: bytes, content_type: str, code: str) -> Transcript:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                SARVAM_URL,
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={"file": ("audio", audio, _bare_mime(content_type))},
                data={"model": SARVAM_MODEL, "language_code": code},
            )
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("Sarvam unreachable (%s): %s", code, exc)
        return Transcript()

    if response.status_code >= 400:
        logger.warning("Sarvam refused (%s): %s %s",
                       code, response.status_code, response.text[:200])
        return Transcript()

    payload = response.json()
    text = (payload.get("transcript") or "").strip()
    if not text:
        return Transcript(provider="sarvam")

    # Sarvam reports how sure it is of the LANGUAGE, not of the words. Treating
    # that as a transcript confidence would be a lie, so it is only used to
    # decide whether the detected language is worth believing.
    language_probability = float(payload.get("language_probability") or 0.0)
    detected = _our_code(payload.get("language_code") or "")

    return Transcript(
        text=text,
        confidence=language_probability,
        language=detected if language_probability >= MIN_CONFIDENCE else "",
        provider="sarvam",
        ok=True,
    )


async def _deepgram(audio: bytes, content_type: str, code: str) -> Transcript:
    settings = get_settings()
    params = {
        "model": DEEPGRAM_MODEL,
        "language": code,
        # Punctuation makes a transcript readable when it is echoed back; the
        # engine does not care either way.
        "punctuate": "true",
        "smart_format": "true",
    }
    payload = await _post_with_one_retry(audio, content_type, params, code)
    if payload is None:
        return Transcript()

    alternatives = (
        payload.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])
    )
    best = alternatives[0] if alternatives else {}
    text = (best.get("transcript") or "").strip()
    confidence = float(best.get("confidence") or 0.0)

    if not text:
        return Transcript(provider="deepgram")

    return Transcript(
        text=text,
        confidence=confidence,
        # `multi` cannot be trusted to have used the right script, so it is
        # never allowed to tell us what language someone speaks.
        language="" if code == DEEPGRAM_MULTILINGUAL else code,
        provider="deepgram",
        ok=True,
        unclear=confidence < MIN_CONFIDENCE or code == DEEPGRAM_MULTILINGUAL,
    )


async def _post_with_one_retry(
    audio: bytes,
    content_type: str,
    params: dict,
    chosen: str,
) -> Optional[dict]:
    """Send the audio, retrying once if the network was the problem.

    The distinction matters because of what the caller does with a failure: it
    tells the person their voice note could not be understood and asks them to
    record it again. A dropped connection would send that message about audio
    that was perfectly clear, and someone who has already struggled to be heard
    is exactly the person who stops trying at that point.

    So a 4xx — Deepgram looked at the request and refused it — is final and not
    retried. A timeout, a reset connection or a 5xx is retried once.
    """
    headers = {
        "Authorization": f"Token {get_settings().deepgram_api_key}",
        "Content-Type": content_type or "audio/ogg",
    }

    for attempt in (1, 2):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.post(
                    DEEPGRAM_URL, params=params, headers=headers, content=audio,
                )
            if response.status_code < 400:
                return response.json()

            if response.status_code < 500:
                # Deepgram read it and said no — sending it again changes nothing.
                logger.warning("Deepgram refused (%s, %s): %s %s",
                               chosen, content_type, response.status_code,
                               response.text[:200])
                return None

            reason = f"HTTP {response.status_code}"
        except Exception as exc:                              # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__

        if attempt == 1:
            logger.info("Deepgram attempt 1 failed (%s), retrying: %s",
                        chosen, reason)
        else:
            logger.warning("Deepgram failed twice (%s, %s): %s",
                           chosen, content_type, reason)

    return None
