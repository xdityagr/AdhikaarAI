# The Yojna Setu engine: FastAPI, the discovery corpus, WhatsApp and speech.
#
# The corpus is fetched at BUILD time, not at boot. On a free tier the service
# spins down when idle, so anything downloaded at startup is downloaded again
# on every cold start — and a WhatsApp webhook times out while it happens.
# Baked into the image it costs one slow build and nothing thereafter.

FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# curl for the corpus download; the rest are what Pillow and cryptography
# need to install without a compiler.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so editing source does not reinstall them.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------
# Published by scripts/publish_corpus.py. Pinned by tag so a deployment is
# reproducible — a corpus that changed silently underneath a running service
# would be very hard to notice from the outside.
ARG CORPUS_TAG=corpus-2026-09-08
ARG CORPUS_REPO=xdityagr/AdhikaarAI

RUN mkdir -p /catalogue \
 && echo "Fetching catalogue ${CORPUS_TAG} from ${CORPUS_REPO}…" \
 && curl -fSL --retry 3 --retry-delay 5 \
      "https://github.com/${CORPUS_REPO}/releases/download/${CORPUS_TAG}/schemes.db.gz" \
      -o /tmp/schemes.db.gz \
 && gunzip -c /tmp/schemes.db.gz > /catalogue/schemes.db \
 && rm /tmp/schemes.db.gz \
 && ls -lh /catalogue/schemes.db

COPY src ./src
COPY corpus ./corpus
COPY scripts ./scripts

# Read-only catalogue in the image; writable state on a mounted disk. Keeping
# them apart is what stops a deploy replacing the file someone's opt-out lives
# in.
#
# Deliberately NOT YOJNASETU_CORPUS_DIR. That name already belongs to the
# hand-curated NSFDC file at /app/corpus/v1/schemes.json — source, shipped with
# the code, a different thing entirely. Setting it here pointed that loader at
# /corpus and the container died on import before serving a single request.
ENV YOJNASETU_CATALOGUE_DIR=/catalogue \
    YOJNASETU_STATE_DIR=/data

RUN mkdir -p /data

EXPOSE 8000

# Render (and most hosts) inject $PORT. Defaulting keeps `docker run` working.
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
