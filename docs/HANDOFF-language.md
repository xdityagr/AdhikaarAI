# Handoff — language and content quality

Side work, parallelisable. **Touches only translations, locale files and the
corpus backfill.** Nothing here changes a feature, a route, or `src/discovery.py`,
so it can run alongside feature work without conflicting — the one shared file is
`web/lib/i18n/locales/*.ts`, and the merge script below appends rather than
rewrites.

There is no `docs/I18N.md`. This file is the whole of it.

**Status: tasks 1, 2 and 4 are done. Task 3 is a long-running job that is
part-way through — see the table.** What each pass found is recorded below, so a
later one does not have to rediscover it.

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

Three of those classes are now **tested** rather than only described — see
"The guards" below. The fourth kind, where the sentence is grammatical but wrong
in register, still has to be read.

---

## Task 1 — Sweep the pages that have not been checked — done

`scripts/audit_i18n.py` **reported 32 findings and all of them were noise**:
translation keys, the brand name, and generated files under `.next`. It read one
line at a time, and JSX text wraps:

```tsx
<span className="text-sm text-muted-foreground">
  aimed at you, of {(card.total as number)?.toLocaleString("en-IN")} possible
</span>
```

No line holds both the `>` and the `<` around that sentence, it starts
lowercase, and it has an expression in the middle. So it passed three pages that
between them printed `aimed at you, of 4,736 possible`, `does not meet the
condition on {facets} gender, age` and `You keep ₹14,400.` in all thirteen
languages.

It now reads whole files: blanks comments, collapses `{expressions}` that hold
no JSX to a marker so a wrapped sentence is still one sentence, and looks for
runs of English between tags. 19 findings, of which 16 were real. It exits
non-zero, so it can gate a commit.

**Two things it still cannot see, both of which were found by reading:**

- a call that *uses* `t()` but never passes the values — `t("…notMatchedOn")`
  printed a literal `{facets}`. Now covered by a test.
- a value interpolated from the backend, which is not in the source at all.
  `DOCUMENT_LABELS` came out of this. Now covered by a test.

Fixed, with the key added to all thirteen locales in each case:

| Where | Was |
|---|---|
| `chat-panel.tsx` | `tr("results.notMatchedOn") + " " + unmet.join(", ")` → literal `{facets}`, English facet names, Latin comma |
| `chat-panel.tsx` | `tr("results.stillToCheck").toLowerCase()` → literal `{facets}`; `.toLowerCase()` does nothing in any Indic script. Now `results.stillToCheck.label`, as the results page already did |
| `chat-panel.tsx` | `meets` / `unmet` / `unknown` rendered raw → `facetLabel()` |
| `chat-panel.tsx` | `aimed at you, of {n} possible`, `{n} found`, `on the same {loan}. You keep {x}.`, `{n} yr`, `{n} km`, `matched on {…}` |
| `chat-panel.tsx` | `blanks.join(", ")` → `listJoin()`, which knows Urdu's comma |
| `document-capture.tsx` | six strings; the component had no translator at all |
| `document-readiness.tsx` | the classifier's document name, interpolated raw into a translated sentence |
| `category-grid.tsx` | the fifteen category names, rendered raw though `categoryLabel()` existed |
| `site-footer.tsx` | two source links whose `label` field held English where a key belongs, so `t()` fell through to the key and they were never translated |
| `layout.tsx` | the site title and description — the browser tab and every forwarded link preview — were English for every reader |
| `not-found.tsx`, `schemes/page.tsx`, `partners/page.tsx` | hardcoded sentences; `partners` also printed the raw enum `mocked` |
| `schemes/[slug]/page.tsx` | the source date came out in Bengali, Marathi, Assamese and Urdu **numerals**, against the Latin-digits rule below |

`chat/page.tsx`, `apply/[slug]/page.tsx` and `application-pack.tsx` were clean —
the hits there were inside comments.

**Three findings are deliberate and should stay:** the scheme name on the
landing page, `PFMS — Know Your Payment` (the portal's own page title), and the
OpenStreetMap attribution in `map-card.tsx`, which is an ODbL licence notice and
says the same thing in every language. The audit will keep reporting them.

## Task 2 — Verify the rendered sentences per language — done

`scripts/render.py` rewritten. It takes languages as arguments, defaults to
`hi, ta, bn, mr, ur`, takes `--all`, and no longer hardcodes an absolute path.

Two things it was getting wrong: it joined facets with `", "` in **every**
language, so it could not show the Urdu defect it existed to find; and it used
facet names the engine does not emit (`income` — the engine says `family
income`), so it proved nothing about the string the app is actually handed. It
now reads the separator and the tables out of `vocabulary.ts`.

It also **reports which interpolating keys have no case yet**, because a key
nobody has put a value into is a key nobody has read. That list is now empty:
all 50-odd interpolating keys in `en.ts` are exercised.

What reading the output found:

- `FACET_LABELS` had no `assets` entry, so a scheme that caps what you may own
  said so in English in twelve languages.
- the new `chat.card.matchedOn` in Marathi used the postposition `वर`, which
  must fuse to the noun (`उत्पन्नावर`) — the defect in the table above. The three
  keys beside it already solve this with an em dash and no case marker; it now
  matches them. Marathi, Tamil and Bengali use the dash form; Hindi, Gujarati,
  Punjabi and Urdu use a genitive that does not inflect the noun.
- `wa.prefill` and `wa.prefill.resume` are spoken **as the user**, whose gender
  is unknown, and they disagreed: the resume line was feminine first person in
  Hindi, Punjabi and Urdu while the other was masculine in six languages, so the
  same person sent a masculine sentence on one button and a feminine one on the
  other. Urdu also opened with two different greetings. All thirteen are now
  neutral, built on the dative construction the Hindi one already used. The
  Marathi grievance text solves it differently and legitimately, with an
  explicit `मागतो/मागते`.

The other first-person strings — `chat.try1`–`4`, `household.empty.seed` — were
already neutral.

## Task 3 — Corpus backfill, 11 languages — part-way

> **The previous note here was wrong, and it mattered.** It said "Urdu is not
> published by myScheme at all" and that Urdu readers get "a fully translated
> interface over English scheme names, and there is nothing in the corpus to fix
> that". It asked for that to be confirmed against the API before being treated
> as permanent. It does not hold: `lang=ur` returns HTTP 200 with a full `ur`
> block — `basicDetails.schemeName`, `schemeContent.briefDescription`,
> `benefits_md`, `eligibilityCriteria` and `applicationProcess.process_md`, all
> in Urdu. Urdu had zero rows because nobody had run it. `LANGUAGES` in
> `src/corpus/myscheme.py` is only `en, hi, mr, bn, ta`; the other ten were
> filled by passing `--langs`, and `ur` never was.

So Urdu is the **highest-value** language to backfill, not an impossible one: it
goes from nothing to complete, and it is the one language whose readers are
currently shown English scheme names under a fully translated interface.

```
python scripts/backfill_translations.py --langs ur        # resume; skips what it holds
```

Resumable, safe to stop, skips what it already holds. Roughly 2 requests per
scheme per language, ~0.65s apart — about **1.7 hours per language**, so one
language is an evening and eleven is a weekend. Run them a few at a time.

Current state (`data/schemes.db`, 4736 schemes):

| lang | name + brief | how-to-apply | documents |
|---|---|---|---|
| hi | 4732 | 4716 | 4704 |
| **ur** | **1348 and climbing** | **1348** | **1343** |
| bn, mr | 4732 | 0 | 0 |
| gu, or, pa, te, kn, ta, ml | ~4730 | 0 | 0 |
| as | 3490 | 0 | 0 |

Urdu was left running and is not finished. Re-run the command above to continue
it; it picks up where it stopped. Note that for Urdu the same pass also fills
`name`, `brief`, `benefits_md` and `eligibility_md`, because `store_translation`
writes every translated field from the detail call and Urdu had no row at all —
which is why its name count climbs with the others.

## Task 4 — Re-verify after the backfill — done for Urdu

`scripts/sweep.py` rewritten. It took no arguments, was hardcoded to Hindi, and
imported a baseline parser from a previous session's temp directory. It now takes
language codes, defaults to every language in the corpus, and reports the two
things that matter.

**Urdu does not split badly — it parses better than Hindi:**

| | collapsed to ≤2 items | step count agrees with English |
|---|---|---|
| hi | 1689 / 4716 (36%) | 29% |
| **ur** | **375 / 1302 (29%)** | **36%** |

So `_STEP_LABEL` needs no widening for Urdu. The reason it already works:
`[^\W\d_]` is Unicode-aware, so it matches Urdu letters as readily as Devanagari.

**One real bug found here, left alone on purpose.** About 1 step in 30 keeps a
leading markdown marker, so the apply page shows `**** The interested applicant
should visit…`. It is **worst in English** (1409/41036 steps, 3.4%; Hindi 1.6%,
Urdu 1.5%), so it is not a translation defect at all — it is a stripping gap in
`parse_list`. Fixing it means changing `src/application.py`, which this lane is
scoped out of, and the handoff only sends you there for the step-label case.
It is a one-line strip at the top of each parsed step. Worth someone's ten
minutes.

---

## The guards

Four tests were added to `tests/test_locales.py` so the structural defect
classes cannot come back. Each was checked by reintroducing the defect and
watching it fail.

- `test_every_facet_the_engine_emits_has_a_translation` — reads the facet names
  out of `src/discovery.py` rather than listing them, so the list cannot rot.
  This is what found `assets`.
- `test_every_document_label_has_a_translation` — same, against
  `KNOWN_DOCUMENTS` in `src/documents.py`.
- `test_every_vocabulary_entry_covers_every_language` — all four tables, all
  twelve languages. `label()` falls back to English, which is the right
  behaviour and the wrong thing to find out in production.
- `test_a_string_that_interpolates_is_never_asked_for_without_its_values` —
  catches `t("key")` where the English has a `{placeholder}`. Splitting the
  string to wrap a React element around the placeholder is allowed, and
  `notfound.back` does exactly that: only the translation knows where in the
  sentence the link goes.
- `test_urdu_punctuates_in_its_own_script` — a Latin comma used as punctuation.
  Figures are exempt: `₹1,20,000` is Indian digit grouping, deliberately Latin.

## How to add translations

Do **not** hand-edit the locale files. Write a JSON file of
`{lang: {key: value}}` and run:

```
python scripts/merge_locales.py yourfile.json
```

It replaces existing keys in place and appends new ones before the closing brace,
adding the comma the previous entry may be missing. That missing comma broke all
twelve files once; `tests/test_locales.py` now catches both it and the doubled
comma, but the script is still the safe path. It accepts an absolute path, so the
JSON does not have to live in `scripts/`.

Validate the JSON before merging — placeholders against English, no `U+FFFD`
from a bad copy-paste, no Latin comma in the Urdu. One Punjabi string lost a
character to encoding damage this way and the merge would have taken it.

After any change:

```
python -m pytest tests/test_locales.py -q      # coverage, placeholders, syntax, the guards
python scripts/render.py                        # and READ the output
python scripts/audit_i18n.py                    # 5 findings expected, all deliberate
cd web && npx tsc --noEmit && npx next build    # the build the tests cannot see
```

## Things not to change

- **Scheme, office and programme names** are never translated by us. They come
  from the corpus in the language the government published them, and an invented
  translation sends someone to a counter to ask for something that does not
  exist.
- **Portal names** — PFMS, DBT Bharat, CPGRAMS — stay in English. They are what
  the sign above the counter and the browser tab say. Their descriptions are
  translated, and `footer.source.*` is how: the name stays, the parenthetical
  does not.
- **Abbreviations and the words printed on the forms** — PAN, EPIC, UDID,
  khatauni, 7/12, pahani, e-Shram — stay as they are inside `DOCUMENT_LABELS`,
  for the same reason.
- **Occupation values** in `web/lib/facets.ts` are matched as exact strings
  against the corpus. Tidying "Safai Karamchari" breaks the filter silently.
  The same is true of every key in `vocabulary.ts`: the English string is the
  value, only the label is translated.
- **Digit grouping and digits** are `en-IN` and Latin deliberately (`GROUPING` in
  `app/check/results/page.tsx`, `numberingSystem: "latn"` in `formatNumber`):
  Indian grouping, Latin numerals, because a person copying a figure onto a paper
  form needs the digits the clerk expects. This applies to **dates** too, which
  is the bug Task 1 fixed — month names translate, the numbers do not.

## A note on the shared branch

Another session committing on this branch ran `git add -A` and swept two of this
lane's in-progress files (`scripts/audit_i18n.py`, `web/components/chat-panel.tsx`)
into commit `5ed19b7`, whose message is about something else entirely. Nothing
was lost, but the history does not say where those changes came from. Stage
explicit paths here, and check `git log` for your own files before assuming they
are uncommitted.
