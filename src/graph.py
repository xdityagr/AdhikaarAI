"""
LangGraph conversation graph — Phase 0 + Phase 1 + Phase 2.

Phase 0 (proven): check_consent, process_message (echo with state proof)
Phase 1 (proven): process_intake — conversational intake flow for scheme matching
Phase 2 (new): Quick-reply buttons for categorical fields (project type, gender)

Intake flow collects: project_type → project_cost → annual_income → gender
Then runs Tier 1 eligibility (schemes.py) + EMI calculator (calculator.py)
and returns formatted results per phrases.md templates.

Phase 2 additions:
- button_payload in state: carries Twilio ButtonPayload from webhook
- response_content_sid in state: when set, worker sends button message
- Intake steps try ButtonPayload first, fall back to text parsing
- Dual-mode: use_button_messages=false → pure text (Sandbox-safe)

Architecture.md Non-negotiable #2: Uses LangGraph's own checkpointer
for state, keyed by thread_id (= WhatsApp number). NOT a custom table.

Note: check_consent clears the response field explicitly when an already-
consented user sends a regular message. This prevents a stale response from
the previous graph invocation from short-circuiting route_after_consent.
"""

from __future__ import annotations

import logging
import re
from typing import TypedDict, Literal, Optional

from langgraph.graph import StateGraph, END

from src.schemes import (
    UserProfile,
    SchemeMatch,
    evaluate_eligibility,
    evaluate_eligible_schemes,
)
from src.literacy import (
    format_fraud_shield,
    format_instalment,
    format_moneylender_comparison,
    format_moratorium_strip,
    format_priority_note,
    format_scheme_comparison,
    format_true_cost,
    format_why_not,
)
from src.calculator import calculate_emi, MoratoriumType
from src.config import get_settings, SCHEMES

from src.database import get_connection
from src.llm import extract_project_type, generate_recommendation_template, format_recommendation
from src.cache import generate_fingerprint, get_cached_template, set_cached_template

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State schema — Phase 0 fields + Phase 1 intake fields
# ---------------------------------------------------------------------------

class ConversationState(TypedDict):
    """State persisted by LangGraph's checkpointer between messages."""
    message: str                     # Current inbound message text
    message_count: int               # Total messages from this user (state proof)
    response: str                    # Outbound response to send
    consent_given: bool              # Has user sent START?
    # Phase 1 — intake flow state
    intake_step: str                 # Current step in intake flow
    project_type: str                # "business" or "education"
    project_cost: float              # In ₹
    annual_income: float             # Family annual income in ₹
    gender: str                      # "male", "female", "other"
    # Phase 2 — button support
    button_payload: str              # Twilio ButtonPayload from webhook (e.g. "project_type:business")
    response_content_sid: str        # If set, worker sends Content Template instead of plain text


# ---------------------------------------------------------------------------
# Consent notice — from phrases.md §1
# ---------------------------------------------------------------------------

CONSENT_NOTICE = (
    "Namaste! I can help you find the right NSFDC loan or education scheme, "
    "estimate your EMI, and point you to your nearest eligible bank/agency.\n\n"
    "To do this, I'll ask for your project details, income, and category — "
    "used only to check scheme eligibility, not stored beyond this purpose.\n\n"
    "Reply *START* to continue."
)

STOP_NOTICE = (
    "Your conversation data has been cleared. "
    "Reply *START* anytime to begin again."
)


# ---------------------------------------------------------------------------
# Intake prompts — from phrases.md §3
# ---------------------------------------------------------------------------

PROMPT_PROJECT_TYPE = (
    "Are you looking for a *business loan* or an *education loan*?\n\n"
    "Reply *business* or *education*."
)

PROMPT_PROJECT_COST = (
    "Roughly how much will your {type_label} cost to set up? (in ₹)\n\n"
    "You can type the amount like: 140000, 1.4 lakh, or 50L"
)

PROMPT_ANNUAL_INCOME = (
    "What's your family's approximate annual income? (in ₹)\n\n"
    "You can type: 300000, 3 lakh, or 5L"
)

PROMPT_GENDER = (
    "What is your gender? Some schemes offer a rebate for women.\n\n"
    "Reply *male*, *female*, or *other*."
)


# ---------------------------------------------------------------------------
# Input parsing helpers
# ---------------------------------------------------------------------------

def _parse_button_payload(payload: str, expected_prefix: str) -> Optional[str]:
    """Parse a structured ButtonPayload value."""
    if not payload:
        return None
    payload = payload.strip()
    if ":" not in payload:
        return None
    prefix, _, value = payload.partition(":")
    if prefix.strip() == expected_prefix and value.strip():
        return value.strip()
    return None


def _parse_project_type(text: str) -> Optional[str]:
    """Parse project type from user text."""
    text = text.strip().lower()
    # Direct matches
    if text in ("business", "biz", "b", "1"):
        return "business"
    if text in ("education", "edu", "e", "2", "student", "study"):
        return "education"
    # Substring matches
    if "business" in text or "shop" in text or "farm" in text or "work" in text:
        return "business"
    if "education" in text or "study" in text or "course" in text or "college" in text:
        return "education"
    return None


def _parse_currency(text: str) -> Optional[float]:
    """Parse an Indian currency amount from user text."""
    text = text.strip().replace("₹", "").replace(",", "").strip()

    match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:lakh|lac|l)\b', text, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 100_000

    match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:crore|cr)\b', text, re.IGNORECASE)
    if match:
        return float(match.group(1)) * 10_000_000

    match = re.match(r'^(\d+(?:\.\d+)?)\s*$', text)
    if match:
        return float(match.group(1))

    return None


def _parse_gender(text: str) -> Optional[str]:
    """Parse gender from user text."""
    text = text.strip().lower()
    if text in ("male", "man", "m", "1", "purush"):
        return "male"
    if text in ("female", "woman", "f", "w", "2", "mahila", "stri"):
        return "female"
    if text in ("other", "o", "3"):
        return "other"
    return None


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

async def check_consent(state: ConversationState) -> ConversationState:
    """Check if user has given consent (replied START)."""
    message = state.get("message", "").strip().upper()
    consent_given = state.get("consent_given", False)

    if not consent_given:
        if message == "START":
            return {
                **state,
                "consent_given": True,
                "message_count": 0,
                "response": "",
                "response_content_sid": "",
                "intake_step": "",
                "project_type": "",
                "project_cost": 0.0,
                "annual_income": 0.0,
                "gender": "",
                "button_payload": "",
            }
        else:
            return {
                **state,
                "consent_given": False,
                "response": CONSENT_NOTICE,
            }
    else:
        if message == "STOP":
            return {
                **state,
                "consent_given": False,
                "message_count": 0,
                "response": STOP_NOTICE,
                "response_content_sid": "",
                "intake_step": "",
                "project_type": "",
                "project_cost": 0.0,
                "annual_income": 0.0,
                "gender": "",
                "button_payload": "",
            }
        return {**state, "response": "", "response_content_sid": ""}


async def route_after_consent(state: ConversationState) -> Literal["process_intake", "__end__"]:
    """Route based on consent status."""
    if state.get("response"):
        return END
    return "process_intake"

def process_message(state: ConversationState) -> ConversationState:
    """Process message with state proof.

    Phase 0: Echo the message with count to prove state persistence.
    KEPT for backward compatibility with Phase 0 tests — no longer used
    in the graph, which routes to process_intake instead.
    """
    message = state.get("message", "")
    count = state.get("message_count", 0) + 1

    # Phase 0: echo with state proof
    response = (
        f"✅ Message #{count} received: \"{message}\"\n\n"
        f"(State is working — I've tracked {count} message{'s' if count != 1 else ''} "
        f"from you across this conversation.)\n\n"
        f"Reply *STOP* anytime to end and clear your data."
    )

    return {
        **state,
        "message_count": count,
        "response": response,
    }

async def process_intake(state: ConversationState) -> ConversationState:
    """Handle the conversational intake flow for scheme matching."""
    message = state.get("message", "").strip()
    button_payload = state.get("button_payload", "")
    intake_step = state.get("intake_step", "")
    count = state.get("message_count", 0) + 1
    settings = get_settings()

    if message.upper() in ("START OVER", "NEW", "RESET", "RESTART"):
        content_sid = settings.content_sid_project_type if settings.use_button_messages else ""
        return {
            **state,
            "message_count": count,
            "intake_step": "",
            "project_type": "",
            "project_cost": 0.0,
            "annual_income": 0.0,
            "gender": "",
            "button_payload": "",
            "response": "Starting over!\n\n" + PROMPT_PROJECT_TYPE,
            "response_content_sid": content_sid,
        }

    # Step 1
    if not intake_step:
        content_sid = settings.content_sid_project_type if settings.use_button_messages else ""
        return {
            **state,
            "message_count": count,
            "intake_step": "awaiting_project_type",
            "response": PROMPT_PROJECT_TYPE,
            "response_content_sid": content_sid,
            "button_payload": "",
        }

    # Step 2: Parse project type → ask cost
    if intake_step == "awaiting_project_type":
        project_type = _parse_button_payload(button_payload, "project_type")
        if project_type is None:
            project_type = _parse_project_type(message)
        if project_type is None:
            # Phase 3: LLM Extraction fallback
            project_type = await extract_project_type(message)
        
        if project_type is None:
            content_sid = settings.content_sid_project_type if settings.use_button_messages else ""
            return {
                **state,
                "message_count": count,
                "button_payload": "",
                "response": (
                    "Sorry, I didn't catch that. "
                    "Please reply *business* or *education*."
                ),
                "response_content_sid": content_sid,
            }
        type_label = "project" if project_type == "business" else "course/education"
        return {
            **state,
            "message_count": count,
            "project_type": project_type,
            "intake_step": "awaiting_cost",
            "button_payload": "",
            "response": PROMPT_PROJECT_COST.format(type_label=type_label),
            "response_content_sid": "",
        }

    # Step 3: Parse project cost → ask income
    if intake_step == "awaiting_cost":
        cost = _parse_currency(message)
        if cost is None or cost < 0:
            return {
                **state,
                "message_count": count,
                "response": (
                    "Sorry, I couldn't read that as an amount. "
                    "Please enter the cost in ₹ — like 140000, 1.4 lakh, or 50L."
                ),
            }
        return {
            **state,
            "message_count": count,
            "project_cost": cost,
            "intake_step": "awaiting_income",
            "response": PROMPT_ANNUAL_INCOME,
        }

    # Step 4: Parse income → ask gender
    if intake_step == "awaiting_income":
        income = _parse_currency(message)
        if income is None or income < 0:
            return {
                **state,
                "message_count": count,
                "response": (
                    "Sorry, I couldn't read that as an amount. "
                    "Please enter your family's annual income in ₹ — "
                    "like 300000, 3 lakh, or 5L."
                ),
                "response_content_sid": "",
            }
        content_sid = settings.content_sid_gender if settings.use_button_messages else ""
        return {
            **state,
            "message_count": count,
            "annual_income": income,
            "intake_step": "awaiting_gender",
            "response": PROMPT_GENDER,
            "response_content_sid": content_sid,
            "button_payload": "",
        }

    # Step 5: Parse gender → run eligibility + format results
    if intake_step == "awaiting_gender":
        gender = _parse_button_payload(button_payload, "gender")
        if gender is None:
            gender = _parse_gender(message)
        if gender is None:
            content_sid = settings.content_sid_gender if settings.use_button_messages else ""
            return {
                **state,
                "message_count": count,
                "button_payload": "",
                "response": (
                    "Sorry, I didn't catch that. "
                    "Please reply *male*, *female*, or *other*."
                ),
                "response_content_sid": content_sid,
            }

        profile = UserProfile(
            project_type=state.get("project_type", "business"),
            project_cost=state.get("project_cost", 0.0),
            annual_income=state.get("annual_income", 0.0),
            gender=gender,
        )
        eligibility = evaluate_eligibility(profile)
        matches = eligibility.matches
        language = "en"  # Future: read from state if multi-lingual
        
        fingerprint = generate_fingerprint(matches)
        
        db = await get_connection()
        try:
            template = await get_cached_template(db, fingerprint, language)
            if not template:
                template = await generate_recommendation_template(matches, language)
                scheme_id = matches[0].scheme_id if matches else "NO_MATCH"
                await set_cached_template(db, fingerprint, language, scheme_id, template)
        finally:
            await db.close()
            
        # Format results using the template and the user's specific math
        response = format_recommendation(template, profile, matches)

        if matches:
            response += "\n\n" + _format_outcome(profile, eligibility, gender)
        elif eligibility.category_note:
            # No Dead Ends — hand an out-of-category user to the right
            # corporation rather than leaving them at a wall.
            response += "\n\n" + eligibility.category_note

        return {
            **state,
            "message_count": count,
            "gender": gender,
            "intake_step": "done",
            "button_payload": "",
            "response": response,
            "response_content_sid": "",
        }

    # Step 6
    if intake_step == "done":
        return {
            **state,
            "message_count": count,
            "response": (
                "Would you like to check eligibility for a different project?\n\n"
                "Reply *START OVER* to begin a new search, or *STOP* to end."
            ),
        }

    logger.warning(f"Unknown intake_step: {intake_step}")
    return {
        **state,
        "message_count": count,
        "intake_step": "",
        "response": (
            "I seem to have lost track — let's start fresh.\n\n"
            + PROMPT_PROJECT_TYPE
        ),
    }


def _price(match: SchemeMatch, profile: UserProfile, gender: str):
    """Price one scheme on ITS OWN published terms.

    The previous version used settings.default_tenure_months (84) and
    default_moratorium_months (6) for every scheme, and produced a MONTHLY
    instalment. Both are wrong now the corpus is real: Micro Finance runs 36
    months with a 3-month grace, Udyam Nidhi 60, the Educational Loan 144 — and
    every NSFDC scheme repays QUARTERLY, so a monthly EMI is a number the
    borrower is never actually asked for.
    """
    return calculate_emi(
        project_cost=profile.project_cost,
        financing_pct=match.financing_pct,
        rate_annual=match.rate_min,
        tenure_months=match.tenure_months,
        moratorium_months=match.moratorium_months,
        moratorium_type=MoratoriumType.SIMPLE_INTEREST,
        women_rebate_pct=match.women_rebate_pct,
        is_female=(gender == "female"),
        periods_per_year=match.periods_per_year,
    )


def _format_outcome(profile: UserProfile, eligibility, gender: str) -> str:
    """Compose the reply from the same blocks the web portal uses.

    Everything here is deterministic (src/literacy.py) — no model. The LLM still
    writes the scheme intro above, cached per outcome fingerprint, but no rupee
    figure a borrower sees is generated, so none can be hallucinated.

    Schemes are ordered by what they actually cost, cheapest first: a person can
    qualify for Micro Finance at 6.5% and Aajeevika at 15% on the same project,
    and nobody tells them.
    """
    priced = [(m, _price(m, profile, gender)) for m in eligibility.matches]
    priced.sort(key=lambda pair: pair[1].total_interest)

    best_match, best_emi = priced[0]
    parts: list[str] = []

    if len(priced) > 1:
        parts.append("*Cheapest for you: " + best_match.name + "*")

    parts.append(format_instalment(best_emi))
    parts.append(format_true_cost(best_emi))

    strip = format_moratorium_strip(best_emi)
    if strip:
        parts.append(strip)

    parts.append(format_moneylender_comparison(best_emi))

    comparison = format_scheme_comparison(priced)
    if comparison:
        parts.append(comparison)

    why_not = format_why_not(eligibility)
    if why_not:
        parts.append(why_not)

    priority = format_priority_note(
        {"women": 0.40} if best_match.scheme_id in ("TERM_LOAN", "MICRO_FINANCE") else None,
        gender,
    )
    if priority:
        parts.append(priority)

    parts.append(format_fraud_shield())
    parts.append(
        "_These are estimates — final terms are set by your Channel Partner._" + "\n"
        + "Reply *START OVER* for different details, or *STOP* to end."
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Build and compile the LangGraph conversation graph."""
    graph = StateGraph(ConversationState)

    graph.add_node("check_consent", check_consent)
    graph.add_node("process_intake", process_intake)

    graph.set_entry_point("check_consent")

    graph.add_conditional_edges(
        "check_consent",
        route_after_consent,
        {
            "process_intake": "process_intake",
            END: END,
        },
    )

    graph.add_edge("process_intake", END)
    return graph

