"""
Configuration module — loads all settings from environment variables.

Every number from rules.md, every credential, every toggle lives here.
Nothing is hardcoded in logic modules. This is the one file you change
when a verified NSFDC number comes back from the SPOC meeting.
"""

from __future__ import annotations

from pathlib import Path

from functools import lru_cache

from pydantic_settings import BaseSettings

from src.corpus import legacy_schemes_dict
from pydantic import Field


def _default_state_db() -> "Path":
    """Resolved late so YOJNASETU_STATE_DIR is read at import, not at build.

    Imported inside the function because `src.paths` must not depend on the
    settings and the settings must not depend on the paths at module scope.
    """
    from src.paths import STATE_DB
    return STATE_DB


class Settings(BaseSettings):
    """Application settings, loaded from .env file and environment variables."""

    # --- Twilio ---
    twilio_account_sid: str = Field(default="", description="Twilio Account SID")
    twilio_auth_token: str = Field(default="", description="Twilio Auth Token")
    twilio_whatsapp_number: str = Field(
        default="whatsapp:+14155238886",
        description="Twilio WhatsApp sender number (Sandbox default)",
    )

    # --- Webhook ---
    # ---- WhatsApp via Meta's Cloud API -----------------------------------
    #
    # Talking to Meta directly rather than through Twilio: one less party
    # between a person's message and the answer, one less bill, and the
    # sandbox-number restriction goes away. Everything below comes from the
    # app's dashboard except the verify token, which we invent and then tell
    # Meta about.
    whatsapp_provider: str = Field(
        default="meta",
        description="'meta' (Cloud API) or 'twilio' (legacy)",
    )
    whatsapp_access_token: str = Field(
        default="",
        description="Meta access token — the dashboard's temporary one expires in 24h",
    )
    whatsapp_sat: str = Field(
        default="",
        description="System User Access Token — never expires; preferred over the above",
    )
    whatsapp_phone_number_id: str = Field(
        default="",
        description="Phone Number ID from the WhatsApp app dashboard (not the number)",
    )
    whatsapp_verify_token: str = Field(
        default="",
        description="A string we choose; Meta echoes it when registering the webhook",
    )
    whatsapp_app_secret: str = Field(
        default="",
        description="App Secret, used to verify X-Hub-Signature-256 on every payload",
    )
    whatsapp_api_version: str = Field(
        default="v21.0",
        description="Graph API version",
    )

    @property
    def whatsapp_token(self) -> str:
        """The token to send with, preferring the one that does not expire.

        The token the dashboard shows on the API Setup page lasts 24 hours. It
        is the obvious one to copy and the reason a WhatsApp integration works
        on the day it is built and returns 401 the next morning — which, on a
        demo day, is indistinguishable from the whole thing being broken. A
        System User Access Token has no expiry, so it wins whenever it is set.
        """
        return self.whatsapp_sat or self.whatsapp_access_token

    webhook_base_url: str = Field(
        default="http://localhost:8000",
        description="Public base URL for webhook (ngrok/cloudflare tunnel)",
    )
    webhook_verify_signatures: bool = Field(
        default=True,
        description="Verify Twilio HMAC-SHA1 signatures. Disable only for local testing.",
    )

    # --- Database ---
    #
    # State, not corpus. Tiny, written to, and it has to survive a deploy —
    # which on a container means it must sit on a mounted disk rather than in
    # the image. `YOJNASETU_STATE_DIR` moves it without a code change; see
    # `src.paths` for why the corpus is kept somewhere else entirely.
    database_path: str = Field(
        default_factory=lambda: str(_default_state_db()),
        description="SQLite file holding state that must outlive a restart",
    )

    # --- Rate limiting ---
    max_messages_per_user_per_minute: int = Field(
        default=10,
        description="Per-user message rate limit (protects against message loops)",
    )

    # --- Worker ---
    worker_count: int = Field(
        default=3,
        description="Number of concurrent worker tasks consuming the message queue",
    )

    # --- Loan defaults (from NSFDC direct verification against nsfdc.nic.in) ---
    default_tenure_months: int = Field(
        default=84,
        description="Default loan tenure in months (7 years)",
    )
    default_moratorium_months: int = Field(
        default=6,
        description="Default moratorium period in months",
    )

    # --- Content Templates (Phase 2 — quick-reply buttons) ---
    content_sid_project_type: str = Field(
        default="",
        description="Twilio Content SID for project type buttons (HXxxxx...)",
    )
    content_sid_gender: str = Field(
        default="",
        description="Twilio Content SID for gender buttons (HXxxxx...)",
    )
    use_button_messages: bool = Field(
        default=False,
        description="Send button messages when Content SIDs are configured. False = text-only mode.",
    )

    # --- LLM Settings (Phase 3) ---
    gemini_api_key: str = Field(default="", description="Gemini API Key")
    gemini_model_extraction: str = Field(
        default="gemini-3.5-flash-lite",
        description="Model for Tier 2 extraction (higher free tier limit)"
    )
    gemini_model_generation: str = Field(
        default="gemini-3.8-flash",
        description="Model for generation on cache miss"
    )

    # --- Inbound voice (Phase C) ---
    #
    # The number people ring. Inbound only — nobody is called unprompted — so
    # there is no outbound credential here and that absence is deliberate.
    vapi_api_key: str = Field(
        default="",
        description="Vapi private API key, for managing the assistant and number",
    )
    vapi_webhook_secret: str = Field(
        default="",
        description="A string we choose and paste into Vapi's credential config. "
                    "Every /api/voice/* request is checked against it.",
    )
    vapi_phone_number_id: str = Field(
        default="",
        description="Vapi's id for the provisioned inbound number (not the number)",
    )
    vapi_signature_header: str = Field(
        default="x-vapi-signature",
        description="Header carrying the HMAC-SHA256 of the raw body, when the "
                    "credential is configured for HMAC rather than a bearer token",
    )
    vapi_timestamp_header: str = Field(
        default="x-vapi-signature-timestamp",
        description="Optional header signed alongside the body for replay protection",
    )
    voice_verify_signatures: bool = Field(
        default=True,
        description="Verify every voice webhook. Disable only for local testing — "
                    "these routes run the matching engine.",
    )

    sarvam_api_key: str = Field(
        default="",
        description="Sarvam AI — primary speech-to-text, built for Indian languages",
    )
    deepgram_api_key: str = Field(
        default="",
        description="Deepgram — fallback speech-to-text, and the only one that "
                    "handles Assamese and Urdu",
    )

    # --- Financial literacy (PS impact goal: "enhance financial literacy") ---
    moneylender_monthly_rate_pct: float = Field(
        default=5.0,
        description=(
            "Informal moneylender rate, % PER MONTH, used for the comparison that "
            "shows what a concessional loan is actually worth. Rates of 3-10%/month "
            "are typical. A config value, not a literal, because the honest answer "
            "to 'where did that number come from' is 'it's an assumption you can change'."
        ),
    )

    model_config = {
        # Both locations are read, project root last so it wins on a clash.
        # `src/.env` sits next to the code and is the one people reach for
        # first; silently ignoring it means a key that looks configured but
        # isn't, which is a miserable thing to debug.
        "env_file": ("src/.env", ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        # An unrecognised key in .env must never take the whole app down. It
        # did once: a teammate added DEEPGRAM_API_KEY and every request started
        # failing on a validation error about an environment variable, which is
        # a spectacularly unhelpful way to learn that a config file changed.
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton. Call this from anywhere."""
    return Settings()


# ---------------------------------------------------------------------------
# Scheme configuration — DERIVED FROM THE CORPUS. Do not edit here.
#
# This used to be a literal dict of three schemes. It is now a view over
# corpus/v1/schemes.json, which holds all five schemes NSFDC actually publishes
# along with per-field provenance (source URL, fetch date, confidence).
#
# To change a scheme number, edit the corpus JSON — not this file. That keeps a
# rate change reviewable as a diff, which is the whole point: docs/rules.md
# spent five research passes on numbers that had in fact already converged,
# because there was no single place where a number and its source lived together.
#
# NO AGE FIELD, still — but the reason has been upgraded. It used to be "no age
# boundary has been confirmed". nsfdc.nic.in/eligibility-requirements states no
# age condition at all, so its absence is now CONFIRMED, not merely unverified.
# ---------------------------------------------------------------------------

SCHEMES = legacy_schemes_dict()

# ---------------------------------------------------------------------------
# Prudential norms — Tier 3
# CONFIDENCE: high, corroborated across every source
# ---------------------------------------------------------------------------

PRUDENTIAL_NORMS = {
    "SCA": {
        "min_cumulative_utilization": 1.0,  # must be >= 100%
        "no_active_overdues": True,
    },
    "RRB": {
        "max_net_npa_percentage": 15.0,  # must be < 15%
    },
}
