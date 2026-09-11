# prompt.md — Paste this to start (or resume) a build session

You're helping build the backend for a Smart India Hackathon 2026 project: PS26092, an AI-driven scheme-matching platform for NSFDC (National Scheduled Castes Finance and Development Corporation) credit schemes, delivered primarily over WhatsApp. This extends an existing project called GrantBot (LangGraph + Gemini + WhatsApp via Twilio), not a fresh build.

**Read these files first, in this order, before writing any code:**
1. `memory.md` — current status. What's done, what's in progress, what's next. Start here every session.
2. `architecture.md` — the technical spec. This is your primary reference for how things fit together.
3. `rules.md` — scheme numbers and eligibility logic. Treat every figure's CONFIDENCE marker as real — don't upgrade a "PS-stated, unresolved" number to something more precise on your own.
4. `phrases.md` — the actual bot copy to use. Don't write new copy from scratch; use or adapt what's there.

## Ground rules
- **The eligibility decision is deterministic, never LLM-based.** Tier 1 in architecture.md is a plain rules table. If you're tempted to have an LLM "figure out" whether someone qualifies for a scheme, stop — that's the one thing this design deliberately keeps out of the model's hands, on purpose, because it needs to be 100% correct on boundary cases every time.
- **Reliability over features.** This project failed once already on WhatsApp specifically because of state-management and synchronous-webhook bugs (see architecture.md's "Non-negotiables" section). Getting the webhook→queue→worker skeleton rock-solid, with idempotency and atomic state, is a harder requirement than any single feature. Don't move on to Tier 1/2/3 until step 1 of the message chain is provably solid — send two rapid messages, get two correct responses, no state confusion.
- **Free and open-source only.** No paid APIs, no paid infra. SQLite, Gemini's free tier, OpenRouter's free models, IndicTrans2 self-hosted or via a free HF Space — that's the budget, and it's not a soft constraint.
- **Config over hardcoding.** Every number in rules.md goes in a config module, not inline in logic. This isn't stylistic — those numbers are still being verified and will change.
- **If you think there's a better approach than what's in architecture.md, say so explicitly before implementing it — don't just silently deviate.** State what you'd change, why, and what tradeoff it costs, then wait for a go-ahead on anything that changes the core pipeline shape (the three-tier split, the webhook decoupling, the checkpointer-based state). Smaller implementation choices (exact library, code structure) don't need sign-off — use your judgment.
- **Don't invent scheme numbers, API rate limits, or regulatory specifics you're not confident about.** If you need a current figure (Gemini's live rate limit, an exact NSFDC number) and can search the web, do — and say what you found and how confident you are, the same way this doc does. If you can't verify something, flag it as unverified rather than stating it plainly. This project has already been burned twice by confident-sounding fabricated statistics in research docs; don't add a third instance.
- **Update memory.md at the end of every session** — what got built, what's tested and working, what's next, anything you got stuck on. The next session (possibly a different model, per the Opus→Gemini fallback) depends on this being accurate, not aspirational.

## What "done" looks like for a session
Don't call something finished because the code compiles. Test it the way it'll actually be used: send a real WhatsApp message (or a realistic simulated one) through the whole path you just built, including a deliberately weird input (a boundary-value income, a message sent mid-Flow, two messages sent back to back) — and confirm state doesn't break. That's the actual bar this project is trying to clear, per its own failure history.
