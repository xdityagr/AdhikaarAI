"""
LLM integration module (Phase 3).

Handles all interactions with Gemini (via LangChain), keeping the graph logic clean.
- extract_project_type: Tier 2 extraction using Flash-Lite.
- generate_recommendation_template: Generation using Flash on a cache miss.
- format_recommendation: Deterministic substitution of the generated template.
"""

import logging
from typing import Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from src.config import get_settings
from src.schemes import SchemeMatch, UserProfile, format_rupees

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier 2 Extraction
# ---------------------------------------------------------------------------

class ExtractionResult(BaseModel):
    project_type: Optional[str] = Field(
        description="Must be exactly 'business', 'education', or None if completely unrelated."
    )


async def extract_project_type(text: str) -> Optional[str]:
    """
    Classify free-text into a structured project_type using Gemini Flash-Lite.
    Returns 'business', 'education', or None if it cannot be determined.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        logger.warning("No GEMINI_API_KEY configured. Skipping extraction.")
        return None

    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model_extraction,
            api_key=settings.gemini_api_key,
            temperature=0.0
        )
        
        # Using structured output guarantees we get the schema we want
        structured_llm = llm.with_structured_output(ExtractionResult)
        
        prompt = (
            "You are helping classify a user's project into an NSFDC scheme category.\n"
            "Given the user's free text input describing what they want to do, classify it as either "
            "'business' (e.g., tailoring shop, dairy farming, small workshop) or "
            "'education' (e.g., studying abroad, college course).\n"
            "If it is completely unrelated to taking a loan for business or education, return None.\n\n"
            f"User input: {text}"
        )
        
        result: ExtractionResult = await structured_llm.ainvoke(prompt)
        if result.project_type in ("business", "education"):
            return result.project_type
        return None
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

async def generate_recommendation_template(matches: list[SchemeMatch], language: str = "en") -> str:
    """
    Generate a response template for the given scheme matches and language using Gemini Flash.
    CRITICAL: This generates a template with placeholders (e.g. {project_cost}, {rate}),
    NOT a final string. This ensures caching is safe across users.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        logger.warning("No GEMINI_API_KEY configured. Falling back to static templates.")
        # Fallback to static English if no key
        if not matches:
            return "Based on what you shared, I couldn't find an exact match among the schemes I currently cover. Would you like me to share what I do cover, or connect you to a human contact?"
        match = matches[0]
        if match.scheme_id == "MICRO_FINANCE":
            return "Based on what you shared, you're likely eligible for the *Micro Finance Scheme* — for projects up to ₹1.40 lakh. NSFDC can finance up to 90% of your ₹{project_cost} project. Estimated rate: {rate}% per year, with a {moratorium} month grace period before repayments start. Here's what it costs and where to go."
        elif match.scheme_id == "TERM_LOAN":
            return "Based on what you shared, you're likely eligible for a *Term Loan* — for larger projects up to ₹50 lakh. Estimated rate: {rate}% per year on ₹{project_cost}, moratorium {moratorium} months. Here's what it costs and where to go."
        elif match.scheme_id == "EDUCATIONAL_LOAN":
            return "Based on what you shared, you're likely eligible for the *Educational Loan Scheme* for your course. NSFDC can cover up to 90% of the cost. {women_rebate_note} Here's what it costs and where to go."
        elif match.scheme_id == "AAJEEVIKA_MICRO_FINANCE":
            return ("Based on what you shared, you're likely eligible for the "
                    "*Aajeevika Micro-Finance Yojana* — for projects up to ₹1.40 lakh, "
                    "through an NBFC-MFI. Estimated rate: {rate}% per year on ₹{project_cost}, "
                    "with a {moratorium} month grace period. Here's what it costs and where to go.")
        elif match.scheme_id == "UDYAM_NIDHI":
            return ("Based on what you shared, you're likely eligible for the "
                    "*Udyam Nidhi Yojana* — for projects up to ₹5 lakh. Estimated rate: "
                    "{rate}% per year on ₹{project_cost}, with a {moratorium} month grace "
                    "period. Here's what it costs and where to go.")
        return ("Based on what you shared, you're likely eligible for {scheme_name}. "
                "Estimated rate: {rate}% per year on ₹{project_cost}. "
                "Here's what it costs and where to go.")

    try:
        llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model_generation,
            api_key=settings.gemini_api_key,
            temperature=0.3
        )
        
        if not matches:
            prompt = (
                f"Translate the following response template to {language}. "
                "Do NOT change any text inside curly braces like {{placeholder}}. "
                "Keep it conversational and short (WhatsApp style):\n\n"
                "Based on what you shared, I couldn't find an exact match among the schemes I currently cover. "
                "This doesn't necessarily mean you're not eligible for something else — would you like me to share what I do cover, or connect you to a human contact?"
            )
        else:
            match = matches[0]
            if match.scheme_id == "MICRO_FINANCE":
                base = "Based on what you shared, you're likely eligible for the *Micro Finance Scheme* — for projects up to ₹1.40 lakh. NSFDC can finance up to 90% of your ₹{project_cost} project. Estimated rate: {rate}% per year, with a {moratorium} month grace period before repayments start. Here's what it costs and where to go."
            elif match.scheme_id == "TERM_LOAN":
                base = "Based on what you shared, you're likely eligible for a *Term Loan* — for larger projects up to ₹50 lakh. Estimated rate: {rate}% per year on ₹{project_cost}, moratorium {moratorium} months. Here's what it costs and where to go."
            elif match.scheme_id == "EDUCATIONAL_LOAN":
                base = "Based on what you shared, you're likely eligible for the *Educational Loan Scheme* for your course. NSFDC can cover up to 90% of the cost. {women_rebate_note} Here's what it costs and where to go."
            else:
                base = "You are eligible for {scheme_name}. Estimated rate: {rate}% per year, with a {moratorium} month grace period. Here's what it costs and where to go."
            
            prompt = (
                f"Translate the following response template to {language}. "
                "Do NOT change any text inside curly braces like {{project_cost}} or {{rate}}. "
                "Keep the formatting (like bolding) intact. "
                "Keep it conversational and short (WhatsApp style):\n\n"
                f"{base}"
            )
            
        result = await llm.ainvoke(prompt)
        return result.content.strip()
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        # Return fallback on error
        return "I'm having connection trouble right now — please try again in a minute."


def format_recommendation(template: str, profile: UserProfile, matches: list[SchemeMatch]) -> str:
    """
    Pure string formatting step. Fills placeholders in the LLM-generated (or cached)
    template using this user's specific Tier 1 numbers.
    """
    if not matches:
        return template

    match = matches[0]
    women_rebate_note = ""
    if match.women_rebate_pct > 0 and profile.gender == "female":
        women_rebate_note = f"Since you are a female applicant, a {match.women_rebate_pct}% interest rebate applies. "

    # Every number here must agree with the deterministic block rendered under
    # it. Before this, the intro quoted the GLOBAL 6-month default while the
    # block below said 3, and quoted rate_max while the EMI used rate_min — so a
    # single message contradicted itself twice.
    effective_rate = match.rate_min
    if match.women_rebate_pct > 0 and profile.gender == "female":
        effective_rate = max(0.0, effective_rate - match.women_rebate_pct)

    return template.format(
        project_cost=format_rupees(profile.project_cost).lstrip("₹"),
        rate=round(effective_rate, 2),
        moratorium=match.moratorium_months,
        women_rebate_note=women_rebate_note,
        scheme_name=match.name,
    )
