"use client";

import { useEffect, useState } from "react";
import { Check, ExternalLink, Printer, UserRound } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { useProfile } from "@/components/profile-sheet";
import { Button } from "@/components/ui/button";
import { ButtonLink } from "@/components/ui/button-link";
import { cn } from "@/lib/utils";

/**
 * The completed application, on paper.
 *
 * The assistant could already fill a form and say so, and there was nowhere to
 * look. It returned the filled fields as a card the chat had no renderer for,
 * so "I have filled in your personal details" was a claim with nothing behind
 * it — which is the one thing this product is not allowed to do.
 *
 * This is the thing behind it: every field the scheme asks for, filled from
 * what the person has already told us, blanks left blank, the documents to
 * carry, and the steps in order. Printable, because the destination is a
 * counter at a bank or a CSC and the person needs something in their hand.
 *
 * It still submits nothing. See `src/application.py` for why that is a
 * decision rather than a gap.
 */

interface Field {
  key: string;
  label: string;
  value: string;
  blank: boolean;
}

interface Pack {
  slug: string;
  name: string;
  official_url: string;
  mode: string;
  fields: Field[];
  documents: { text: string }[];
  steps: string[];
  notes: string[];
  filled: number;
  total: number;
}

export function ApplicationPack({ slug }: { slug: string }) {
  const { lang, t } = useLanguage();
  const profile = useProfile();
  const [pack, setPack] = useState<Pack | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    setFailed(false);
    fetch(`/api/application/${encodeURIComponent(slug)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, lang }),
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((data) => live && setPack(data))
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [slug, profile, lang]);

  if (failed) {
    return (
      <p className="text-sm leading-relaxed text-clay">{t("apply.failed")}</p>
    );
  }
  if (!pack) {
    return <p className="text-sm text-muted-foreground">{t("apply.loading")}</p>;
  }

  const blanks = pack.fields.filter((f) => f.blank).length;

  return (
    <div className="space-y-8">
      {/* Not a progress bar. The number that matters is what is still missing,
          because that is the work left before someone can walk in. */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-border bg-secondary/40 px-4 py-3 print:hidden">
        <p className="text-sm">
          <span className="font-semibold tabular-nums">{pack.filled}</span>
          <span className="text-muted-foreground">
            {" "}/ {pack.total} {t("apply.filledOf")}
          </span>
        </p>
        {blanks ? (
          <p className="text-sm text-muted-foreground">
            {t("apply.blanksLeft", { n: blanks })}
          </p>
        ) : null}
        <div className="ms-auto flex flex-wrap gap-2">
          <ButtonLink href="/me" variant="ghost" className="h-9">
            <UserRound className="size-4" />
            {t("apply.editDetails")}
          </ButtonLink>
          <Button
            type="button"
            variant="outline"
            className="h-9"
            onClick={() => window.print()}
          >
            <Printer className="size-4" />
            {t("apply.print")}
          </Button>
        </div>
      </div>

      {/* ---------------------------------------------------------- fields */}
      <section>
        <h2 className="font-display text-lg font-bold">{t("apply.yourDetails")}</h2>
        <p className="mt-1 text-sm text-muted-foreground print:hidden">
          {t("apply.yourDetails.hint")}
        </p>
        <dl className="mt-4 border-t border-border">
          {pack.fields.map((f) => (
            <div
              key={f.key}
              className="grid gap-x-6 gap-y-1 border-b border-border py-2.5 sm:grid-cols-[15rem_1fr]"
            >
              <dt className="text-sm text-muted-foreground">{f.label}</dt>
              <dd
                className={cn(
                  "text-sm",
                  f.blank
                    ? // A ruled line to write on, not the word "missing" — this
                      // sheet is filled in by hand at a counter.
                      "min-h-[1.5rem] border-b border-dashed border-faint/60 text-faint"
                    : "font-medium text-foreground",
                )}
              >
                {f.value || " "}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      {/* ------------------------------------------------------- documents */}
      {pack.documents.length ? (
        <section>
          <h2 className="font-display text-lg font-bold">
            {t("apply.documents")}{" "}
            <span className="text-sm font-normal text-muted-foreground tabular-nums">
              ({pack.documents.length})
            </span>
          </h2>
          <ul className="mt-4 space-y-2">
            {pack.documents.map((d, i) => (
              <li key={i} className="flex items-start gap-3 text-sm leading-relaxed">
                <span
                  aria-hidden
                  className="mt-0.5 size-4 shrink-0 rounded-[0.25rem] border border-foreground/40"
                />
                <span>{d.text}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* ----------------------------------------------------------- steps */}
      {pack.steps.length ? (
        <section>
          <h2 className="font-display text-lg font-bold">{t("apply.steps")}</h2>
          <ol className="mt-4 space-y-2.5">
            {pack.steps.map((s, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed">
                <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-secondary text-[0.7rem] font-semibold tabular-nums text-primary">
                  {i + 1}
                </span>
                <span>{s}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* ----------------------------------------------------------- notes */}
      {pack.notes.length ? (
        <section className="space-y-2">
          {pack.notes.map((n, i) => (
            <p
              key={i}
              className="border-s-2 border-gold bg-gold-soft px-4 py-2.5 text-sm leading-relaxed text-gold-ink"
            >
              {n}
            </p>
          ))}
        </section>
      ) : null}

      {pack.official_url ? (
        <a
          href={pack.official_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline print:hidden"
        >
          {t("apply.official")}
          <ExternalLink className="size-3.5" />
        </a>
      ) : null}

      <p className="flex items-start gap-2 border-t border-border pt-4 text-xs leading-relaxed text-muted-foreground">
        <Check className="mt-0.5 size-3.5 shrink-0 text-leaf" />
        {t("apply.notSubmitted")}
      </p>
    </div>
  );
}
