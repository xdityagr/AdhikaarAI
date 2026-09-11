# Deploying Adhikaar AI

Front end on Vercel, engine on Render, and the corpus baked into the engine's
image. Roughly forty minutes end to end, most of it waiting for a Docker build.

```
  browser ──▶ Vercel (Next.js)
                 │  rewrite /api/* and /media/*   ← server-side, so the browser
                 ▼                                  only ever sees one origin
              Render (FastAPI)
                 ├── /catalogue/schemes.db  285 MB, read-only, baked into the image
                 └── /data                tiny, written to, must survive a deploy
```

The rewrite is the reason there is no CORS configuration anywhere in this
repository, and the reason the engine's URL never reaches client code.

---

## 1. The corpus

`data/schemes.db` is 283 MB and it is **not source**. It is a build artefact:
read-only at runtime, identical for every deployment, and rebuilt only by an
ingest that takes hours.

It is therefore neither committed nor downloaded at boot. Committing it exceeds
GitHub's 100 MB per-file limit and would add 283 MB to history on every
re-ingest. Downloading it at boot is worse: a free instance spins down when
idle, so every cold start would pay for it again — and a WhatsApp webhook times
out while it does.

It goes to a GitHub Release and the Dockerfile fetches it at **build** time.
Gzipped it is 42 MB.

```bash
python scripts/publish_corpus.py --tag corpus-2026-09-08
```

That prints a SHA-256. Put the tag in `render.yaml` under `dockerBuildArgs`.
Pin it — `corpus-latest` lets the data change underneath a running service with
nothing to show for it.

---

## 2. The engine, on Render

New → Blueprint → point it at this repository. `render.yaml` is picked up
automatically.

Then set the secrets in the dashboard (they are marked `sync: false`, so they
are never in git):

| Variable | Where it comes from |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio |
| `SARVAM_API_KEY` | Sarvam dashboard — primary speech |
| `DEEPGRAM_API_KEY` | Deepgram — Assamese and Urdu only |
| `WHATSAPP_SAT` | Meta system-user token. **Not** the API Setup one, which expires in 24h |
| `WHATSAPP_APP_SECRET` | App settings → Basic |
| `WHATSAPP_VERIFY_TOKEN` | Anything you choose; Meta echoes it back |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp → API Setup |
| `WEBHOOK_BASE_URL` | The `https://….onrender.com` URL, once it exists |

Check `/health` when it comes up. It reports where it looked for the corpus and
whether it found it — a disk mounted somewhere other than where the app looks
is the commonest way this fails, and it is invisible until something reads.

```json
{ "status": "ok", "catalogue": { "found": true, "size_mb": "285" } }
```

`"status": "degraded"` means the catalogue is missing. Check the `CORPUS_TAG`.

### Two things about the free plan that will bite

**It spins down after 15 minutes idle**, and the cold start takes about 50
seconds. Meta's webhook gives you far less than that, so the first WhatsApp
message after a quiet period is dropped. Meta retries, so nothing is lost — but
the reply arrives minutes late, which on a demo looks broken.

Fix it with an external ping every 10 minutes — cron-job.org or UptimeRobot,
both free — hitting `https://your-service.onrender.com/health`.

**The filesystem is ephemeral.** See below.

---

### A name that is already taken

`ADHIKAAR_CORPUS_DIR` belongs to `src/corpus/loader.py` and points at the
hand-curated NSFDC file, `corpus/v1/schemes.json` — source, shipped with the
code. The myScheme catalogue uses `ADHIKAAR_CATALOGUE_DIR`. Two different
things in this repository are called "the corpus"; setting the wrong one killed
the container on import, before it served a single request.

### Build arguments

There is no `dockerBuildArgs` field in a Blueprint — Render translates a Docker
service's **environment variables** into build arguments by itself, so
`CORPUS_TAG` and `CORPUS_REPO` are declared under `envVars` and reach the
Dockerfile's `ARG` instructions from there.

A consequence worth knowing: that translation applies to every variable,
secrets included. They are only baked into the image if the Dockerfile
*references* them with an `ARG`, and this one references exactly two — neither
of which is a secret. Do not add `ARG GEMINI_API_KEY` or similar.

The Dockerfile also carries the real tag as its `ARG` default, so `docker build`
with no arguments produces a working image.

---

## 3. The database

There are two kinds of data here and conflating them is the mistake to avoid.

|  | Corpus | State |
|---|---|---|
| What | 4,736 schemes, 50,793 translations, facets, FTS index | opt-outs, message idempotency, geocoding cache |
| Size | 283 MB | **76 KB** |
| Written at runtime | never | rarely |
| If lost | rebuild from the Release | someone who sent STOP is messaged again |

The corpus is solved above. The state is the real question, and it is 76 KB —
which is why the honest answer is "almost anything works".

**Recommended, and free: leave it as SQLite and accept the loss for now.**
`ADHIKAAR_STATE_DIR=/data` on the container's own filesystem. A redeploy
forgets it. For a demo on a Meta *test* number — five pre-registered
recipients — that is tolerable, and it costs nothing.

**Before real traffic, pick one:**

1. **Render disk** (`disk:` block in `render.yaml`, needs a paid instance from
   $7/mo). Zero code change; SQLite carries on exactly as it does locally.
   Simplest correct answer.
2. **Neon or Supabase Postgres** (free, and unlike Render's own free Postgres it
   does not expire after 30 days). Needs `src/database.py` ported off SQLite —
   a few hours, and the write surface is genuinely small.
3. **Turso** (libSQL — SQLite over the network, generous free tier). Between the
   two in effort.

### The part that is not merely inconvenient

Consent opt-outs live in `_OPTED_OUT`, a set **in memory** — not even in SQLite.
Along with WhatsApp conversation context and handoff codes:

```
src/whatsapp_consent.py   _OPTED_OUT     someone who sent STOP
src/whatsapp_brain.py     _HISTORY       recent turns
src/whatsapp_brain.py     _CONTEXT       what we learned about a number
src/handoff.py            _PENDING       website → WhatsApp codes
```

Losing a handoff code costs someone one repeated sentence. Losing an opt-out
means messaging a person who explicitly asked you to stop. **That one needs a
table before this touches real users** — it is a promise the product makes in
thirteen languages.

---

## 4. The front end, on Vercel

Import the repository, set the root directory to `web/`, and add one
environment variable:

```
ADHIKAAR_API_ORIGIN = https://adhikaar-api.onrender.com
```

`web/next.config.ts` already reads it. Nothing else needs configuring — no
CORS, no API URL in client code.

Also set `NEXT_PUBLIC_WHATSAPP_NUMBER` to the WhatsApp number in E.164, or the
QR panels render a "not configured yet" placeholder.

### The streaming route does not go through the proxy

An assistant turn takes about twenty seconds. Vercel's Hobby plan cuts a
response at ten, and the failure is quiet: the tool trace arrives, the answer
never does, and the conversation looks like it stopped mid-thought. Measured
against the deployed engine directly, the same turn completes in 19.4s.

So that one route goes straight from the browser to Render. Two settings:

```
# Vercel
NEXT_PUBLIC_ADHIKAAR_STREAM_ORIGIN = https://adhikaar-api.onrender.com

# Render
ADHIKAAR_ALLOWED_ORIGINS = https://your-project.vercel.app
```

Everything else still goes through the rewrite, so this is the only route with
any CORS at all — named origins, never `*`, and no credentials, because none
are used. Left unset locally, where the dev proxy has no such limit, the fetch
stays relative and nothing changes.

### One risk worth testing early

The assistant streams over Server-Sent Events and a turn can take 20–60
seconds. Vercel's Hobby plan caps serverless function duration at 10 seconds by
default. External rewrites are handled by the routing layer rather than as a
function, so streaming *should* pass through untouched — but confirm it on the
deployed site before demo day rather than on the day.

If it does get cut off, point the browser straight at Render for that one route
and add CORS for it. Everything else keeps going through the proxy.

---

## 5. WhatsApp, after deploying

Meta's callback URL has to move off ngrok and onto the Render URL:

```
https://adhikaar-api.onrender.com/webhook/whatsapp
```

App Dashboard → WhatsApp → Configuration → Edit. Verify token is whatever you
set for `WHATSAPP_VERIFY_TOKEN`. Subscribe the `messages` field, and confirm
the app is subscribed to the WABA — those are two separate steps and only the
first is obvious.

---

## Running it locally

```bash
pip install -r requirements-dev.txt      # runtime + ingest + tests
uvicorn src.main:app --port 8001 --reload
cd web && npm run dev
```

`requirements.txt` is the runtime alone — no pandas, no pdfplumber, no
selectolax. The API imports none of them, and together they are larger than
everything it does import.
