"""
Application entry point — FastAPI app with lifecycle management.

Startup:
  1. Initialize database (create tables if needed)
  2. Create the message queue
  3. Start the message worker (which initializes LangGraph + checkpointer)
  4. Mount the webhook router

Shutdown:
  1. Drain the message queue
  2. Stop worker tasks
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import re
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from src.config import get_settings
from src.database import init_database
from src import whatsapp_consent as consent
from src.api import router as api_router
from src.operator_api import router as operator_router
from src.webhook import router as webhook_router, set_message_queue
from src.voice import router as voice_router
from src.worker import MessageWorker

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

_worker: MessageWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    # A mounted volume starts empty and SQLite will not create a missing
    # parent — the first write would fail with "unable to open database
    # file", which says nothing about a directory.
    from src.paths import ensure_state_dirs
    ensure_state_dirs()

    global _worker

    settings = get_settings()
    logger.info("Starting Yojna Setu backend...")
    logger.info("Database: %s", settings.database_path)
    logger.info("Webhook URL: %s/webhook/whatsapp", settings.webhook_base_url)
    logger.info(
        "Signature verification: %s",
        "ENABLED" if settings.webhook_verify_signatures else "DISABLED",
    )

    # 1. Initialize database
    await init_database()

    # 1a. Read the opt-out list into memory before a single message is handled.
    # The webhook starts accepting as soon as this function returns, so loading
    # it later would leave a window in which somebody who sent STOP last week
    # gets answered — which is exactly the failure the table was added to end.
    await consent.load()

    # 2. Create the message queue
    message_queue = asyncio.Queue()

    # 3. Inject queue into webhook module
    set_message_queue(message_queue)

    # 4. Start the worker
    _worker = MessageWorker(queue=message_queue)
    await _worker.start()

    logger.info("Yojna Setu backend ready — listening for WhatsApp messages")

    yield  # App is running

    # Shutdown
    logger.info("Shutting down Yojna Setu backend...")
    if _worker:
        await _worker.stop()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Yojna Setu",
    description="Scheme discovery for India — every central and state welfare, scholarship, pension and credit scheme, matched deterministically against published eligibility rules.",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount routes
app.include_router(webhook_router)
app.include_router(api_router)
# The only guarded routes in this API. Everything above is anonymous by
# design; this one is a view of other people's applications.
app.include_router(operator_router)
app.include_router(voice_router)


# ---------------------------------------------------------------------------
# Cross-origin access, for the one route that cannot go through the proxy
# ---------------------------------------------------------------------------
#
# Everything else reaches this service through the front end's rewrite, so the
# browser sees a single origin and there is no CORS to configure. The assistant
# stream is the exception: a turn takes about twenty seconds and Vercel's Hobby
# plan cuts a response at ten, so the trace arrives, the answer never does, and
# the conversation appears to stop mid-thought.
#
# So the browser is allowed to talk to this service directly for that route.
# Named origins only — never "*" — and no credentials, because none are used.
_origins = [
    o.strip() for o in os.environ.get("YOJNASETU_ALLOWED_ORIGINS", "").split(",")
    if o.strip()
]
if _origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    logger.info("Cross-origin requests allowed from: %s", ", ".join(_origins))


def _commit() -> str:
    """The commit this process was built from, or "unknown" off a platform."""
    import os
    import subprocess

    sha = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT")
    if not sha:
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=2,
            ).stdout.strip()
        except Exception:
            sha = ""
    return sha[:7] or "unknown"


@app.get("/health")
async def health_check():
    """Health check — 200 when the server is up, and where its data is.

    The paths are here because the commonest way a container deployment goes
    wrong is a disk mounted somewhere other than where the app looks, and that
    is invisible until something tries to read the corpus or write an opt-out.
    Reporting them turns a mystifying 500 into one glance.

    Also what Render's health check hits, and what an external ping should hit
    to keep a free instance from spinning down — see DEPLOY.md.
    """
    from src import paths

    where = paths.describe()
    return {
        "status": "ok" if where["catalogue_present"] == "True" else "degraded",
        "service": "yojnasetu",
        "catalogue": {
            "found": where["catalogue_present"] == "True",
            "size_mb": where["catalogue_mb"],
            "dir": where["catalogue_dir"],
        },
        "state_dir": where["state_dir"],
        # Which code is actually running.
        #
        # "Did the fix deploy?" was answered all day by probing for a route
        # that only exists in the newer build — a guess dressed as a check.
        # Render sets RENDER_GIT_COMMIT on every build, so the answer is just
        # sitting there.
        "commit": _commit(),
    }


ASSET_NAME_RE = re.compile(r"^[a-z0-9_-]+\.(css|js)$")
ASSET_TYPES = {".css": "text/css", ".js": "text/javascript"}


@app.get("/", response_class=HTMLResponse)
async def landing():
    """Landing page.

    Served from this same app rather than a separate frontend build: one process,
    one deploy, no Node toolchain, and nothing extra to go wrong on demo day.
    (The partner console proper is planned as a separate Next.js app.) No
    webfonts either — the site has to work offline, for the same reason map tiles
    are cached locally.
    """
    return FileResponse(WEB_DIR / "landing.html", media_type="text/html")


@app.get("/app", response_class=HTMLResponse)
async def portal():
    """The scheme finder itself."""
    return FileResponse(WEB_DIR / "app.html", media_type="text/html")


@app.get("/assets/{filename}")
async def get_asset(filename: str):
    """Serve the shared stylesheet and custom-element definitions.

    A named allowlist pattern rather than a StaticFiles mount — same reasoning as
    /media below: one narrow route is easier to reason about than a directory
    served wholesale.
    """
    if not ASSET_NAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="Not found")
    path = (WEB_DIR / filename).resolve()
    if not path.is_file() or WEB_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type=ASSET_TYPES[path.suffix])


@app.get("/api-info")
async def api_info():
    """What this service is, for anything that pings the old root route."""
    return {
        "name": "Yojna Setu",
        "description": "Scheme discovery for India — every central and state welfare, scholarship, pension and credit scheme, matched deterministically against published eligibility rules.",
        "landing": "/",
        "portal": "/app",
        "health": "/health",
        "webhook": "/webhook/whatsapp",
        "api": ["/api/recommend", "/api/schemes", "/api/partners"],
    }


# ---------------------------------------------------------------------------
# Rendered partner maps
#
# Twilio fetches media_url from the public internet, so a map has to be served on
# a URL with no auth in front of it. That map encodes a beneficiary's approximate
# location, which is personal data under DPDP — so this is ONE narrow route with
# a strict filename pattern, not a StaticFiles mount over a directory. Filenames
# are unguessable tokens and old files are swept.
# ---------------------------------------------------------------------------

WEB_DIR = Path(__file__).resolve().parent / "web"
from src.paths import MEDIA_DIR
MEDIA_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{22}\.png$")
MEDIA_TTL_SECONDS = 3600


def _sweep_media(ttl_seconds: int = MEDIA_TTL_SECONDS) -> int:
    """Delete rendered maps older than the TTL. Twilio caches what it fetches."""
    if not MEDIA_DIR.exists():
        return 0
    cutoff = time.time() - ttl_seconds
    removed = 0
    for path in MEDIA_DIR.glob("*.png"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            pass
    return removed


@app.get("/media/{filename}")
async def get_media(filename: str):
    """Serve a rendered map. Rejects anything not matching the token pattern."""
    if not MEDIA_NAME_RE.match(filename):
        raise HTTPException(status_code=404, detail="Not found")

    path = MEDIA_DIR / filename
    # Resolve and confirm containment — belt and braces against traversal.
    try:
        resolved = path.resolve()
        if not resolved.is_file() or MEDIA_DIR.resolve() not in resolved.parents:
            raise HTTPException(status_code=404, detail="Not found")
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")

    _sweep_media()
    return FileResponse(resolved, media_type="image/png")
