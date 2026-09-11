# phrases.md — Bot copy templates
English versions below are the source text to translate (via Gemini or the IndicTrans2 bridge, see architecture.md) and cache per language, per architecture.md's caching design. Keep every message short — this is WhatsApp, not a web page. `{placeholders}` are personalization slots filled at send time; everything else is cacheable as-is.

## 1. Opening message (sent on first contact — doubles as the DPDP consent notice)
> Namaste! I can help you find the right NSFDC loan or education scheme, estimate your EMI, and point you to your nearest eligible bank/agency. To do this, I'll ask for your project details, income, and category — used only to check scheme eligibility, not stored beyond this purpose. Reply START to continue.

*(Keep this itemized and specific — "used only to check scheme eligibility" — per Rule 3's itemized-purpose requirement, not a generic blanket line.)*

## 2. Language selection (buttons, not free text)
> Which language would you like to continue in?
Buttons: `English` · `हिंदी` · `More languages`
*(If "More languages": list message with remaining supported languages.)*

## 3. Intake — via WhatsApp Flow where possible; text fallback shown below
Field prompts (used as Flow field labels or, on the free-text fallback path, sequential questions):
- "What kind of work or business are you planning? (e.g. tailoring shop, dairy farming, small workshop)" — free text, feeds Tier 2
- "Roughly how much will it cost to set up? (in ₹)" — numeric
- "What's your family's approximate annual income? (in ₹)" — numeric
- "Are you applying for yourself as a business, or for education?" — buttons: `Business` · `Education`
- *(if Education)* "What course, and where — India or abroad?"

## 4. Per-scheme explanation templates (cache these per scheme × language, personalize only the bracketed parts)

**Micro Finance Scheme match:**
> Based on what you shared, you're likely eligible for the **Micro Finance Scheme** — for projects up to ₹1.40 lakh. NSFDC can finance up to 90% of your ₹{project_cost} project. Estimated rate: {rate}% per year, with a {moratorium} month grace period before repayments start. Want your estimated monthly payment, or the nearest place to apply?

**Term Loan match:**
> Based on what you shared, you're likely eligible for a **Term Loan** — for larger projects up to ₹50 lakh. Estimated rate: {rate}% per year on ₹{project_cost}, moratorium {moratorium} months. Want your estimated monthly payment, or the nearest place to apply?

**Educational Loan match:**
> Based on what you shared, you're likely eligible for the **Educational Loan Scheme** for your course. NSFDC can cover up to 90% of the cost. {women_rebate_note} Want your estimated monthly payment, or the nearest place to apply?

**No match:**
> Based on what you shared, I couldn't find an exact match among the schemes I currently cover. This doesn't necessarily mean you're not eligible for something else — would you like me to share what I do cover, or connect you to a human contact?

*(The "no match" path matters — don't let the bot go silent or generic on an edge case; that's exactly the "kept asking hardcoded things" failure mode from before.)*

## 5. Calculator result
> For a ₹{principal} loan over {tenure} years at {rate}%: your estimated EMI is ₹{emi}/month after the {moratorium}-month grace period. During the grace period, estimated interest is ₹{moratorium_interest}/month. *(These are estimates — final terms are set by your Channel Partner.)*

## 6. Partner locator result
> Nearest eligible partners for you:
> {list of: name, agency_type, distance_km}
> *(Note: eligibility here reflects each partner's current fund availability — shown for demonstration with representative data.)*

*(That last line is the honest-mock disclosure — keep it in every locator response, not just the pitch.)*

## 7. Fallback / error states (never let these go silent)
- LLM/extraction failure: "Sorry, having a little trouble understanding that — could you try rephrasing, or pick one of the options below?" *(then re-show buttons, don't just hang)*
- All providers down: "I'm having connection trouble right now — please try again in a minute. Your progress so far is saved."
- Off-topic message: "I'm focused on NSFDC scheme matching for now — want to start with your project type?"

## 8. Consent withdrawal (must be as easy as giving consent — Rule 3 requirement)
> Reply STOP anytime to end this conversation and delete your data. Reply START to begin again.
