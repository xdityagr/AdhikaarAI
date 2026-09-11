import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ExternalLink, FileText, Sparkles } from "lucide-react";

import { Markdown } from "@/components/markdown";
import { Orb } from "@/components/orb";
import { ButtonLink } from "@/components/ui/button-link";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { getScheme, type SchemeDetail } from "@/lib/api";
import { getLang, getT } from "@/lib/i18n/server";
import { categoryLabel, levelLabel } from "@/lib/i18n/vocabulary";
import { translator, type Translate } from "@/lib/i18n";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const lang = await getLang();
  const scheme = await getScheme(slug, lang);
  if (!scheme) return { title: translator(lang)("scheme.notFound") };
  return {
    title: scheme.name.trim(),
    description: scheme.brief ?? undefined,
  };
}

export default async function SchemePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  // The language decides WHAT is fetched, not just how it is labelled:
  // myScheme publishes its own translations and we hold about 4,730 schemes
  // in each of nine languages. Calling this without a language — which is what
  // it did — served English scheme text under a Hindi interface.
  const [lang, t] = await Promise.all([getLang(), getT()]);
  const scheme = await getScheme(slug, lang);
  if (!scheme) notFound();

  const sections = [
    { title: t("scheme.benefits"), body: scheme.benefits_md },
    { title: t("scheme.eligibility"), body: scheme.eligibility_md },
    { title: t("scheme.exclusions"), body: scheme.exclusions_md },
    { title: t("scheme.application"), body: scheme.application_md },
    { title: t("scheme.documents"), body: scheme.documents_md },
  ].filter((section) => section.body?.trim());

  return (
    <article className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-12">
      <Link
        href="/schemes"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="size-4" />
        {t("scheme.back")}
      </Link>

      <header className="mt-6 border-b border-border pb-8">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-secondary px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-primary">
            {scheme.level ? levelLabel(lang, scheme.level) : t("scheme.level")}
          </span>
          {scheme.state && scheme.state !== "All" ? (
            <span className="rounded-md bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
              {scheme.state}
            </span>
          ) : null}
          {scheme.categories.map((category) => (
            <Link
              key={category}
              href={`/schemes?category=${encodeURIComponent(category)}`}
              className="rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:border-primary/40 hover:text-primary"
            >
              {categoryLabel(lang, category)}
            </Link>
          ))}
        </div>

        <h1 className="mt-4 max-w-4xl font-display text-[2rem] font-light leading-tight sm:text-4xl">
          {scheme.name.trim()}
        </h1>

        {scheme.ministry ? (
          <p className="mt-3 text-sm text-muted-foreground">{scheme.ministry}</p>
        ) : null}

        {scheme.brief ? (
          <p className="mt-4 max-w-3xl text-lg leading-relaxed text-muted-foreground">
            {scheme.brief}
          </p>
        ) : null}
      </header>

      <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_300px]">
        <div className="min-w-0">
          {sections.length === 0 ? (
            <NotYetFetched scheme={scheme} t={t} />
          ) : (
            sections.map((section) => (
              <section key={section.title} className="mb-8">
                <h2 className="font-display text-[1.25rem] font-normal">{section.title}</h2>
                <Markdown className="mt-2">{section.body}</Markdown>
              </section>
            ))
          )}

          {scheme.details_md?.trim() ? (
            <section className="mb-8">
              <h2 className="font-display text-[1.25rem] font-normal">{t("scheme.details")}</h2>
              <Markdown className="mt-2">{scheme.details_md}</Markdown>
            </section>
          ) : null}

          {scheme.faqs?.length ? (
            <section className="mb-8">
              <h2 className="font-display text-[1.25rem] font-normal">
                {t("scheme.faqs")}
              </h2>
              <Accordion className="mt-3">
                {scheme.faqs.map((faq, index) => (
                  <AccordionItem key={index} value={String(index)}>
                    <AccordionTrigger className="text-left">
                      {faq.question}
                    </AccordionTrigger>
                    <AccordionContent>
                      <Markdown>{faq.answer}</Markdown>
                    </AccordionContent>
                  </AccordionItem>
                ))}
              </Accordion>
            </section>
          ) : null}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <div className="card-quiet p-5">
            <h2 className="text-sm font-semibold">{t("scheme.qualify.title")}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
              {t("scheme.qualify.body")}
            </p>
            <ButtonLink
              href={`/check?scheme=${encodeURIComponent(scheme.slug)}`}
              size="pill"
              className="mt-4 w-full"
            >
              {t("scheme.qualify.cta")}
            </ButtonLink>
          </div>

          {/*
            The page answers what the government wrote down. This answers
            everything else — and carries the scheme with it, so nobody has to
            retype a fifteen-word official title to ask about it.
          */}
          <div className="card-quiet p-5">
            {/* The orb rather than a sparkle: this is the same assistant that
                answers in the rail and on WhatsApp, and it should be
                recognisably the same thing wherever it is offered. */}
            <Orb className="size-9" />
            <h2 className="mt-3.5 text-[0.9375rem] font-medium">
              {t("scheme.ask.title")}
            </h2>
            <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
              {t("scheme.ask.body")}
            </p>
            <ButtonLink
              href={`/chat?scheme=${encodeURIComponent(scheme.slug)}`}
              variant="outline"
              size="pill"
              className="mt-4 w-full bg-card"
            >
              {t("scheme.ask.cta")}
            </ButtonLink>
          </div>

          <Provenance scheme={scheme} lang={lang} t={t} />
        </aside>
      </div>
    </article>
  );
}

/**
 * Where the text came from and when. Shown on every scheme because a person
 * about to travel to a government office deserves to know how fresh this is
 * and how to check it against the original.
 */
function Provenance({
  scheme,
  lang,
  t,
}: {
  scheme: SchemeDetail;
  lang: string;
  t: Translate;
}) {
  // The date is formatted in the reader's own locale — a Tamil page that dates
  // its source in English months is still half in English.
  const fetched = scheme.fetched_at
    ? new Date(scheme.fetched_at).toLocaleDateString(`${lang}-IN`, {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : null;

  return (
    <div className="rounded-xl border border-border bg-muted/50 p-5">
      <h2 className="text-sm font-semibold">{t("scheme.source")}</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
        {t("scheme.source.body")}
        {fetched ? ` ${t("scheme.source.copied", { date: fetched })}` : ""}
      </p>
      <a
        href={scheme.source_url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline"
      >
        {t("scheme.source.open")}
        <ExternalLink className="size-3.5" />
      </a>
      {scheme.official_url ? (
        <a
          href={scheme.official_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline"
        >
          {t("scheme.source.official")}
          <ExternalLink className="size-3.5" />
        </a>
      ) : null}
      <p className="mt-4 border-t border-border pt-3 text-xs leading-relaxed text-muted-foreground">
        {t("scheme.source.confirm")}
      </p>
    </div>
  );
}

function NotYetFetched({ scheme, t }: { scheme: SchemeDetail; t: Translate }) {
  return (
    <div className="rounded-xl border border-dashed border-border p-8">
      <FileText className="size-6 text-muted-foreground" />
      <h2 className="mt-3 font-semibold">{t("scheme.partial.title")}</h2>
      <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted-foreground">
        {t("scheme.partial.body")}
      </p>
      <ButtonLink
        href={scheme.source_url}
        external
        variant="outline"
        className="mt-5 h-10"
      >
        {t("scheme.partial.cta")}
        <ExternalLink className="size-4" />
      </ButtonLink>
    </div>
  );
}
