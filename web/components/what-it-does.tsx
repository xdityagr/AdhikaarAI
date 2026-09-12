import Link from "next/link";
import {
  ArrowRight, BellRing, ScrollText, Users, UserRoundCheck,
} from "lucide-react";

import { Reveal } from "@/components/reveal";
import type { Translate } from "@/lib/i18n";

/**
 * What the product can do now, said plainly and in its own voice.
 *
 * The landing page proves ONE thing very well — a real match, with real
 * figures, for a real profile. Four capabilities had landed since and were
 * reachable only by knowing the URL: a household view, the rules read out of
 * scheme prose, the change alerts, and help at a counter.
 *
 * Its own section rather than more cards in the hero, deliberately. The hero
 * earns attention with a single claim and one action; a grid of features up
 * there competes with that claim and wins nothing. This sits after the proof,
 * where somebody who is still reading has already decided the thing works and
 * is asking what else it does.
 *
 * COLOUR CARRIES MEANING HERE, NOT DECORATION
 *
 * The accent on each card is the one that already means that thing elsewhere
 * in the product: `verified` green for a household's confirmed entitlements,
 * `gold` for the rules read out of prose (the same amber the interface uses
 * for "worth checking"), `clay` for an alert, and `forest` for the counter.
 * A reader who has used the eligibility page has already learned them.
 */

interface Capability {
  key: string;
  href: string;
  icon: typeof Users;
  /** Tailwind classes for the icon chip. One accent from the palette each. */
  chip: string;
}

const CAPABILITIES: Capability[] = [
  {
    key: "household",
    href: "/household",
    icon: Users,
    chip: "bg-verified-soft text-verified",
  },
  {
    key: "rules",
    href: "/schemes",
    icon: ScrollText,
    chip: "bg-gold-soft text-gold-ink",
  },
  {
    key: "alerts",
    href: "/chat",
    icon: BellRing,
    chip: "bg-clay-soft text-clay",
  },
  {
    key: "counter",
    href: "/check",
    icon: UserRoundCheck,
    chip: "bg-secondary text-primary",
  },
];

export function WhatItDoes({ t }: { t: Translate }) {
  return (
    <section className="border-t border-border bg-card/60">
      <div className="mx-auto max-w-6xl px-5 py-20 sm:px-6 sm:py-28">
        <Reveal as="header" className="mx-auto max-w-[62ch] text-center">
          <h2 className="text-[1.75rem] sm:text-[2.5rem]">
            {t("home.does.h2")}
          </h2>
          <p className="mx-auto mt-4 max-w-[56ch] text-[1.0625rem] leading-relaxed text-muted-foreground">
            {t("home.does.lede")}
          </p>
        </Reveal>

        <ul className="mt-12 grid gap-4 sm:mt-14 sm:grid-cols-2">
          {CAPABILITIES.map((capability, index) => {
            const Icon = capability.icon;
            return (
              <Reveal
                as="li"
                key={capability.key}
                delay={60 + index * 60}
                className="group card-quiet relative flex flex-col p-6 transition-colors hover:border-primary/40 sm:p-7"
              >
                <span
                  className={`flex size-11 shrink-0 items-center justify-center rounded-xl ${capability.chip}`}
                >
                  <Icon className="size-5" />
                </span>

                <h3 className="mt-5 font-display text-[1.1875rem] font-normal leading-snug">
                  <Link href={capability.href}>
                    {/* Covers the whole card, so the target is the card and
                        not a six-word link on a phone. */}
                    <span className="absolute inset-0" aria-hidden />
                    {t(`home.does.${capability.key}.title` as never)}
                  </Link>
                </h3>

                <p className="mt-2.5 flex-1 text-[0.9375rem] leading-relaxed text-muted-foreground">
                  {t(`home.does.${capability.key}.body` as never)}
                </p>

                <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-medium text-primary">
                  {t(`home.does.${capability.key}.cta` as never)}
                  <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Reveal>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
