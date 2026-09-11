# WhatsApp message templates — what to submit, and why

A3 (change alerts) is blocked on this and on nothing else in our code.

Meta allows free-form messages only inside a **24-hour window that opens when
the person messages us**. Outside it, only a pre-approved template goes through.
`src/meta_whatsapp.py` sends `"type": "text"` and `"type": "image"` and nothing
else, so a cold send is rejected and `send()` returns False.

Two things have to happen, and they are independent:

1. **A template approved by Meta** — this document. Anyone with access to the
   WhatsApp Manager can do it; it does not need a developer.
2. **A `"type": "template"` send path in our code** — a small change, and
   pointless before a template name exists to send.

---

## Creating it

**WhatsApp Manager → Account Tools → Message Templates → Create template.**

Or via the Graph API, with a token carrying `whatsapp_business_management`:

```
POST https://graph.facebook.com/v21.0/{WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates
```

`WHATSAPP_BUSINESS_ACCOUNT_ID` is already in `src/.env`. `config.py` does not
read it yet — it reads `whatsapp_phone_number_id` but not the account id — so
the API route needs that one line added first.

---

## Template 1 — a scheme changed, or a new one appeared

**Name:** `scheme_update`
**Category:** `UTILITY`
**Language:** `en` first, then `hi`, `mr`, `bn`, `ta` (the ones with the most
users; the rest can follow)

**Body:**

```
Hello {{1}}, a government scheme you may qualify for has changed: {{2}}.

Reply SCHEME to see what it means for you, or STOP to get no more messages.
```

**Sample values for review** (Meta rejects a template whose variables have no
examples): `{{1}}` = `Sunita`, `{{2}}` = `Pradhan Mantri Awas Yojana – Urban`

### Why UTILITY and not MARKETING

UTILITY is for a message that follows from something the person did. These go
only to people who asked us about schemes and did not opt out, which is that
shape. **Expect Meta to push back anyway** — reviewers reclassify liberally, and
a scheme alert can read as promotional. If it is rejected or reclassified,
resubmit as MARKETING rather than rewording it into something misleading;
MARKETING costs more per message and requires the same opt-in we already have.

### Why STOP is in the body

Meta requires an opt-out path on MARKETING and it costs nothing to have it on
UTILITY. It also matches what `src/whatsapp_consent.py` already listens for, in
every script — so the instruction is true rather than decorative.

---

## Template 2 — a document is missing on a case (Phase B)

**Name:** `document_request`
**Category:** `UTILITY`

**Body:**

```
Hello {{1}}, {{2}} is helping with your application for {{3}} and needs one more paper: {{4}}.

Reply with a photo of it, or STOP to get no more messages.
```

`{{1}}` = `Sunita`, `{{2}}` = `Patna CSC`, `{{3}}` = `Pradhan Mantri Awas Yojana`,
`{{4}}` = `income certificate`

This one is squarely UTILITY: the person has a live application and an operator
is working on it. It is what `PRD-v3.md` §6.2 calls one-tap
request-a-missing-document, and it is the reason the partner console can chase a
paper without telephoning.

---

## What NOT to put in a template

- **No amount of money.** A figure in a push message that turns out to be wrong
  is the one mistake this product cannot make. The message says a scheme
  changed; the person opens the conversation and the engine computes the figure.
- **No Aadhaar number, account number or OTP**, in either direction.
- **No scheme name we invented.** `{{2}}` is filled from the corpus, in the
  language the government published it.

## Before anything is sent

`whatsapp_consent.is_loaded()` must be True and `has_opted_out` must be checked
for every recipient. An empty opt-out cache means "we have not looked", not
"nobody opted out", and acting on the second reading would message every person
who ever asked us to stop. That is the one data loss `render.yaml` calls not
merely inconvenient.

## Once a template is approved

Tell whoever is picking up A3: the name, the category it was approved under, and
the languages. The send path needs the name, and the alert job needs to know
which languages exist so it can fall back for a person whose language was not
approved.
