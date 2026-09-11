# Handoff — language and content quality

Side work, parallelisable. **Touches only translations, locale files and the
corpus backfill.** Nothing here changes a feature, a route, or `src/discovery.py`,
so it can run alongside feature work without conflicting — the one shared file is
`web/lib/i18n/locales/*.ts`, and the merge script below appends rather than
rewrites.

Whoever picks this up: read `docs/I18N.md` first if it exists, then this.

---

## The rule that matters

**Judge a translation by the finished sentence with real data in it, never by
key coverage.** `tests/test_locales.py` proves every locale has every key, that
placeholders survive, and that the file parses. It cannot tell you whether the
sentence reads like something a person would say. That part is manual, and it is
where every defect so far has been.

Three real ones, for calibration:

| Rendered | Wrong because |
|---|---|
| `मेल नहीं खाता gender` | The template translated; the value interpolated into it did not. |
| `लिंग ची अट` (Marathi) | Needs `लिंगाची` — the genitive inflects the noun, and concatenation cannot do that. |
| `جنس, عمر` (Urdu) | Arabic script takes `،` not `,`. |

The fix for the first two was structural, not lexical: put the whole clause in
one string with a `{placeholder}` so each language controls word order, and
translate the interpolated data too. See `web/lib/i18n/vocabulary.ts`.

---

## Task 1 — Sweep the pages that have not been checked

These three were never audited and almost certainly carry hardcoded English:

- `web/app/chat/page.tsx` and `web/components/chat-panel.tsx`
- `web/app/apply/[slug]/page.tsx` and `web/components/application-pack.tsx`
- `web/app/schemes/[slug]/page.tsx`

There is an audit script at
`scripts/audit_i18n.py` (it greps
JSX text nodes and user-facing props for multi-word English). Expect false
positives on translation keys and the brand name.

For each finding: add a key to `web/lib/i18n/locales/en.ts`, wire the component,
then translate into the other twelve. **Do not** leave English-only keys — that
is the specific thing the user has asked three times to stop.

## Task 2 — Verify the rendered sentences per language

For every key that takes a `{placeholder}`, print the finished string in at least
`hi, ta, bn, mr, ur` with realistic values and read it. A harness exists at
`scripts/render.py`; it imports `_entries` from `tests/test_locales.py` and
substitutes. Extend it to cover the household keys, which have not had this pass:

- `household.result.targeted` / `.plain` with `{count}` = 1 and 12
- `household.card.age` with `{age}` = 7 and 70
- `track.stage.usuallyBy` with `{days}`
- `track.card.mark` with a translated stage name inside `{stage}`

## Task 3 — Corpus backfill, 11 languages

`scheme_i18n` holds myScheme's own translations. Names and summaries are present
for 11 languages; the **how-to-apply steps and document lists** are present for
Hindi only.

```
python scripts/backfill_translations.py --langs mr,bn,ta
```

Resumable, safe to stop, skips what it already holds. Roughly 2 requests per
scheme per language, ~0.65s apart, so one language is several hours. Run them a
few at a time.

Current state (`data/schemes.db`, 4736 schemes):

| lang | name + brief | how-to-apply |
|---|---|---|
| hi | 4732 | **done** |
| bn, mr | 4732 | 0 |
| gu, or, pa, te, kn, ta, ml | ~4730 | 0 |
| as | 3490 | 0 |
| **ur** | **0** | **0** |

**Urdu is not published by myScheme at all.** Urdu readers get a fully
translated interface over English scheme names, and there is nothing in the
corpus to fix that. Worth confirming against the myScheme API before assuming it
is permanent; if it is, the product should say so rather than look broken.

## Task 4 — Re-verify after the backfill

The step parser (`src/application.py`) was fixed against Hindi's shape. Other
languages may mangle differently. After backfilling a language, run the sweep at
`scripts/sweep.py` against it and check:

- how many records collapse to ≤ 2 items (Hindi went 4036 → 1576)
- whether the step count agrees with English (Hindi went 10% → 29%)

If a language splits badly, the likely cause is its word for "Step" not matching
`_STEP_LABEL` in `src/application.py` — the pattern allows one or two letter-only
words and a Latin number before a colon. Widen it with a test, not by loosening
it blindly; `tests/test_application_and_handoff.py::TestStepsSurviveTranslation`
is the place, and `test_a_number_in_prose_is_not_mistaken_for_a_step` is the
guard against over-splitting.

---

## How to add translations

Do **not** hand-edit the locale files. Write a JSON file of
`{lang: {key: value}}` and run:

```
python scripts/merge_locales.py yourfile.json
```

It replaces existing keys in place and appends new ones before the closing brace,
adding the comma the previous entry may be missing. That missing comma broke all
twelve files once; `tests/test_locales.py` now catches both it and the doubled
comma, but the script is still the safe path.

After any change:

```
python -m pytest tests/test_locales.py -q      # coverage, placeholders, syntax
cd web && npx tsc --noEmit && npx next build   # the build the tests cannot see
```

## Things not to change

- **Scheme, office and programme names** are never translated by us. They come
  from the corpus in the language the government published them, and an invented
  translation sends someone to a counter to ask for something that does not
  exist.
- **Portal names** — PFMS, DBT Bharat, CPGRAMS — stay in English. They are what
  the sign above the counter and the browser tab say. Their descriptions are
  translated.
- **Occupation values** in `web/lib/facets.ts` are matched as exact strings
  against the corpus. Tidying "Safai Karamchari" breaks the filter silently.
- **Digit grouping** is `en-IN` deliberately (`GROUPING` in
  `app/check/results/page.tsx`): Indian grouping, Latin numerals, because a
  person copying a figure onto a paper form needs the digits the clerk expects.
