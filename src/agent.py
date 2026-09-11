"""
The assistant that can be asked anything, and answers with facts it looked up.

The model here is a router and a writer. It is emphatically NOT a decider: it
cannot judge eligibility, cannot invent a rupee figure, and cannot name an
office. Everything it says about who qualifies, what a loan costs and where to
go comes back from the deterministic functions in `discovery`, `schemes`,
`calculator` and `routing` — the same code paths the wizard and WhatsApp use.

That split is the whole design. A language model asked "can I get this loan?"
will happily answer, fluently and wrongly, and the person on the other end has
no way to tell. So the model is given tools and denied opinions: it decides
*which question is being asked*, the tools decide *what is true*, and the reply
is assembled from what they returned.

Every tool call is reported back to the interface, so a person can see that the
answer came from a lookup over 4,736 schemes rather than from a guess.

With no API key configured this module stands aside entirely and the scripted
conversation in `chat.py` takes over — a demo must never depend on a key.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from src import application
from src.calculator import calculate_emi
from src.catalog import catalog_meta, get_scheme, search_schemes
from src.paths import MEDIA_DIR, TILE_DIR
from src.config import SCHEMES, get_settings
from src.discovery import Facets, discover_with_credit, evaluate_scheme
from src.i18n import LANGUAGES
from src.routing import haversine_km, utilisation_note
from src.schemes import UserProfile, evaluate_eligibility, format_rupees
from src.seed import partners_near

logger = logging.getLogger(__name__)

# Seven tools chain: search, then read, then check eligibility, then price
# and route. Eight rounds is room to follow that through without looping.
# Every round is one API call, and the free tier allows twenty per model per
# DAY. Four rounds is enough to search, read, check eligibility and answer —
# and the model may emit several tool calls in a single round, which this loop
# already handles, so depth is cheaper than it looks.
MAX_TOOL_ROUNDS = 4

# Free-tier quota is counted per model, so a second model is a second budget.
# Falling down this list turns a hard stop mid-demo into a shrug. Order is
# roughly best-first; the lites are last because they are the least capable but
# the most likely to still have room.
FALLBACK_MODELS = (
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
)


# Models whose daily quota ran out, and when. Remembered between requests:
# without this, every question spends its first call rediscovering that the
# primary model is spent — the most wasteful call possible when the budget is
# what ran out.
_EXHAUSTED: dict[str, float] = {}
_QUOTA_COOLDOWN_SECONDS = 900


def _in_cooldown(model: str) -> bool:
    since = _EXHAUSTED.get(model)
    return since is not None and (time.monotonic() - since) < _QUOTA_COOLDOWN_SECONDS


def _is_quota_error(exc: Exception) -> bool:
    """Out of budget on this model — it will not clear for a while."""
    text = str(exc)
    return "RESOURCE_EXHAUSTED" in text or "429" in text


def _is_transient_error(exc: Exception) -> bool:
    """Busy or briefly broken. A different model is very likely fine.

    "This model is currently experiencing high demand" is the common one, and
    treating it as terminal — which this did at first — throws away a working
    fallback chain over a problem that lasts seconds.
    """
    text = str(exc)
    return any(marker in text for marker in (
        "UNAVAILABLE", "503", "500", "INTERNAL", "DEADLINE_EXCEEDED", "504",
    ))

SYSTEM_PROMPT = """\
You are Adhikaar AI, an assistant that helps people in India — especially \
Scheduled Caste, Scheduled Tribe, OBC and other marginalised households — find \
government schemes they are entitled to, understand what a loan really costs, \
and reach an office that can actually process it.

HOW YOU WORK
- You never judge eligibility yourself. Call a tool and report what it returns.
  If you have not called a tool, you do not know the answer.
- You never state a rupee figure that a tool did not return. Not an interest
  total, not an instalment, not a ceiling. No arithmetic of your own.
- You never name an office, branch or agency that `find_offices` did not return.
- You never name a scheme a tool did not return. Government scheme names are
  easy to invent and impossible for the reader to check.
- If a tool returns nothing, say so plainly and suggest what would change it
  (usually: their state, their community, or their household income).

WHICH TOOL
- They describe THEMSELVES ("I am a widow in Bihar") -> `find_schemes`.
- They describe a THING ("widow pension", "loan for a sewing machine", a scheme
  name) -> `search_schemes`.
- They name one scheme and ask about it -> `lookup_scheme` for what it says,
  then `check_scheme_eligibility` for whether they qualify.
- "Do I qualify for X?" -> ALWAYS `check_scheme_eligibility`. Never answer it
  from the scheme's prose alone.
- Money, interest, instalments, repayment -> `price_loan`.
- "Where do I go?" -> `find_offices`.
- "How many...", "what categories are there" -> `corpus_stats`.
- "How do I apply?", "what papers do I need?", "help me fill this" ->
  `prepare_application`, with everything you already know about them.

APPLYING
You can fill a form in. You cannot submit one, and you must never suggest
otherwise — not "I have applied for you", not "your application is sent", not
"I will submit this". Say what is filled, what they still have to write, what
to carry, and where to take it.

That restraint is the product working, not failing. Every agent who charges a
poor household a fee for a free government scheme offers to "handle it all",
and a person who believes an application was submitted when it was not will
stop chasing it and miss the window entirely.

Chain them. Searching, then reading the scheme, then checking eligibility
against it is a normal and good sequence — do it rather than guessing a step.

Do NOT repeat a search with reworded terms. If a search returned results, use
them; if it returned nothing, say so and suggest what would change it. You have
four rounds of tool calls, and a second search for the same thing spends one
that eligibility checking needed.

HOW YOU SPEAK
- Reply in the language named below, always. Never announce the language, never
  apologise for it, never offer to switch.
- Short sentences. No jargon. Assume the reader may be reading with difficulty,
  and may be reading this aloud to someone else.
- Never promise approval. Schemes have conditions in prose we have not read, so
  the honest word is "likely", never "you will get it".
- Money is life-changing here and fraud is common. If someone mentions paying a
  fee or an agent to get a government loan, tell them plainly that no fee is
  required."""


# The two channels show a tool's results in completely different ways, and the
# difference is not cosmetic: on the website the schemes are already on screen
# as cards, and on WhatsApp there is no screen at all — the message IS the
# entire interface. A single prompt cannot serve both, and when the web version
# was sent to WhatsApp the model wrote "the schemes are showing above on the
# screen" to someone holding a phone with nothing above.

SHAPE_WEB = """

SHAPE OF AN ANSWER

Every scheme a tool returned is ALREADY on the screen as a card, with its name,
its summary and its conditions. The reader can see them. Do not list them again.

This is the single most common way to make this interface worse: the cards say
everything, and then the same six schemes are repeated underneath in bold text,
so the person scrolls through the same list twice and trusts neither copy.

So write the part the cards cannot:
- Two to four sentences. What the answer to their question actually is.
- The judgement a list cannot make: which one to try FIRST, and why that one.
- The condition most likely to trip them up, named plainly. "This is for OBC
  applicants, and you said you are SC" is useful; "you may not be eligible" is
  not.
- The one next step worth taking.

Name a scheme only when you are saying something about it that is not on its
card. Never reproduce a card as a bulleted list. Never restate rupee figures
that a card already shows.

You may use light Markdown — **bold** for a scheme name you are singling out,
and short `-` lists for steps. Do not build tables or headings; this is read on
a phone."""


SHAPE_WHATSAPP = """

SHAPE OF A WHATSAPP MESSAGE

There are no cards here and no screen to point at. Your message is the whole
interface, on a small phone, often on a slow connection. Never say "above",
"on the screen", "below" or "the list" — there is nothing there but your words.

LENGTH IS THE WHOLE BATTLE. WhatsApp folds anything long behind a "Read more"
link, and a folded answer is an unread answer. Keep the entire message under
about six short lines. If you cannot say it in six lines, you are answering a
question they have not asked yet.

ONE THING PER MESSAGE. Either you ask a question, or you give an answer. Never
both. Asking "which state do you live in?" and then listing schemes anyway
tells the person their answer does not matter.

WHEN YOU DO NOT KNOW ENOUGH YET
A greeting like "hello, I am a poor SC woman" is not enough to recommend
anything — half of what decides a scheme is the state they live in. So reply
with a short greeting and ONE question, and nothing else. No list. No counts.
No "521 schemes match". Ask, and wait.

WHEN YOU DO HAVE ENOUGH
- Open with one line saying what you found.
- Then at most THREE schemes, one line each: the name, then three or four
  words on what it gives. Nothing more.
- Then one line: which to try first, and why.
- Then one short question inviting the next step.

FORMAT
- NEVER write a file path or a bare URL. A map is delivered as a picture, and
  a person sent the characters "/media/x.png" cannot open them, cannot see a
  map, and reads it as the assistant breaking. Say "the map is below"; the
  system attaches it.
- Emoji as signposts, at most one per line, always at the start: 🙏 greeting,
  ✅ good news, 📋 a scheme, 💰 money, 🏠 state or place, ⚠️ a warning,
  📄 documents, 👉 next step. Never decorative, never mid-sentence.
- Number choices 1️⃣ 2️⃣ 3️⃣ so they can reply with a digit — many people here
  dictate rather than type, and a digit is the easiest possible reply.
- **bold** only for a scheme name. No headings, no tables, no long dashes.
- A blank line between each idea. Dense text is unreadable on a phone."""



# Appended when the interface has a chosen language. Deliberately emphatic:
# every model tested replies in the script it was written to unless told
# otherwise, and that default is wrong for this audience.
LANGUAGE_RULE = """

THE LANGUAGE OF THIS REPLY: {name} ({native}).
Write every word of your reply in {name}, in its own script.

This is the language the person chose in the interface, and it overrides
whatever script their message happens to arrive in. Someone who reads only
{name} may still type in English letters, because that is what their phone
keyboard offers most easily — replying in English because they typed "helo"
hands them an answer they cannot read, which is the exact failure this product
exists to prevent.

Two things stay exactly as the tools returned them: the names of schemes,
offices and government programmes, which are published in a fixed form and have
to be recognisable at a counter, and rupee figures, which are already
formatted."""

SCHEME_FOCUS = """

THE SCHEME THEY ARE READING: {name}  (slug: {slug})

They opened this conversation from that scheme's page, so it is almost
certainly what they are asking about even when they do not name it. "Am I
eligible?", "what papers do I need?", "how much do I get?" all mean THIS one.

Look it up rather than answering from the name — call `lookup_scheme` with the
slug for what it says, and `check_scheme_eligibility` with the slug for whether
they qualify. Never describe a scheme you have not read.

If they clearly ask about something else, follow them; do not drag every
question back to this scheme."""


@dataclass
class ToolCall:
    """One lookup, shown to the person so the answer is traceable."""
    name: str
    label: str                                  # human-readable, for the UI
    arguments: dict = field(default_factory=dict)
    summary: str = ""


@dataclass
class AgentReply:
    text: str = ""
    cards: list[dict] = field(default_factory=list)
    trace: list[ToolCall] = field(default_factory=list)
    used_model: bool = False
    """Which model actually answered — it may not be the configured one."""
    model: str = ""
    """True when every model's daily quota is spent, so the caller can say so
    rather than showing an empty bubble."""
    quota_exhausted: bool = False


def is_available() -> bool:
    """Whether an agentic reply is possible at all."""
    return bool(get_settings().gemini_api_key)


# ---------------------------------------------------------------------------
# Tools
#
# Each returns (payload_for_the_model, cards_for_the_interface, summary). The
# model sees compact JSON; the person sees rendered cards built from the same
# call, so the two can never disagree.
# ---------------------------------------------------------------------------

def _tool_find_schemes(
    caste: Optional[str] = None,
    state: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    family_income: Optional[float] = None,
    occupation: Optional[str] = None,
    is_bpl: Optional[bool] = None,
    disability: Optional[bool] = None,
    is_student: Optional[bool] = None,
    categories: Optional[list[str]] = None,
) -> tuple[dict, list[dict], str]:
    """Deterministic match against the whole corpus."""
    facets = Facets(
        caste=caste, state=state, gender=gender, age=age,
        family_income=family_income, occupation=occupation, is_bpl=is_bpl,
        disability=disability, is_student=is_student,
        categories=categories or [],
    )
    result = discover_with_credit(facets, profile=None, limit=6)

    top = [
        {
            "name": m.name.strip(),
            "slug": m.slug,
            "state": m.state,
            "strength": m.strength.value,
            "matched_on": m.matched_on,
            "unknown": m.unknown,
        }
        for m in result.matches[:6]
    ]
    payload = {
        "total_matched": result.total_matched,
        "aimed_at_this_person": result.total_targeted,
        "considered": result.total_considered,
        "top_matches": top,
    }
    cards = [{
        "kind": "matches",
        "total": result.total_matched,
        "targeted": result.total_targeted,
        "items": top,
    }]
    summary = (
        f"{result.total_targeted} aimed at this person, "
        f"{result.total_matched} possible, of {result.total_considered}"
    )
    return payload, cards, summary


def _tool_price_loan(
    project_cost: float,
    annual_income: float,
    project_type: str = "business",
    category: str = "SC",
    gender: str = "male",
) -> tuple[dict, list[dict], str]:
    """Which NSFDC schemes fit, and what each actually costs."""
    try:
        profile = UserProfile(
            project_type=project_type, project_cost=project_cost,
            annual_income=annual_income, category=category.upper(), gender=gender,
        )
    except ValueError as exc:
        return {"error": str(exc)}, [], "invalid profile"

    result = evaluate_eligibility(profile)
    if not result.matches:
        payload = {
            "eligible": False,
            "reasons": [r.reason for r in result.rejections],
            "referral": result.referral_note,
        }
        return payload, [], "no NSFDC scheme fits"

    priced = []
    cards = []
    for index, match in enumerate(result.matches):
        scheme = SCHEMES[match.scheme_id]
        quote = calculate_emi(
            project_cost=profile.project_cost,
            financing_pct=scheme["financing_pct"],
            rate_annual=match.rate_min,
            tenure_months=scheme["tenure_months"],
            moratorium_months=scheme["moratorium_months"],
            women_rebate_pct=match.women_rebate_pct,
            is_female=profile.gender == "female",
            periods_per_year=scheme["periods_per_year"],
        )
        priced.append({
            "name": match.name,
            "rate_percent": quote.rate_annual,
            "loan": format_rupees(quote.loan_amount),
            "each_instalment": format_rupees(quote.instalment_amount),
            "instalments": quote.instalment_count,
            "total_interest": format_rupees(quote.total_interest),
            "why": match.why_eligible,
        })
        cards.append({
            "kind": "scheme",
            "best": index == 0,
            "name": match.name,
            "rate": quote.rate_annual,
            "loan": format_rupees(quote.loan_amount),
            "instalment": format_rupees(quote.instalment_amount),
            "instalment_count": quote.instalment_count,
            "interest": format_rupees(quote.total_interest),
            "total": format_rupees(quote.total_payable),
            "years": scheme["tenure_months"] // 12,
            "grace_months": scheme["moratorium_months"],
            "why": match.why_eligible,
        })

    payload = {"eligible": True, "schemes": priced,
               "not_offered": [r.reason for r in result.rejections]}
    return payload, cards, f"{len(priced)} scheme(s) priced"


def _tool_find_offices(
    state: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> tuple[dict, list[dict], str]:
    """Offices that can actually disburse, nearest first.

    No interest rate is returned here. Rates are per-scheme and per-partner-type,
    so quoting one without knowing the scheme would be a made-up number attached
    to a real office — exactly the kind of confident wrongness this design exists
    to prevent. `price_loan` is where rates come from.
    """
    partners = partners_near(latitude, longitude, radius_km=250)

    # A state agency lends within its own state only, so one from elsewhere is
    # not a lead, it is a wasted journey.
    def serves(partner) -> bool:
        if partner.partner_type != "SCA":
            return True
        return (partner.state or "").strip().lower() == state.strip().lower()

    candidates = [p for p in partners if serves(p)]
    if latitude is not None and longitude is not None:
        candidates.sort(key=lambda p: haversine_km(
            latitude, longitude, p.latitude, p.longitude,
        ) if p.latitude and p.longitude else 1e9)

    items = []
    # Kept beside the items rather than inside them: the model is shown the
    # items and has no use for coordinates, but the interface needs them to
    # draw the map. See the map rendering in the tool loop.
    pins: list[dict] = []
    if latitude is not None and longitude is not None:
        pins.append({"lat": latitude, "lon": longitude, "label": "You"})

    for partner in candidates[:4]:
        distance = (
            round(haversine_km(latitude, longitude, partner.latitude, partner.longitude), 1)
            if latitude is not None and longitude is not None
            and partner.latitude and partner.longitude
            else None
        )
        if partner.latitude is not None and partner.longitude is not None:
            pins.append({
                "lat": partner.latitude,
                "lon": partner.longitude,
                "label": str(len(pins) if latitude is not None else len(pins) + 1),
            })
        items.append({
            "name": partner.name,
            "where": ", ".join(x for x in (partner.district, partner.state) if x),
            "distance_km": distance,
            "type": partner.partner_type,
            "note": utilisation_note(partner) or "",
            "official": partner.partner_type == "SCA",
        })

    if not items:
        return {"offices": []}, [], "no office found"
    return ({"offices": items},
            [{"kind": "partners", "items": items, "pins": pins}],
            f"{len(items)} office(s) in {state}")


def _tool_lookup_scheme(query: str) -> tuple[dict, list[dict], str]:
    """Find a scheme by name and return what it actually says."""
    page = search_schemes(q=query, page_size=3)
    if not page.items:
        return {"found": []}, [], "nothing found"

    first = get_scheme(page.items[0].slug)
    payload = {
        "found": [{"name": i.name.strip(), "slug": i.slug, "state": i.state}
                  for i in page.items],
        "detail": None,
    }
    cards: list[dict] = []
    if first:
        payload["detail"] = {
            "name": first["name"].strip(),
            "benefits": (first.get("benefits_md") or "")[:900],
            "eligibility": (first.get("eligibility_md") or "")[:900],
            "how_to_apply": (first.get("application_md") or "")[:900],
        }
        cards.append({
            "kind": "scheme_link",
            "name": first["name"].strip(),
            "slug": first["slug"],
            "brief": first.get("brief") or "",
            "state": first.get("state"),
        })
    return payload, cards, f"{len(page.items)} match(es)"


def _tool_search_schemes(
    query: str,
    state: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 6,
) -> tuple[dict, list[dict], str]:
    """Free-text search, for when the person describes a thing rather than
    themselves — "widow pension", "loan for a sewing machine", a scheme name
    half-remembered."""
    page = search_schemes(q=query, state=state, category=category,
                          page_size=max(1, min(limit, 10)))
    items = [
        {"name": i.name.strip(), "slug": i.slug, "state": i.state,
         "categories": i.categories, "brief": (i.brief or "")[:220]}
        for i in page.items
    ]
    cards = [{"kind": "scheme_list", "title": query, "total": page.total,
              "items": items}] if items else []
    return ({"total_found": page.total, "showing": items},
            cards,
            f"{page.total} found for '{query[:30]}'")


def _tool_check_scheme_eligibility(
    slug: str,
    caste: Optional[str] = None,
    state: Optional[str] = None,
    gender: Optional[str] = None,
    age: Optional[int] = None,
    family_income: Optional[float] = None,
    occupation: Optional[str] = None,
    is_bpl: Optional[bool] = None,
    disability: Optional[bool] = None,
    is_student: Optional[bool] = None,
) -> tuple[dict, list[dict], str]:
    """Does this person qualify for this one scheme, and if not, which rule
    stops them?"""
    facets = Facets(caste=caste, state=state, gender=gender, age=age,
                    family_income=family_income, occupation=occupation,
                    is_bpl=is_bpl, disability=disability, is_student=is_student)
    match = evaluate_scheme(slug, facets)
    if match is None:
        return {"error": f"No scheme with slug '{slug}'"}, [], "not found"

    payload = {
        "scheme": match.name.strip(),
        "verdict": match.strength.value,
        "meets": match.matched_on,
        "not_asked": match.unknown,
        "fails_on": match.unmet,
    }
    cards = [{
        "kind": "eligibility",
        "name": match.name.strip(),
        "slug": match.slug,
        "verdict": match.strength.value,
        "meets": match.matched_on,
        "unknown": match.unknown,
        "unmet": match.unmet,
    }]
    return payload, cards, f"{match.strength.value.lower()} for {match.name.strip()[:34]}"


def _tool_corpus_stats(
    state: Optional[str] = None,
    category: Optional[str] = None,
) -> tuple[dict, list[dict], str]:
    """Counts, for "how many housing schemes does Bihar have?" — questions
    about the landscape rather than about one person."""
    page = search_schemes(state=state, category=category, page_size=1)
    meta = catalog_meta()
    payload = {
        "matching_count": page.total,
        "corpus_total": meta.get("total"),
        "filters": {"state": state, "category": category},
    }
    if not state and not category:
        payload["categories"] = meta.get("categories", [])[:15]
    return payload, [], f"{page.total} schemes"


def _tool_prepare_application(
    slug: str,
    known: Optional[dict] = None,
) -> tuple[dict, list[dict], str]:
    """Fill in this scheme's application from what the person has told us.

    Returns the fields we could complete, the ones they must write themselves,
    the documents to carry and the steps in order. It submits NOTHING — see
    `src.application` for why that is a decision rather than a gap.
    """
    pack = application.build(slug, known or {})
    if pack is None:
        return {"error": f"No scheme with slug '{slug}'"}, [], "no such scheme"

    payload = application.to_dict(pack)
    card = {
        "kind": "application",
        "slug": payload["slug"],
        "name": payload["name"],
        "mode": payload["mode"],
        "filled": payload["filled"],
        "total": payload["total"],
        "blanks": [f["label"] for f in payload["fields"] if f["blank"]],
        "documents": [d["text"] for d in payload["documents"]],
        "steps": payload["steps"][:8],
        "official_url": payload["official_url"],
    }
    summary = f"{payload['filled']} of {payload['total']} fields filled"
    return payload, [card], summary


async def _render_office_map(cards: list[dict]) -> Optional[dict]:
    """A map card for whatever `find_offices` just returned, or nothing.

    Never fatal and never retried. The list of offices is the answer; the map
    is how that answer is read at a glance, and a tile server having a bad
    minute is not a reason to fail the reply.
    """
    pins_raw: list[dict] = []
    for card in cards:
        if card.get("kind") == "partners":
            pins_raw = card.get("pins") or []
            break
    if len(pins_raw) < 1:
        return None

    try:
        from pathlib import Path
        from src.maps import MapPin, render_map

        pins = [MapPin(p["lat"], p["lon"], p.get("label", "")) for p in pins_raw]
        path = await render_map(pins, MEDIA_DIR, cache_dir=TILE_DIR)
        return {"kind": "map", "url": f"/media/{path.name}"}
    except Exception as exc:                          # noqa: BLE001
        logger.warning("Agent map render failed: %s", exc)
        return None


def _clean_args(args: dict) -> dict:
    """Repair the shapes a model hands back for an object-typed argument.

    Gemini serialises a nested object as a JSON STRING often enough that it
    cannot be treated as an exception: `prepare_application` was handed
    `known` as text, `known.get(...)` raised, the tool failed three times in
    one turn, and the model quietly fell back to answering from the scheme's
    prose — a wrong answer with no error anywhere the person could see.

    Parsed rather than rejected, because the content is right and only the
    envelope is wrong.
    """
    cleaned = dict(args)
    for key, value in list(cleaned.items()):
        if isinstance(value, str) and value[:1] in "{[":
            try:
                cleaned[key] = json.loads(value)
            except (ValueError, TypeError):
                pass
        # A model that has nothing to send sometimes sends the word instead.
        if cleaned.get(key) in ("null", "None", "{}"):
            cleaned[key] = None
    return cleaned


TOOL_IMPLEMENTATIONS = {
    "search_schemes": _tool_search_schemes,
    "check_scheme_eligibility": _tool_check_scheme_eligibility,
    "corpus_stats": _tool_corpus_stats,
    "find_schemes": _tool_find_schemes,
    "price_loan": _tool_price_loan,
    "find_offices": _tool_find_offices,
    "lookup_scheme": _tool_lookup_scheme,
    "prepare_application": _tool_prepare_application,
}

TOOL_LABELS = {
    "search_schemes": "Searched the scheme corpus",
    "check_scheme_eligibility": "Checked this scheme's rules against you",
    "corpus_stats": "Counted what exists",
    "find_schemes": "Matched against every scheme in the corpus",
    "price_loan": "Calculated the repayment",
    "find_offices": "Looked up offices that can disburse",
    "lookup_scheme": "Read the scheme's published text",
    "prepare_application": "Filled in the application form",
}

# Declared for the model. Descriptions matter more than names here — they are
# how it decides which question it is being asked.
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "search_schemes",
        "description": (
            "Search schemes by words — a scheme name, or a thing someone needs "
            "('widow pension', 'sewing machine loan', 'girl child scholarship'). "
            "Use when the person describes a THING rather than themselves. Use "
            "find_schemes instead when they describe who they are."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "state": {"type": "string", "description": "Optional full state name"},
                "category": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_scheme_eligibility",
        "description": (
            "Check ONE named scheme against this person and report which "
            "conditions they meet, which are unknown, and which one blocks them. "
            "Use after search_schemes or lookup_scheme has given you a slug, and "
            "whenever someone asks 'do I qualify for X'. Never answer that "
            "question without calling this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "The scheme's slug from another tool"},
                "caste": {"type": "string"},
                "state": {"type": "string"},
                "gender": {"type": "string"},
                "age": {"type": "integer"},
                "family_income": {"type": "number"},
                "occupation": {"type": "string"},
                "is_bpl": {"type": "boolean"},
                "disability": {"type": "boolean"},
                "is_student": {"type": "boolean"},
            },
            "required": ["slug"],
        },
    },
    {
        "name": "corpus_stats",
        "description": (
            "How many schemes exist, optionally for one state or category. Use "
            "for questions about the landscape — 'how many housing schemes does "
            "Bihar have', 'what categories are there' — not about one person."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "category": {"type": "string"},
            },
        },
    },
    {
        "name": "find_schemes",
        "description": (
            "Find government welfare and credit schemes a person may be entitled "
            "to. Use for any question about what someone can get, apply for, or "
            "is eligible for. Pass only what the person has actually said — every "
            "argument is optional and omitting one never hides schemes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caste": {"type": "string", "description": "sc, st, obc, pvtg, dnt or general"},
                "state": {"type": "string", "description": "Full state name, e.g. 'Uttar Pradesh'"},
                "gender": {"type": "string", "description": "female, male or transgender"},
                "age": {"type": "integer"},
                "family_income": {"type": "number", "description": "Whole household, per year, in rupees"},
                "occupation": {"type": "string", "description": "e.g. 'Farmer', 'Safai Karamchari', 'Construction Worker'"},
                "is_bpl": {"type": "boolean"},
                "disability": {"type": "boolean"},
                "is_student": {"type": "boolean"},
                "categories": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Areas of need, e.g. 'Education & Learning', 'Housing & Shelter'",
                },
            },
        },
    },
    {
        "name": "price_loan",
        "description": (
            "Work out which NSFDC credit schemes fit a project and exactly what "
            "each costs — instalment, total interest, total repaid. Use whenever "
            "money, a loan, interest or repayment is discussed. Requires the "
            "project cost and the household's annual income."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_cost": {"type": "number", "description": "Cost of the business or course, in rupees"},
                "annual_income": {"type": "number", "description": "Whole household, per year, in rupees"},
                "project_type": {"type": "string", "description": "'business' or 'education'"},
                "category": {"type": "string", "description": "SC, ST, OBC or GENERAL"},
                "gender": {"type": "string", "description": "female, male or other"},
            },
            "required": ["project_cost", "annual_income"],
        },
    },
    {
        "name": "find_offices",
        "description": (
            "Find the offices, banks or state agencies that can actually process "
            "and disburse an NSFDC loan near someone. Use for 'where do I go' or "
            "'who gives this money' questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
            },
            "required": ["state"],
        },
    },
    {
        "name": "prepare_application",
        "description": (
            "Fill in a scheme's application form for this person. Give the "
            "scheme's slug and everything you already know about them, and it "
            "returns the fields it could complete, the ones they must write "
            "themselves, the documents to carry and the steps in order. "
            "Use when someone asks how to apply, what to bring, or to help "
            "them fill the form. It does NOT submit the application anywhere "
            "and you must never say that it did — say what is filled, what is "
            "left, and where to take it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string"},
                "known": {
                    "type": "object",
                    "description": (
                        "What the person has told you: full_name, parent_name, "
                        "dob, gender, category, address, state, district, "
                        "pincode, mobile, income, purpose, project_cost, "
                        "bank_name, institution, course, year. Omit anything "
                        "they have not said; never invent a value."
                    ),
                },
            },
            "required": ["slug"],
        },
    },
    {
        "name": "lookup_scheme",
        "description": (
            "Look up one named scheme and read its published benefits, eligibility "
            "and application process. Use when the person names a scheme."
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

async def stream(
    message: str,
    history: Optional[list[dict]] = None,
    context: Optional[dict] = None,
    language: Optional[str] = None,
    channel: str = "web",
) -> "AsyncIterator[dict]":
    """One turn, reported as it happens.

    Yields `{"type": "tool", ...}` the moment each lookup returns, then
    `{"type": "text", ...}` with the written answer, then `{"type": "done"}`.

    A generator rather than a single return because a turn takes twenty to sixty
    seconds — four model round-trips and up to seven lookups — and a person
    watching a spinner for a minute assumes it has hung. Showing "searched the
    corpus, 6 found" as it lands is both more honest and less anxious than a
    progress message we made up.

    `context` carries what the interface already knows (state, caste, income),
    so the person is not asked again for something they typed into the wizard
    five seconds ago. `language` is the one chosen in the interface, and it wins
    over the script the message happens to arrive in.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        yield {"type": "unavailable", "quota_exhausted": False}
        return

    from langchain_core.messages import (
        AIMessage, HumanMessage, SystemMessage, ToolMessage,
    )
    from langchain_google_genai import ChatGoogleGenerativeAI

    system = SYSTEM_PROMPT + (
        SHAPE_WHATSAPP if channel == "whatsapp" else SHAPE_WEB
    )
    if language and language in LANGUAGES:
        meta = LANGUAGES[language]
        system += LANGUAGE_RULE.format(name=meta["name"], native=meta["native"])
    if context:
        # The scheme they are reading is not a fact ABOUT them, so it must not
        # go into the "what you already know about this person" block — listed
        # there it reads as though they told us their caste is a scheme slug.
        focus_slug = context.get("scheme") or ""
        focus_name = context.get("scheme_name") or ""

        known = {
            k: v for k, v in context.items()
            if k not in ("scheme", "scheme_name") and v not in (None, "", [])
        }
        if known:
            system += (
                "\n\nWhat you already know about this person, from what they "
                f"filled in earlier — use it, do not ask again: {json.dumps(known)}"
            )
        if focus_slug:
            system += SCHEME_FOCUS.format(name=focus_name or focus_slug,
                                          slug=focus_slug)

    messages: list[Any] = [SystemMessage(content=system)]
    for turn in history or []:
        role = turn.get("role")
        text = turn.get("text") or ""
        if not text:
            continue
        messages.append(HumanMessage(content=text) if role == "user"
                        else AIMessage(content=text))
    messages.append(HumanMessage(content=message))

    # One budget per model, tried in order. `max_retries=0` because the library
    # otherwise spends thirty seconds backing off a quota error that will not
    # clear for another minute — time better spent on the next model.
    chain: list[str] = []
    for name in (settings.gemini_model_generation, *FALLBACK_MODELS):
        if name and name not in chain and not _in_cooldown(name):
            chain.append(name)
    if not chain:
        # Everything is in cooldown. Say so rather than trying anyway.
        yield {"type": "unavailable", "quota_exhausted": True}
        return

    state: dict[str, Any] = {"index": 0, "quota": False}

    def make(model: str, with_tools: bool):
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
            max_retries=0,
        )
        return llm.bind_tools([{"function_declarations": TOOL_SCHEMAS}]) if with_tools else llm

    async def invoke(with_tools: bool = True):
        """Ask the current model; on an exhausted quota, move down the chain.

        Returns None when every model is spent — the caller then says so, which
        is the honest outcome and better than an empty bubble.
        """
        while state["index"] < len(chain):
            model = chain[state["index"]]
            try:
                result = await make(model, with_tools).ainvoke(messages)
                reply.model = model
                return result
            except Exception as exc:                  # noqa: BLE001
                if _is_quota_error(exc):
                    logger.info("Quota spent on %s, falling back", model)
                    _EXHAUSTED[model] = time.monotonic()
                    state["quota"] = True
                    state["index"] += 1
                    continue
                if _is_transient_error(exc):
                    logger.info("%s is busy, falling back", model)
                    state["index"] += 1
                    continue
                logger.warning("Agent call failed on %s: %s", model, exc)
                return None
        logger.warning("Every model in the chain is spent or unavailable")
        # Only claim "quota" if that is what actually happened; a chain of
        # overloads is a different problem and deserves a different message.
        reply.quota_exhausted = bool(state.get("quota"))
        return None

    reply = AgentReply(used_model=True)

    for _ in range(MAX_TOOL_ROUNDS):
        response = await invoke(with_tools=True)
        if response is None:
            # No model answered. The scripted flow takes over unless the reason
            # was quota, which the interface should state plainly.
            yield {"type": "unavailable", "quota_exhausted": reply.quota_exhausted}
            return

        calls = getattr(response, "tool_calls", None) or []
        if not calls:
            reply.text = _text_of(response)
            yield {"type": "text", "text": reply.text, "model": reply.model}
            yield {"type": "done"}
            return

        messages.append(response)
        for call in calls:
            name = call.get("name")
            args = _clean_args(call.get("args") or {})
            # The person's own details, handed to the tool that fills forms
            # rather than left to the model to copy across. It has them in the
            # prompt, but relying on it to retype an eleven-field object into a
            # function argument is a coin flip, and losing it means a blank form.
            if name == "prepare_application" and context:
                merged = {k: v for k, v in context.items()
                          if k not in ("scheme", "scheme_name") and v}
                # Whatever the model sent is only merged if it is actually an
                # object. It has arrived as a JSON string, as a list, and as
                # the bare word "null"; none of those are worth a crash when
                # the context already holds everything the form needs.
                supplied = args.get("known")
                if isinstance(supplied, dict):
                    merged.update(supplied)
                args["known"] = merged
            implementation = TOOL_IMPLEMENTATIONS.get(name)
            if implementation is None:
                payload, cards, summary = {"error": "unknown tool"}, [], "unknown"
            else:
                try:
                    payload, cards, summary = implementation(**args)
                except Exception as exc:              # noqa: BLE001
                    logger.warning("Tool %s failed: %s", name, exc)
                    payload, cards, summary = {"error": str(exc)}, [], "failed"

            # A list of offices answers "which"; a map answers "where", and
            # the second is the question someone standing at a bus stand is
            # actually asking. The scripted flow has always drawn one — the
            # agentic path returned only the list, so the model could never
            # show it however clearly it was asked.
            if name == "find_offices":
                map_card = await _render_office_map(cards)
                if map_card is not None:
                    cards.append(map_card)

            reply.cards.extend(cards)
            step = ToolCall(
                name=name or "",
                label=TOOL_LABELS.get(name or "", "Looked something up"),
                arguments=args,
                summary=summary,
            )
            reply.trace.append(step)
            yield {"type": "tool", "name": step.name, "label": step.label,
                   "summary": step.summary, "cards": cards}
            messages.append(ToolMessage(
                content=json.dumps(payload, ensure_ascii=False, default=str),
                tool_call_id=call.get("id") or name or "tool",
            ))

    # Out of tool rounds. Ask once more with the tools withheld, so the model
    # has no option but to write prose.
    #
    # The bug this replaces returned `messages[-1]`, which at this point is a
    # ToolMessage — meaning a person who asked about their daughter's schooling
    # got a wall of raw JSON. Anything is better than that, including silence:
    # the interface still renders the cards and the lookup trace, which are the
    # parts that carry the facts.
    final = await invoke(with_tools=False)
    reply.text = _text_of(final) if final is not None else ""

    # Some models answer an empty string when they still want a tool they can no
    # longer reach. Saying so plainly gets prose on the second ask.
    if not reply.text:
        messages.append(HumanMessage(content=(
            "You have no more tool calls. Using only what the tools already "
            "returned above, write the answer now, in the language the person "
            "used. Do not ask for more information."
        )))
        final = await invoke(with_tools=False)
        reply.text = _text_of(final) if final is not None else ""

    yield {"type": "text", "text": reply.text, "model": reply.model}
    yield {"type": "done"}


async def respond(
    message: str,
    history: Optional[list[dict]] = None,
    context: Optional[dict] = None,
    language: Optional[str] = None,
    channel: str = "web",
) -> AgentReply:
    """The whole turn at once, for callers that cannot stream — WhatsApp, and
    anything that just wants the answer."""
    reply = AgentReply(used_model=True)
    async for event in stream(message, history, context, language, channel):
        kind = event.get("type")
        if kind == "tool":
            reply.cards.extend(event.get("cards") or [])
            reply.trace.append(ToolCall(
                name=event.get("name", ""), label=event.get("label", ""),
                summary=event.get("summary", ""),
            ))
        elif kind == "text":
            reply.text = event.get("text", "")
            reply.model = event.get("model", "")
        elif kind == "unavailable":
            return AgentReply(used_model=False,
                              quota_exhausted=bool(event.get("quota_exhausted")))
    return reply


def _text_of(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        ]
        return "".join(parts).strip()
    return str(content).strip()
