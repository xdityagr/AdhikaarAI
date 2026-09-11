"""
The conversational engine behind the web chat.

Same ENGINE as WhatsApp — schemes, calculator, literacy, routing — but a
different presentation. WhatsApp can only send text, so it gets a formatted
block. A browser can render components, so this returns STRUCTURED CARDS and
keeps the spoken part short. Dumping the WhatsApp text blob into a web page is
what made the first version a wall of text.

Design rules:

1. ONE QUESTION PER TURN, always with tappable options. Typing is allowed but
   never required — the person this is built for may not type comfortably in any
   language, let alone English.
2. NEVER A DEAD END. Anything unparseable re-asks with the options visible.
3. THE LANGUAGE FOLLOWS THE USER. Script detection on the first message, and a
   switch at any point without losing the conversation.
4. NO MODEL ON THE CRITICAL PATH. Deterministic parsers handle every expected
   answer; the LLM is a fallback for free text only, and its absence costs
   nothing but flexibility.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from src.calculator import MoratoriumType, calculate_emi
from src.discovery import Facets, discover
from src.paths import MEDIA_DIR, TILE_DIR
from src.config import SCHEMES, get_settings
from src.i18n import DEFAULT_LANGUAGE, LANGUAGES, detect_language, t
from src.routing import route_partners, utilisation_note
from src.schemes import (
    UserProfile,
    evaluate_eligibility,
    format_rupees,
    notable_rejections,
)
from src.seed import partners_near

logger = logging.getLogger(__name__)

# Two tracks, because "what do you need?" has two very different answers.
#
# The first build asked "what do you need the money for?" and offered business
# or a course. That was written when this was an NSFDC credit tool, and it is
# wrong for what the product now is: most of the 4,736 schemes are not money at
# all. A widow needing a pension, a family needing a house, a child needing a
# scholarship — none of them are asking for a loan, and being asked about
# project cost is how a person concludes this is not for them and leaves.
#
# So the opening asks what kind of help is needed. Credit questions are asked
# only of people who said they want to borrow.
STEPS_CREDIT = ["need", "cost", "income", "category", "gender", "place", "done"]
STEPS_WELFARE = ["need", "category", "place", "done"]

# What people come for, mapped to the corpus's own category strings. The values
# are exact: a category name we invent filters to nothing.
NEEDS = [
    {"id": "business", "track": "credit", "project_type": "business", "category": None},
    {"id": "study", "track": "welfare", "category": "Education & Learning"},
    {"id": "housing", "track": "welfare", "category": "Housing & Shelter"},
    {"id": "pension", "track": "welfare", "category": "Social welfare & Empowerment"},
    {"id": "health", "track": "welfare", "category": "Health & Wellness"},
    {"id": "job", "track": "welfare", "category": "Skills & Employment"},
    {"id": "farming", "track": "welfare", "category": "Agriculture,Rural & Environment"},
    {"id": "everything", "track": "welfare", "category": None},
]

NEED_BY_ID = {need["id"]: need for need in NEEDS}

PLACES = [
    {"id": "ballia", "label": "Ballia, Uttar Pradesh", "lat": 25.7585, "lon": 84.1487, "state": "Uttar Pradesh"},
    {"id": "delhi", "label": "New Delhi", "lat": 28.6139, "lon": 77.2090, "state": "Delhi"},
    {"id": "mumbai", "label": "Mumbai, Maharashtra", "lat": 19.0760, "lon": 72.8777, "state": "Maharashtra"},
    {"id": "chennai", "label": "Chennai, Tamil Nadu", "lat": 13.0827, "lon": 80.2707, "state": "Tamil Nadu"},
    {"id": "kolkata", "label": "Kolkata, West Bengal", "lat": 22.5726, "lon": 88.3639, "state": "West Bengal"},
]


@dataclass
class Session:
    session_id: str
    language: str = DEFAULT_LANGUAGE
    step: str = "need"
    track: str = "welfare"
    answers: dict[str, Any] = field(default_factory=dict)

    @property
    def steps(self) -> list[str]:
        return STEPS_CREDIT if self.track == "credit" else STEPS_WELFARE


_SESSIONS: dict[str, Session] = {}


def get_session(session_id: Optional[str]) -> Session:
    if session_id and session_id in _SESSIONS:
        return _SESSIONS[session_id]
    session = Session(session_id=session_id or uuid.uuid4().hex)
    _SESSIONS[session.session_id] = session
    return session


# ---------------------------------------------------------------------------
# Parsing — deterministic first, model only as a fallback
# ---------------------------------------------------------------------------

_NUM = re.compile(r"(\d[\d,]*\.?\d*)")


def parse_amount(text: str) -> Optional[float]:
    """Read an amount written how people actually write it.

    '1.4 lakh', '₹1,40,000', '50L', '2 crore', 'about 1 lakh 20 thousand'.
    Handles the multi-part case by summing, which is what someone does when they
    say 'my husband earns 2 lakh and I earn 80 thousand'.
    """
    if not text:
        return None
    lowered = text.lower().replace(",", "")
    total = 0.0
    found = False

    # Scaled amounts first, so "1.4 lakh" isn't read as a bare 1.4.
    for value, unit in re.findall(r"(\d+\.?\d*)\s*(crore|cr|lakh|lac|lakhs|l\b|thousand|k\b)", lowered):
        multiplier = (
            10_000_000 if unit in ("crore", "cr")
            else 100_000 if unit in ("lakh", "lac", "lakhs", "l")
            else 1_000
        )
        total += float(value) * multiplier
        found = True
    if found:
        return total

    numbers = _NUM.findall(lowered)
    if not numbers:
        return None
    return sum(float(n) for n in numbers)


_PURPOSE_WORDS = {
    "business": ["business", "shop", "tailor", "silai", "दुकान", "काम", "व्यवसाय", "व्यापार",
                 "ব্যবসা", "দোকান", "தொழில்", "கடை", "dairy", "farm", "auto", "salon", "kirana"],
    "education": ["education", "study", "college", "course", "school", "degree", "पढ़ाई", "शिक्षा",
                  "कॉलेज", "शिक्षण", "পড়া", "কলেজ", "படிப்பு", "கல்லூரி"],
}

_GENDER_WORDS = {
    "female": ["woman", "female", "girl", "wife", "महिला", "औरत", "स्त्री", "मुलगी", "মহিলা", "பெண்"],
    "male": ["man", "male", "boy", "husband", "पुरुष", "आदमी", "मर्द", "পুরুষ", "ஆண்"],
    "other": ["other", "अन्य", "इतर", "অন্য", "மற்ற"],
}

_CATEGORY_WORDS = {
    "SC": ["sc", "scheduled caste", "अनुसूचित जाति", "dalit"],
    "ST": ["st", "scheduled tribe", "अनुसूचित जनजाति", "adivasi", "tribal"],
    "OBC": ["obc", "backward", "पिछड़ा", "ओबीसी"],
    "MINORITY": ["minority", "अल्पसंख्यक", "muslim", "christian", "sikh"],
    "GENERAL": ["general", "सामान्य", "none"],
}


def _match_words(text: str, table: dict[str, list[str]]) -> Optional[str]:
    lowered = (text or "").lower()
    for key, words in table.items():
        if any(word in lowered for word in words):
            return key
    return None


# ---------------------------------------------------------------------------
# Turn construction
# ---------------------------------------------------------------------------

def _chip(value: str, label: str) -> dict:
    return {"value": value, "label": label}


def _question(session: Session) -> dict:
    """The prompt and options for the session's current step."""
    lang = session.language
    step = session.step

    if step == "need":
        return {"text": t("ask_need", lang), "chips": [
            _chip(need["id"], t(f"need_{need['id']}", lang)) for need in NEEDS
        ]}

    if step == "cost":
        return {"text": t("ask_cost", lang), "chips": [
            _chip("50000", "₹50,000"), _chip("120000", "₹1.2 " + ("लाख" if lang == "hi" else "lakh")),
            _chip("300000", "₹3 " + ("लाख" if lang == "hi" else "lakh")),
            _chip("1000000", "₹10 " + ("लाख" if lang == "hi" else "lakh")),
        ], "input": "amount"}

    if step == "income":
        return {"text": t("ask_income", lang), "chips": [
            _chip("120000", "₹1.2 lakh"), _chip("280000", "₹2.8 lakh"),
            _chip("450000", "₹4.5 lakh"), _chip("700000", "₹7 lakh"),
        ], "input": "amount"}

    if step == "category":
        return {"text": t("ask_category", lang), "chips": [
            _chip("SC", "SC"), _chip("ST", "ST"), _chip("OBC", "OBC"),
            _chip("MINORITY", "Minority"), _chip("GENERAL", "General"),
        ]}

    if step == "gender":
        return {"text": t("ask_gender", lang), "chips": [
            _chip("female", t("opt_woman", lang)),
            _chip("male", t("opt_man", lang)),
            _chip("other", t("opt_other", lang)),
        ]}

    if step == "place":
        return {"text": t("ask_place", lang),
                "chips": [_chip(p["id"], p["label"]) for p in PLACES]}

    return {"text": "", "chips": []}


def _advance(session: Session) -> None:
    steps = session.steps
    session.step = steps[min(steps.index(session.step) + 1, len(steps) - 1)]


def _accept(session: Session, message: str) -> bool:
    """Record an answer for the current step. False when it can't be read."""
    step, text = session.step, (message or "").strip()

    if step == "need":
        need = NEED_BY_ID.get(text.lower())
        if need is None:
            # Free text: fall back to the old business/course matcher, which
            # reads phrases like "I want to open a shop".
            guessed = _match_words(text, _PURPOSE_WORDS)
            if guessed == "business":
                need = NEED_BY_ID["business"]
            elif guessed == "education":
                need = NEED_BY_ID["study"]
        if need is None:
            return False

        session.track = need["track"]
        session.answers["need"] = need["id"]
        if need.get("category"):
            session.answers["scheme_category"] = need["category"]
        if need.get("project_type"):
            session.answers["project_type"] = need["project_type"]
        session.answers.setdefault("purpose_text", text)
        return True

    if step in ("cost", "income"):
        amount = parse_amount(text)
        if amount is None or amount <= 0:
            return False
        session.answers["project_cost" if step == "cost" else "annual_income"] = amount
        return True

    if step == "category":
        value = text.upper() if text.upper() in _CATEGORY_WORDS else _match_words(text, _CATEGORY_WORDS)
        if not value:
            return False
        session.answers["category"] = value
        return True

    if step == "gender":
        value = text.lower() if text.lower() in ("male", "female", "other") else _match_words(text, _GENDER_WORDS)
        if not value:
            return False
        session.answers["gender"] = value
        return True

    if step == "place":
        place = next((p for p in PLACES if p["id"] == text.lower()), None)
        if place is None:
            place = next((p for p in PLACES if p["label"].lower().split(",")[0] in text.lower()), None)
        if place is None:
            return False
        session.answers["place"] = place
        return True

    return False


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

async def _build_welfare_results(session: Session) -> tuple[str, list[dict]]:
    """Discovery for people who did not come here to borrow.

    Most schemes are not loans, so most conversations should end here: a ranked
    list of what this person is entitled to, with the reason each one matched.
    """
    lang = session.language
    a = session.answers
    place = a.get("place") or {}

    facets = Facets(
        caste=(a.get("category") or "").lower() or None,
        state=place.get("state"),
        categories=[a["scheme_category"]] if a.get("scheme_category") else [],
    )
    result = discover(facets, limit=6)

    if not result.matches:
        return t("welfare_none", lang), []

    cards: list[dict] = [{
        "kind": "matches",
        "total": result.total_matched,
        "targeted": result.total_targeted,
        "items": [
            {
                "name": m.name.strip(),
                "slug": m.slug,
                "state": m.state,
                "strength": m.strength.value,
                "matched_on": m.matched_on,
            }
            for m in result.matches[:6]
        ],
    }]
    cards.append({
        "kind": "notice", "tone": "quiet",
        "body": t("welfare_note", lang),
    })
    return t("welfare_intro", lang), cards


async def _build_results(session: Session) -> tuple[str, list[dict]]:
    """Run the engine and turn the outcome into cards."""
    if session.track != "credit":
        return await _build_welfare_results(session)

    lang = session.language
    a = session.answers
    profile = UserProfile(
        project_type=a.get("project_type", "business"),
        project_cost=a.get("project_cost", 0.0),
        annual_income=a.get("annual_income", 0.0),
        category=a.get("category", "SC"),
        gender=a.get("gender", "other"),
    )
    eligibility = evaluate_eligibility(profile)
    cards: list[dict] = []

    if not eligibility.matches:
        text = t("no_match", lang)
        if eligibility.category_note:
            cards.append({"kind": "notice", "tone": "info", "body": eligibility.category_note})
        for r in notable_rejections(eligibility, limit=3):
            cards.append({"kind": "rejection", "name": r.name, "reason": r.reason})
        return text, cards

    priced = []
    for match in eligibility.matches:
        cfg = SCHEMES[match.scheme_id]
        emi = calculate_emi(
            project_cost=profile.project_cost, financing_pct=match.financing_pct,
            rate_annual=match.rate_min, tenure_months=match.tenure_months,
            moratorium_months=match.moratorium_months,
            moratorium_type=MoratoriumType.SIMPLE_INTEREST,
            women_rebate_pct=match.women_rebate_pct,
            is_female=(profile.gender == "female"),
            periods_per_year=match.periods_per_year,
        )
        priced.append((match, emi))
    priced.sort(key=lambda pair: pair[1].total_interest)

    best_match, best_emi = priced[0]

    text = (t("result_intro_one", lang) if len(priced) == 1
            else t("result_intro_many", lang, n=len(priced)))

    for index, (match, emi) in enumerate(priced):
        cards.append({
            "kind": "scheme",
            "best": index == 0,
            "scheme_id": match.scheme_id,
            "name": match.name,
            "rate": emi.rate_annual,
            "loan": format_rupees(emi.loan_amount),
            "interest": format_rupees(emi.total_interest),
            "total": format_rupees(emi.total_payable),
            "instalment": format_rupees(emi.instalment_amount),
            "instalment_count": emi.instalment_count,
            "monthly": format_rupees(emi.monthly_equivalent),
            "years": max(1, emi.tenure_months // 12),
            "grace_months": emi.moratorium_months,
            "why": match.why_eligible,
        })

    informal = best_emi.loan_amount * (get_settings().moneylender_monthly_rate_pct / 100.0) \
        * best_emi.repayment_months
    cards.append({
        "kind": "compare",
        "loan": format_rupees(best_emi.loan_amount),
        "scheme_label": f"{best_match.name}, {best_emi.rate_annual}%",
        "scheme_amount": format_rupees(best_emi.total_interest),
        "scheme_raw": best_emi.total_interest,
        "alt_label": t("moneylender", lang),
        "alt_amount": format_rupees(informal),
        "alt_raw": informal,
        "saving": format_rupees(informal - best_emi.total_interest),
    })

    rejections = notable_rejections(eligibility, limit=2)
    if rejections:
        cards.append({"kind": "whynot", "items": [
            {"name": r.name, "reason": r.reason} for r in rejections]})

    place = a.get("place")
    if place:
        candidates = partners_near(place["lat"], place["lon"], 150.0)
        routing = route_partners(best_match, place["lat"], place["lon"], candidates,
                                 radius_km=150.0, user_state=place["state"])
        if routing.viable:
            cards.append({"kind": "partners", "items": [
                {
                    "name": r.partner.name,
                    "where": f'{r.partner.district}, {r.partner.state}',
                    "distance_km": r.distance_km,
                    "rate": r.beneficiary_rate,
                    "note": utilisation_note(r.partner),
                    "official": r.partner.utilisation_confidence == "OFFICIAL",
                }
                for r in routing.viable[:4]
            ]})
            map_url = await _render_map(place, routing.viable[:4])
            if map_url:
                cards.append({"kind": "map", "url": map_url})
        blocked = [e for e in routing.excluded
                   if e.rule not in ("OUT_OF_RADIUS", "NO_LOCATION")][:2]
        if blocked:
            cards.append({"kind": "blocked", "items": [
                {"name": e.name, "reason": e.reason} for e in blocked]})

    cards.append({"kind": "notice", "tone": "warn", "body": t("fraud_shield", lang)})
    cards.append({"kind": "notice", "tone": "quiet", "body": t("estimates_note", lang)})
    return text, cards


async def _render_map(place: dict, ranked) -> Optional[str]:
    """A map of the shortlisted offices. Never fatal — the list is the answer."""
    try:
        from pathlib import Path
        from src.maps import MapPin, render_map
        pins = [MapPin(place["lat"], place["lon"], "You")]
        pins += [MapPin(r.partner.latitude, r.partner.longitude, str(i + 1))
                 for i, r in enumerate(ranked)
                 if r.partner.latitude is not None]
        path = await render_map(pins, MEDIA_DIR, cache_dir=TILE_DIR)
        return f"/media/{path.name}"
    except Exception as exc:
        logger.warning("Chat map render failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# The one entry point
# ---------------------------------------------------------------------------

async def turn(
    session_id: Optional[str],
    message: str = "",
    language: Optional[str] = None,
    restart: bool = False,
) -> dict:
    """Advance the conversation by one turn."""
    session = get_session(session_id)

    if restart:
        session.step = "need"
        session.track = "welfare"
        session.answers = {}

    if language and language in LANGUAGES:
        session.language = language
    elif message and not session.answers:
        # Only on the opening message: after that an English digit shouldn't
        # yank someone out of Hindi mid-conversation.
        detected = detect_language(message)
        if detected:
            session.language = detected

    lang = session.language
    opening = not message and not session.answers and session.step == "need"

    if opening:
        question = _question(session)
        return {
            "session_id": session.session_id, "language": lang,
            "messages": [{"text": t("greet", lang)}, {"text": question["text"]}],
            "chips": question["chips"], "input": question.get("input"),
            "cards": [], "done": False, "step": session.step,
        }

    if session.step == "done":
        session.step = "need"
        session.track = "welfare"
        session.answers = {}
        question = _question(session)
        return {
            "session_id": session.session_id, "language": lang,
            "messages": [{"text": question["text"]}], "chips": question["chips"],
            "input": question.get("input"), "cards": [], "done": False, "step": session.step,
        }

    if not _accept(session, message):
        question = _question(session)
        return {
            "session_id": session.session_id, "language": lang,
            "messages": [{"text": t("didnt_understand", lang)}, {"text": question["text"]}],
            "chips": question["chips"], "input": question.get("input"),
            "cards": [], "done": False, "step": session.step,
        }

    _advance(session)

    if session.step == "done":
        text, cards = await _build_results(session)
        return {
            "session_id": session.session_id, "language": lang,
            "messages": [{"text": text}], "chips": [], "input": None,
            "cards": cards, "done": True, "step": "done",
        }

    question = _question(session)
    return {
        "session_id": session.session_id, "language": lang,
        "messages": [{"text": question["text"]}], "chips": question["chips"],
        "input": question.get("input"), "cards": [], "done": False, "step": session.step,
    }
