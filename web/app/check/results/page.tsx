import Link from "next/link";
import { AlertCircle, ArrowLeft, BadgeCheck, HelpCircle } from "lucide-react";

import { ButtonLink } from "@/components/ui/button-link";
import { checkScheme, discover, type DiscoveryMatch, type SchemeVerdict } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import { answersToPayload, queryToAnswers } from "@/lib/facets";

export const metadata = {
  title: "Your matches",
  description: "The government schemes you are likely to be entitled to.",
};

// The results depend entirely on the query string, and a person's answers are
// nobody's business — never cached, never prerendered.
export const dynamic = "force-dynamic";

const STRENGTH = {
  ELIGIBLE: {
    label: "Eligible",
    blurb: "Every published rule checked",
    icon: BadgeCheck,
    className: "bg-verified-soft text-verified",
  },
  LIKELY: {
    label: "Likely",
    blurb: "You meet the conditions we hold",
    icon: BadgeCheck,
    className: "bg-secondary text-primary",
  },
  CHECK: {
    label: "Worth checking",
    blurb: "Asks about something you did not answer",
    icon: HelpCircle,
    className: "bg-gold-soft text-gold-ink",
  },
  NOT_MATCHED: {
    label: "Not a match",
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
  const t = await getT();

  // Arrived from one scheme's page: that scheme's verdict is the answer they
  // came for, so it goes first, ahead of the hundreds of general matches.
  const wanted = Array.isArray(params.scheme) ? params.scheme[0] : params.scheme;
  const focus = wanted ? await checkScheme(wanted, payload) : null;

  let result;
  try {
    result = await discover({ ...payload, limit: 60 });
  } catch {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20 text-center">
        <h1 className="font-display text-[1.5rem] font-normal">
          We could not run the match just now
        </h1>
        <p className="mt-3 text-muted-foreground">
          The scheme engine did not answer. Your answers are safe in the address
          bar — try again in a moment.
        </p>
        <ButtonLink href={`/check`} className="mt-6 h-11 px-6">
          Back to the questions
        </ButtonLink>
      </div>
    );
  }

  const { matches, counts } = result;
  const answeredCount = Object.keys(answers).length;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-14">
      <Link
        href={`/check`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="size-4" />
        Change my answers
      </Link>

      {focus ? <FocusVerdict verdict={focus} t={t} /> : null}

      <header className="mt-6 border-b border-border pb-8">
        {/* The headline is the targeted count, not the total. A scheme that
            restricts nobody matches everybody, so "664 matches" is true and
            useless; "41 are meant for you" is the number worth acting on. */}
        <h1 className="font-display text-[2rem] font-light sm:text-4xl">
          {result.total_targeted > 0 ? (
            <>
              {result.total_targeted.toLocaleString("en-IN")}{" "}
              {result.total_targeted === 1 ? "scheme is" : "schemes are"} aimed
              at people like you
            </>
          ) : (
            <>
              {result.total_matched.toLocaleString("en-IN")}{" "}
              {result.total_matched === 1 ? "scheme" : "schemes"} you may be
              entitled to
            </>
          )}
        </h1>
        <p className="mt-3 max-w-3xl text-muted-foreground">
          {result.total_targeted > 0 ? (
            <>
              They name your community, work or circumstances directly. Another{" "}
              {(result.total_matched - result.total_targeted).toLocaleString("en-IN")}{" "}
              schemes are open to you without singling anyone out — all of them
              are below, strongest first.
            </>
          ) : (
            <>
              Checked against {result.total_considered.toLocaleString("en-IN")}{" "}
              schemes using {answeredCount}{" "}
              {answeredCount === 1 ? "answer" : "answers"}. Telling us your
              community or your work is what surfaces the schemes meant
              specifically for you.
            </>
          )}
        </p>

        <div className="mt-5 flex flex-wrap gap-3">
          <Tally count={counts.eligible} label="Eligible" tone="verified" />
          <Tally count={counts.likely} label="Likely" tone="primary" />
          <Tally count={counts.check} label="Worth checking" tone="gold" />
        </div>
      </header>

      {matches.length === 0 ? (
        <NoMatches />
      ) : (
        <>
          <ul className="mt-8 grid gap-4 lg:grid-cols-2">
            {matches.map((match) => (
              <MatchCard key={match.scheme_uid} match={match} />
            ))}
          </ul>

          {result.total_matched > matches.length ? (
            <p className="mt-8 card-quiet p-5 sm:p-6 text-sm text-muted-foreground">
              Showing the {matches.length} strongest of{" "}
              {result.total_matched.toLocaleString("en-IN")} matches. Answering
              one or two more questions is the fastest way to shorten this list —
              particularly your state and household income.
            </p>
          ) : null}
        </>
      )}

      {result.not_matched.length > 0 ? (
        <section className="mt-12">
          <h2 className="font-display text-[1.25rem] font-normal">
            Ruled out, and why
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Shown rather than hidden, so you can see the rule that stopped it. If
            one looks wrong, the answer behind it is probably the thing to change.
          </p>
          <ul className="mt-4 space-y-2">
            {result.not_matched.map((match) => (
              <li
                key={match.scheme_uid}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3"
              >
                <Link
                  href={`/schemes/${match.slug}`}
                  className="text-sm font-medium hover:text-primary"
                >
                  {match.name.trim()}
                </Link>
                <span className="text-xs text-muted-foreground">
                  does not match on {match.unmet.join(", ")}
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
}: {
  verdict: SchemeVerdict;
  t: (key: never, vars?: Record<string, string | number>) => string;
}) {
  const tr = t as unknown as (key: string) => string;
  const blocked = verdict.verdict === "NOT_MATCHED";

  return (
    <section
      className={`mt-6 rounded-xl border p-6 ${
        blocked ? "border-clay/30 bg-clay-soft" : "border-verified/40 bg-verified-soft"
      }`}
    >
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {tr("results.focus.title")}
      </p>
      <h2 className="mt-2 font-display text-[1.5rem] font-normal">
        <Link href={`/schemes/${verdict.slug}`} className="hover:underline">
          {verdict.name}
        </Link>
      </h2>
      <p className={`mt-1 font-medium ${blocked ? "text-clay" : "text-verified"}`}>
        {blocked
          ? `${tr("results.notMatchedOn")} ${verdict.unmet.join(", ")}`
          : tr(verdict.verdict === "CHECK" ? "results.strength.check" : "results.strength.likely")}
      </p>

      <dl className="mt-4 grid gap-1.5 border-t border-border/60 pt-4 text-sm sm:grid-cols-2">
        {verdict.meets.map((item) => (
          <div key={item} className="flex items-center gap-2">
            <BadgeCheck className="size-4 shrink-0 text-verified" />
            <dt>{item}</dt>
          </div>
        ))}
        {verdict.unmet.map((item) => (
          <div key={item} className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0 text-clay" />
            <dt className="font-medium text-clay">{item}</dt>
          </div>
        ))}
        {verdict.unknown.map((item) => (
          <div key={item} className="flex items-center gap-2">
            <HelpCircle className="size-4 shrink-0 text-gold-ink" />
            <dt className="text-muted-foreground">
              {item} — {tr("results.stillToCheck").toLowerCase()}
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

function MatchCard({ match }: { match: DiscoveryMatch }) {
  const strength = STRENGTH[match.strength];
  const Icon = strength.icon;

  return (
    <li className="card-quiet relative flex flex-col p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold ${strength.className}`}
        >
          <Icon className="size-3.5" />
          {strength.label}
        </span>
        {match.depth === "DEEP" ? (
          <span className="rounded-md bg-primary px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-primary-foreground">
            Loan · fully checked
          </span>
        ) : null}
        {match.state && match.state !== "All" ? (
          <span className="text-xs text-muted-foreground">{match.state}</span>
        ) : null}
      </div>

      <h3 className="mt-3 font-semibold leading-snug">
        <Link href={`/schemes/${match.slug}`} className="hover:text-primary">
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
          <span className="font-medium text-foreground">Matched on</span>{" "}
          {match.matched_on.join(", ")}
        </p>
      ) : null}

      {match.unknown.length > 0 ? (
        <p className="mt-1.5 text-xs text-gold-ink">
          <span className="font-medium">Still to check</span>{" "}
          {match.unknown.join(", ")}
        </p>
      ) : null}
    </li>
  );
}

function NoMatches() {
  return (
    <div className="mt-10 rounded-2xl border border-dashed border-input p-12 text-center">
      <h2 className="font-display text-[1.25rem] font-normal">
        Nothing matched every answer
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        That usually means one answer is narrower than it needs to be — a state
        with few schemes of its own, or an income figure entered per month rather
        than per year. Change one answer and the list will almost certainly fill.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <ButtonLink href="/check" className="h-11 rounded-full px-5">
          Change my answers
        </ButtonLink>
        <ButtonLink
          href="/schemes"
          variant="outline"
          className="h-11 bg-card px-5"
        >
          Browse everything instead
        </ButtonLink>
      </div>
    </div>
  );
}
