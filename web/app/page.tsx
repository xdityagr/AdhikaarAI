import { ArrowRight } from "lucide-react";

import { CategoryGrid } from "@/components/category-grid";
import { Marked } from "@/components/marked";
import { Ornament } from "@/components/ornament";
import { Reveal } from "@/components/reveal";
import { ScrollCue } from "@/components/scroll-cue";
import { WhatsAppDoor, WhatsAppQrPanel } from "@/components/whatsapp-door";
import { ButtonLink } from "@/components/ui/button-link";
import { getCatalogMeta } from "@/lib/api";
import { formatNumber } from "@/lib/i18n";
import { getLang } from "@/lib/i18n/server";
import { translator } from "@/lib/i18n";

type T = ReturnType<typeof translator>;

export default async function HomePage() {
  const [meta, lang] = await Promise.all([getCatalogMeta(), getLang()]);
  const t = translator(lang);
  const count = formatNumber(lang, meta.total || 4736);

  return (
    <>
      {/* ---------------------------------------------------------------- Hero
          Centred, light and unhurried. The whole composition is one column so
          it reads identically at 380px and 1400px — this page is opened on a
          phone far more often than it is opened on anything else. */}
      {/* Left-aligned on a phone, centred from `sm` up. Centring a headline, a
          lede and an eyebrow on the same narrow measure gives all three the
          same silhouette, and the page arrives as one block of centred text
          with no way in. Ranged left, the size ramp does the work instead. */}
      <section className="motion-stagger mx-auto flex min-h-[calc(100svh-4rem)] max-w-6xl flex-col justify-center px-5 pt-10 pb-28 text-start sm:px-6 sm:pb-32 sm:text-center">
        <Ornament className="h-5 w-36 opacity-70 sm:mx-auto sm:h-6 sm:w-44 sm:opacity-75" />

        <p className="mt-6 text-[0.8125rem] font-medium text-leaf sm:text-sm">
          {t("home.eyebrow")}
        </p>

        <h1 className="mt-3 text-balance text-[2.625rem] sm:mx-auto sm:mt-5 sm:max-w-[20ch] sm:text-[3.25rem] lg:text-[4.125rem]">
          <Marked text={t("home.h1")} />
        </h1>

        <p className="mt-5 max-w-[42ch] text-[1rem] leading-relaxed text-muted-foreground sm:mx-auto sm:mt-6 sm:max-w-[56ch] sm:text-lg">
          {t("home.lede", { count })}
        </p>

        <div className="mt-8 flex flex-col items-stretch gap-2.5 sm:mt-9 sm:flex-row sm:items-center sm:justify-center sm:gap-3">
          <ButtonLink href="/check" size="pill-lg" className="font-medium">
            {t("home.cta.primary")}
            <ArrowRight className="nudge size-4" />
          </ButtonLink>
          <WhatsAppDoor size="pill-lg" />
        </div>

        <p className="mt-5 text-[0.8125rem] leading-relaxed text-faint">
          {t("home.reassurance")}
        </p>
      </section>

      {/* --------------------------------------------------------------- Proof
          Not a card. A card here would sit on the page like a dashboard widget
          dropped into a poster — which is exactly what it looked like before.
          It is a ruled record instead: hairlines, tabular figures, air, and
          nothing boxed inside anything else. */}
      <Reveal>
        <ProofRecord t={t} />
      </Reveal>
      <ScrollCue />

      {/* ------------------------------------------------------------- Sources */}
      <Reveal as="section" className="mx-auto max-w-6xl px-5 pt-20 pb-4 text-center sm:px-6 sm:pt-24">
        <p className="meta">{t("home.sources")}</p>
        <ul className="mt-5 flex flex-wrap items-center justify-center gap-x-10 gap-y-3 font-display text-base font-normal text-faint">
          {["NSFDC", "NBCFDC", "NSKFDC", "myScheme", "MoSJE"].map((name) => (
            <li key={name}>{name}</li>
          ))}
        </ul>
      </Reveal>

      {/* ----------------------------------------------------------- The asking */}
      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-6 sm:py-28">
        <Reveal as="header" className="mx-auto max-w-[62ch] text-center">
          <h2 className="text-[1.75rem] sm:text-[2.5rem]">{t("home.ask.h2")}</h2>
          <p className="mt-4 text-[1.0625rem] leading-relaxed text-muted-foreground">
            {t("home.ask.lede")}
          </p>
        </Reveal>
        <Reveal delay={80}>
          <ConversationPreview t={t} />
        </Reveal>
        <div className="mt-8 flex justify-center">
          <ButtonLink href="/chat" variant="outline" size="pill" className="bg-card">
            {t("home.ask.cta")}
            <ArrowRight className="nudge size-4" />
          </ButtonLink>
        </div>
      </section>

      {/* ------------------------------------------------------------ Categories */}
      <section className="border-t border-border bg-card/60">
        <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6 sm:py-24">
          <Reveal as="header" className="mx-auto max-w-[62ch] text-center">
            <h2 className="text-[1.75rem] sm:text-[2.5rem]">{t("home.cats.h2")}</h2>
            <p className="mt-4 text-[1.0625rem] leading-relaxed text-muted-foreground">
              {t("home.cats.lede")}
            </p>
          </Reveal>
          <Reveal delay={80}>
            <CategoryGrid categories={meta.categories} className="mt-12" />
          </Reveal>
          <div className="mt-10 flex justify-center">
            <ButtonLink href="/schemes" variant="outline" size="pill" className="bg-card">
              {t("home.cats.cta", { count })}
              <ArrowRight className="nudge size-4" />
            </ButtonLink>
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------------- WhatsApp */}
      <section className="mx-auto max-w-6xl px-5 py-20 sm:px-6 sm:py-24">
        <Reveal className="relative overflow-hidden rounded-[1.75rem] bg-forest-deep px-7 py-11 text-[#dcede4] sm:px-12 sm:py-14">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_80%_at_88%_18%,rgba(122,222,168,0.14),transparent_62%)]"
          />
          <div className="relative flex flex-col items-start gap-9 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-[46ch]">
              <h2 className="text-[1.75rem] text-white sm:text-[2.125rem]">
                {t("home.wa.h2")}
              </h2>
              <p className="mt-4 text-[0.9375rem] leading-relaxed text-[#9ebfb0] sm:text-base">
                {t("home.wa.body")}
              </p>
              <WhatsAppDoor
                size="pill-lg"
                variant="soft"
                className="mt-7 bg-[#7adea8] text-[#052b1b] hover:bg-[#6cd39c]"
              />
            </div>
            <WhatsAppQrPanel className="shrink-0 self-center lg:self-auto" />
          </div>
        </Reveal>
      </section>

      {/* ------------------------------------------------------------------ CTA */}
      <section className="border-t border-border">
        <Reveal className="mx-auto max-w-6xl px-5 py-20 text-center sm:px-6 sm:py-24">
          <h2 className="mx-auto max-w-[18ch] text-[1.75rem] sm:text-[2.5rem]">
            {t("home.final.h2")}
          </h2>
          <p className="mx-auto mt-4 max-w-[56ch] text-[1.0625rem] leading-relaxed text-muted-foreground">
            {t("home.final.body")}
          </p>
          <div className="mt-8 flex justify-center">
            <ButtonLink href="/check" size="pill-lg" className="font-medium">
              {t("home.final.cta")}
              <ArrowRight className="nudge size-4" />
            </ButtonLink>
          </div>
        </Reveal>
      </section>
    </>
  );
}

/**
 * One real result, before anyone has typed anything.
 *
 * The figures are the ones the engine actually produces for this profile, and
 * the number given the most room is not the loan — it is what the loan saves
 * against the moneylender. That difference is the entire argument this product
 * makes, so it is set at display size and everything else is set around it.
 */
function ProofRecord({ t }: { t: T }) {
  return (
    <section className="mx-auto max-w-5xl px-5 sm:px-6">
      <div className="border-t border-border pt-10">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <p className="text-[0.8125rem] text-faint">{t("home.proof.who")}</p>
          <p className="rounded-full bg-mint px-3 py-1 text-[0.8125rem] font-medium text-leaf">
            {t("home.proof.matched")}
          </p>
        </div>

        <div className="mt-9 grid gap-x-14 gap-y-12 md:grid-cols-[1.15fr_0.85fr]">
          <div>
            <h2 className="font-display text-[1.625rem] font-normal tracking-[-0.02em] sm:text-[1.875rem]">
              Micro Finance Scheme
            </h2>
            <p className="mt-1.5 text-[0.9375rem] text-muted-foreground">
              {t("home.proof.terms")}
            </p>

            <dl className="mt-8">
              {[
                { k: t("home.proof.quarter"), v: "₹12,568", tone: "" },
                { k: t("home.proof.interest"), v: "₹17,272", tone: "" },
                { k: t("home.proof.moneylender"), v: "₹1,08,000", tone: "text-clay" },
              ].map((row) => (
                <div
                  key={row.k}
                  className={`flex items-baseline justify-between gap-6 border-t border-border py-3.5 text-[0.9375rem] ${row.tone}`}
                >
                  <dt>{row.k}</dt>
                  <dd className="tnum shrink-0 font-medium">{row.v}</dd>
                </div>
              ))}
            </dl>
          </div>

          <div>
            <p className="meta">{t("home.proof.keepLabel")}</p>
            <p className="tnum mt-2 font-display text-[2.75rem] font-light leading-none tracking-[-0.03em] text-leaf">
              ₹90,728
            </p>
            <p className="mt-3.5 text-[0.9375rem] leading-relaxed text-muted-foreground">
              {t("home.proof.keepBody")}
            </p>
            <div className="mt-6 border-t border-border pt-5">
              <p className="meta">{t("home.proof.whereLabel")}</p>
              <p className="mt-2 text-[0.9375rem] leading-relaxed">
                {t("home.proof.whereBody")}
              </p>
            </div>
          </div>
        </div>

        <p className="mt-12 border-t border-border pt-5 text-[0.8125rem] text-faint">
          {t("home.proof.caption")}
        </p>
      </div>
    </section>
  );
}

/**
 * What the assistant looks like when it answers.
 *
 * Shown rather than described, because "ask in your own language" is a claim
 * and a Hindi question with a rupee table under it is evidence. The figures
 * repeat the ones above on purpose: the same loan, the same answer, whichever
 * door you came in through.
 */
function ConversationPreview({ t }: { t: T }) {
  return (
    <div className="card-quiet mx-auto mt-12 max-w-3xl overflow-hidden">
      <div className="flex flex-col gap-4 p-5 sm:p-7">
        <p className="max-w-[85%] self-end rounded-[1.125rem] rounded-ee-md bg-primary px-4 py-3 text-[0.9375rem] leading-relaxed text-primary-foreground sm:max-w-[70%]">
          {t("home.ask.q")}
        </p>

        <div className="max-w-full self-start">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-verified-soft px-3 py-1 text-[0.75rem] font-semibold text-verified">
            {t("home.ask.badge")}
          </span>
          <p className="mt-3 text-[0.9375rem] leading-relaxed">{t("home.ask.a")}</p>

          <dl className="mt-4 overflow-hidden rounded-xl border border-border">
            <p className="meta border-b border-border bg-muted/60 px-4 py-2.5">
              {t("home.ask.card")}
            </p>
            {[
              { k: t("home.ask.instalment"), v: "₹12,568", tone: "" },
              { k: t("home.ask.interest"), v: "₹17,272", tone: "" },
              {
                k: t("home.ask.moneylender"),
                v: "₹1,08,000",
                tone: "bg-clay-soft text-clay",
              },
            ].map((row) => (
              <div
                key={row.k}
                className={`flex items-baseline justify-between gap-4 border-b border-border px-4 py-3 text-[0.9375rem] last:border-b-0 ${row.tone}`}
              >
                <dt>{row.k}</dt>
                <dd className="tnum shrink-0 font-medium">{row.v}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}
