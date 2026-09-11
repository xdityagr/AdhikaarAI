import Link from "next/link";
import { AlertCircle, ArrowLeft, BadgeCheck, HelpCircle } from "lucide-react";

import { ButtonLink } from "@/components/ui/button-link";
import { checkScheme, discover, type DiscoveryMatch, type SchemeVerdict } from "@/lib/api";
import { type Translate } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n/config";
import { facetLabel, facetList } from "@/lib/i18n/vocabulary";
import { getLang, getT } from "@/lib/i18n/server";
import { answersToPayload, queryToAnswers } from "@/lib/facets";

export async function generateMetadata() {
  const t = await getT();
  return { title: t("results.title"), description: t("results.description") };
}

// The results depend entirely on the query string, and a person's answers are
// nobody's business — never cached, never prerendered.
export const dynamic = "force-dynamic";

/* Keys, not sentences. Resolved at render against the reader's language —
   holding the English here is how "Worth checking" survived a switch to
   Hindi on a page where everything around it had changed. */
/* Indian digit grouping — 1,23,456 rather than 123,456 — with Latin numerals,
   which is what every government form and notice board uses. Deliberately not
   the reader's own locale: `toLocaleString("bn-IN")` can render Bengali
   numerals, and a person copying a figure onto a paper form needs the digits
   the clerk is expecting. */
const GROUPING = "en-IN";

const STRENGTH = {
  ELIGIBLE: {
    label: "results.strength.eligible",
    blurb: "results.strength.eligible.blurb",
    icon: BadgeCheck,
    className: "bg-verified-soft text-verified",
  },
  LIKELY: {
    label: "results.strength.likely",
    blurb: "results.strength.likely.blurb",
    icon: BadgeCheck,
    className: "bg-secondary text-primary",
  },
  CHECK: {
    label: "results.strength.check",
    blurb: "results.strength.check.blurb",
    icon: HelpCircle,
    className: "bg-gold-soft text-gold-ink",
  },
  NOT_MATCHED: {
    label: "results.strength.notMatched",
    blurb: "",
    icon: AlertCircle,
    className: "bg-muted text-muted-foreground",
  },
} as const;

export default async function ResultsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const answers = queryToAnswers(params);
  const payload = answersToPayload(answers);
  const lang = await getLang();
  const t = await getT();

  // Arrived from one scheme's page: that scheme's verdict is the answer they
  // came for, so it goes first, ahead of the hundreds of general matches.
  const wanted = Array.isArray(params.scheme) ? params.scheme[0] : params.scheme;
  const focus = wanted ? await checkScheme(wanted, { ...payload, lang }) : null;

  let result;
  try {
    result = await discover({ ...payload, limit: 60, lang });
  } catch {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <h1 className="font-display text-[1.5rem] font-normal">
          {t("results.error.h1")}
        </h1>
        <p className="mt-3 text-muted-foreground">{t("results.error.body")}</p>
        <ButtonLink href={`/check`} className="mt-6 h-11 px-6">
          {t("results.error.back")}
        </ButtonLink>
      </div>
    );
  }

  const { matches, counts } = result;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/check`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="size-4" />
        {t("results.back")}
      </Link>

      {focus ? <FocusVerdict verdict={focus} t={t} lang={lang} /> : null}

      <header className="mt-6 border-b border-border pb-8">
        {/* The headline is the targeted count, not the total. A scheme that
            restricts nobody matches everybody, so "664 matches" is true and
            useless; "41 are meant for you" is the number worth acting on. */}
        <h1 className="font-display text-[2rem] font-light sm:text-4xl">
          {result.total_targeted > 0
            ? result.total_targeted === 1
              ? t("results.h1.targeted.one")
              : t("results.h1.targeted", {
                  count: result.total_targeted.toLocaleString(GROUPING),
                })
            : result.total_matched === 1
              ? t("results.h1.plain.one")
              : t("results.h1.plain", {
                  count: result.total_matched.toLocaleString(GROUPING),
                })}
        </h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          {result.total_targeted > 0
            ? t("results.lede.targeted", {
                count: (result.total_matched - result.total_targeted)
                  .toLocaleString(GROUPING),
              })
            : t("results.lede.plain", {
                total: result.total_considered.toLocaleString(GROUPING),
              })}
        </p>

        <div className="mt-5 flex flex-wrap gap-3">
          <Tally count={counts.eligible} label={t("results.strength.eligible")} tone="verified" />
          <Tally count={counts.likely} label={t("results.strength.likely")} tone="primary" />
          <Tally count={counts.check} label={t("results.strength.check")} tone="gold" />
        </div>
      </header>

      {matches.length === 0 ? (
        <NoMatches t={t} />
      ) : (
        <>
          <ul className="mt-8 grid gap-4 lg:grid-cols-2">
            {matches.map((match) => (
              <MatchCard
                key={match.scheme_uid}
                match={match}
                t={t}
                lang={lang}
              />
            ))}
          </ul>

          {result.total_matched > matches.length ? (
            <p className="mt-8 card-quiet p-5 sm:p-6 text-sm text-muted-foreground">
              {t("results.showing", {
                shown: matches.length,
                total: result.total_matched.toLocaleString(GROUPING),
              })}
            </p>
          ) : null}
        </>
      )}

      {result.not_matched.length > 0 ? (
        <section className="mt-12">
          <h2 className="font-display text-[1.25rem] font-normal">
            {t("results.ruledOut")}
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            {t("results.ruledOut.lede")}
          </p>
          <ul className="mt-4 space-y-2">
            {result.not_matched.map((match) => (
              <li
                key={match.scheme_uid}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3"
              >
                <Link
                  href={`/schemes/${match.slug}?from=check`}
                  className="text-sm font-medium hover:text-primary"
                >
                  {match.name.trim()}
                </Link>
                <span className="text-xs text-muted-foreground">
                  {t("results.notMatchedOn", {
                    facets: facetList(lang, match.unmet),
                  })}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

/**
 * The one scheme they asked about, answered plainly and first.
 *
 * Before this, tapping "Check my eligibility" on a scheme page dropped people
 * into the general wizard and returned six hundred matches — the answer was in
 * there somewhere, which is not the same as answering.
 */
function FocusVerdict({
  verdict,
  t,
  lang,
}: {
  verdict: SchemeVerdict;
  t: Translate;
  lang: Lang;
}) {
  const blocked = verdict.verdict === "NOT_MATCHED";

  return (
    <section
      className={`mt-6 rounded-xl border p-6 ${
        blocked ? "border-clay/30 bg-clay-soft" : "border-verified/40 bg-verified-soft"
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {t("results.focus.title")}
      </p>
      <h2 className="mt-2 font-display text-[1.5rem] font-normal">
        <Link href={`/schemes/${verdict.slug}?from=check`} className="hover:underline">
          {verdict.name}
        </Link>
      </h2>
      <p className={`mt-1 font-medium ${blocked ? "text-clay" : "text-verified"}`}>
        {blocked
          ? t("results.notMatchedOn", { facets: facetList(lang, verdict.unmet) })
          : t(verdict.verdict === "CHECK" ? "results.strength.check" : "results.strength.likely")}
      </p>

      <dl className="mt-4 grid gap-1.5 border-t border-border/60 pt-4 text-sm sm:grid-cols-2">
        {verdict.meets.map((item) => (
          <div key={item} className="flex items-center gap-2">
            <BadgeCheck className="size-4 shrink-0 text-verified" />
            <dt>{facetLabel(lang, item)}</dt>
          </div>
        ))}
        {verdict.unmet.map((item) => (
          <div key={item} className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0 text-clay" />
            <dt className="font-medium text-clay">{facetLabel(lang, item)}</dt>
          </div>
        ))}
        {verdict.unknown.map((item) => (
          <div key={item} className="flex items-center gap-2">
            <HelpCircle className="size-4 shrink-0 text-gold-ink" />
            <dt className="text-muted-foreground">
              {facetLabel(lang, item)} — {t("results.stillToCheck.label")}
            </dt>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Tally({
  count,
  label,
  tone,
}: {
  count: number;
  label: string;
  tone: "verified" | "primary" | "gold";
}) {
  const tones = {
    verified: "bg-verified-soft text-verified",
    primary: "bg-secondary text-primary",
    gold: "bg-gold-soft text-gold-ink",
  };
  return (
    <span
      className={`inline-flex items-baseline gap-2 rounded-lg px-3 py-2 text-sm font-medium ${tones[tone]}`}
    >
      <span className="font-display text-[1.125rem] font-normal tabular-nums">{count}</span>
      {label}
    </span>
  );
}

function MatchCard({
  match,
  t,
  lang,
}: {
  match: DiscoveryMatch;
  t: Translate;
  lang: Lang;
}) {
  const strength = STRENGTH[match.strength];
  const Icon = strength.icon;

  return (
    <li className="card-quiet relative flex flex-col p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold ${strength.className}`}
        >
          <Icon className="size-3.5" />
          {t(strength.label)}
        </span>
        {match.depth === "DEEP" ? (
          <span className="rounded-md bg-primary px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-primary-foreground">
            {t("results.deep")}
          </span>
        ) : null}
        {match.state && match.state !== "All" ? (
          <span className="text-xs text-muted-foreground">{match.state}</span>
        ) : null}
      </div>

      <h3 className="mt-3 font-semibold leading-snug">
        <Link href={`/schemes/${match.slug}?from=check`} className="hover:text-primary">
          <span className="absolute inset-0" aria-hidden />
          {match.name.trim()}
        </Link>
      </h3>

      {match.brief ? (
        <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
          {match.brief}
        </p>
      ) : null}

      {match.matched_on.length > 0 ? (
        <p className="mt-3 text-xs text-muted-foreground">
          {t("results.matchedOn", { facets: facetList(lang, match.matched_on) })}
        </p>
      ) : null}

      {match.unknown.length > 0 ? (
        <p className="mt-1.5 text-xs text-gold-ink">
          {t("results.stillToCheck", { facets: facetList(lang, match.unknown) })}
        </p>
      ) : null}
    </li>
  );
}

function NoMatches({ t }: { t: Translate }) {
  return (
    <div className="mt-10 rounded-2xl border border-dashed border-input p-12 text-center">
      <h2 className="font-display text-[1.25rem] font-normal">
        {t("results.empty.h2")}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        {t("results.empty.body")}
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <ButtonLink href="/check" className="h-11 rounded-full px-5">
          {t("results.back")}
        </ButtonLink>
        <ButtonLink
          href="/schemes"
          variant="outline"
          className="h-11 bg-card px-5"
        >
          {t("results.empty.browse")}
        </ButtonLink>
      </div>
    </div>
  );
}
