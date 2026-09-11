"""
Naming the paper someone is holding, and saying what is still missing.

A person turned away from a government office for the wrong document often does
not come back. The corpus already publishes what each scheme wants — a list of
sentences like "Caste certificate issued by the competent authority" — and the
application pack already renders it. What it could not do was answer the question
people actually ask, which is *"is this one of them?"*, held up to a camera.

WHAT THIS IS ALLOWED TO DECIDE: NOTHING

The classification ticks a checkbox. It never touches eligibility, it is never
required, and every answer it gives can be overridden by tapping the same box.
That is what makes it safe to run a model here at all: the failure mode of
getting it wrong is a wrong tick on a checklist the person is reading anyway,
not a wrong answer about whether they qualify. `Document.held` is a tri-state for
this reason — True, False, and "nobody has said", which must never render as
"missing".

THE PROMISE THAT CHANGES

`aadhaar-scan.tsx` says, truthfully, that the photograph never leaves the phone:
a QR code is decoded in the browser and only the decoded string is uploaded. A
photograph of a ration card cannot work that way — there is nothing to decode —
so this path sends the image. It is held in memory, classified, and dropped; it
is never written to disk and never logged. The copy has to say so plainly rather
than inheriting a promise that is no longer being kept.

WHEN THERE IS NO MODEL

The product still works. `is_available()` is false, the endpoint says so, and the
checklist stays a checklist people tick by hand — which is how it has to behave
on a cold free-tier instance anyway.
"""

from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from typing import Optional

from src.config import get_settings

logger = logging.getLogger(__name__)

#: Bigger than a phone photo needs to be. A 12-megapixel JPEG is ~4 MB; the cap
#: is there to stop a mis-sent video, not to be generous.
MAX_IMAGE_BYTES = 6 * 1024 * 1024

ALLOWED_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic"}

#: The documents Indian welfare schemes ask for, over and over. Kept as a closed
#: list so the model picks from known labels instead of inventing a name that
#: matches nothing on the checklist — the same reason facet values are never
#: typed from memory.
KNOWN_DOCUMENTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Aadhaar card", ("aadhaar", "aadhar", "uid", "आधार")),
    ("PAN card", ("pan card", "permanent account number")),
    ("Ration card", ("ration", "राशन", "bpl card", "apl card")),
    ("Voter ID (EPIC)", ("voter", "epic", "election commission", "मतदाता")),
    ("Caste certificate", ("caste", "scheduled caste", "scheduled tribe", "obc",
                           "जाति", "community certificate")),
    ("Income certificate", ("income certificate", "आय प्रमाण")),
    ("Domicile or residence certificate", ("domicile", "residence certificate",
                                           "निवास")),
    ("Bank passbook", ("passbook", "bank account", "ifsc", "बैंक")),
    ("Birth certificate", ("birth certificate", "जन्म")),
    ("Disability certificate", ("disability", "divyang", "udid", "दिव्यांग")),
    ("Land record (khatauni / 7-12 / pahani)", ("khatauni", "khasra", "7/12",
                                                "pahani", "jamabandi", "patta",
                                                "land record", "खतौनी")),
    ("Marksheet or school certificate", ("marksheet", "mark sheet", "transfer "
                                         "certificate", "school", "board exam")),
    ("Death certificate", ("death certificate", "मृत्यु")),
    ("Photograph", ("passport size", "photograph")),
    ("Driving licence", ("driving licence", "driving license")),
    ("Labour or worker card", ("labour card", "labor card", "e-shram", "eshram",
                               "worker card", "श्रम")),
)

_LABELS = tuple(label for label, _ in KNOWN_DOCUMENTS)


@dataclass
class Identification:
    """What we think the photograph is."""
    label: Optional[str] = None
    confident: bool = False
    #: True when we could not tell. The UI must say "we couldn't read that"
    #: rather than showing a wrong guess quietly.
    unclear: bool = True
    note: str = ""


def is_available() -> bool:
    """Whether a vision model is configured. False degrades, never breaks."""
    return bool(getattr(get_settings(), "gemini_api_key", "")) is True


def match_to_requirement(label: str, requirements: list[str]) -> Optional[int]:
    """Which line of a scheme's document list this photograph satisfies.

    The corpus writes requirements as prose — "A copy of the Ration card or
    voter identity card or any proof of residence" — so this is a keyword hit
    against the known document's own aliases, not string equality. Returns the
    index, or None when the photograph is a real document the scheme did not ask
    for, which is worth saying out loud rather than silently dropping.
    """
    aliases = next((a for lbl, a in KNOWN_DOCUMENTS if lbl == label), ())
    needles = (label.lower(), *aliases)
    for index, requirement in enumerate(requirements):
        haystack = requirement.lower()
        if any(needle in haystack for needle in needles):
            return index
    return None


_PROMPT = (
    "You are looking at a photograph of an Indian identity or government "
    "document. Reply with EXACTLY ONE of these labels and nothing else:\n"
    + "\n".join(f"- {label}" for label in _LABELS)
    + "\n- UNKNOWN\n\n"
    "Reply UNKNOWN if the image is blurred, cropped, not a document, or you are "
    "not sure. Guessing wrongly is worse than saying UNKNOWN. Do not describe "
    "the image. Do not read out any number printed on it."
)


#: A compliant reply is a label. Beyond this many words it is a sentence, and a
#: sentence is the model declining to follow the contract — at which point a
#: keyword hit inside it means nothing. "I think this might be a photograph of a
#: cat" contains "photograph", which is a real label, and is not a document.
_MAX_REPLY_WORDS = 6


def _normalise(reply: str) -> Optional[str]:
    """Map the model's reply onto a known label, or None.

    Closed-vocabulary on purpose: a label we never offered cannot match anything
    on a checklist, so an invented one is worse than no answer. This is the same
    reason facet values are never typed from memory.
    """
    text = (reply or "").strip().strip(".-• ")
    if not text or text.upper().startswith("UNKNOWN"):
        return None
    lowered = text.lower()

    for label in _LABELS:
        if label.lower() == lowered:
            return label

    # Only a short, label-shaped reply earns the fuzzy pass — "Aadhaar" for
    # "Aadhaar card". Prose does not.
    if len(lowered.split()) > _MAX_REPLY_WORDS:
        return None
    for label, aliases in KNOWN_DOCUMENTS:
        if label.lower() in lowered or any(a in lowered for a in aliases):
            return label
    return None


async def identify(image: bytes, content_type: str) -> Identification:
    """Name the document in a photograph. Never raises; degrades instead.

    The image is passed to the model and dropped. It is not written to disk, it
    is not logged, and no number printed on it is ever requested or stored — the
    prompt says so and the return type cannot carry one.
    """
    if not image:
        return Identification(note="empty", unclear=True)
    if not is_available():
        return Identification(
            unclear=True,
            note="No document reader is configured, so the checklist has to be "
                 "ticked by hand.")

    try:
        from langchain_core.messages import HumanMessage
        from langchain_google_genai import ChatGoogleGenerativeAI

        settings = get_settings()
        model = ChatGoogleGenerativeAI(
            model=settings.gemini_model_extraction,
            google_api_key=settings.gemini_api_key,
            temperature=0,
        )
        encoded = base64.b64encode(image).decode("ascii")
        mime = content_type if content_type in ALLOWED_TYPES else "image/jpeg"
        reply = await model.ainvoke([HumanMessage(content=[
            {"type": "text", "text": _PROMPT},
            {"type": "image_url", "image_url": f"data:{mime};base64,{encoded}"},
        ])])
        label = _normalise(getattr(reply, "content", "") or "")
    except Exception:
        # A model outage must not break a checklist someone can tick themselves.
        logger.warning("Document identification failed", exc_info=True)
        return Identification(
            unclear=True,
            note="That could not be read just now. Tick the box yourself if you "
                 "have it.")

    if label is None:
        return Identification(
            unclear=True,
            note="That was not clear enough to name. Try again in better light, "
                 "or tick the box yourself.")
    return Identification(label=label, confident=True, unclear=False)
