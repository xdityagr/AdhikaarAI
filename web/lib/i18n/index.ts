import { type Lang } from "@/lib/i18n/config";
import { en } from "@/lib/i18n/locales/en";
import { hi } from "@/lib/i18n/locales/hi";
import { bn } from "@/lib/i18n/locales/bn";
import { mr } from "@/lib/i18n/locales/mr";
import { ta } from "@/lib/i18n/locales/ta";
import { te } from "@/lib/i18n/locales/te";
import { gu } from "@/lib/i18n/locales/gu";
import { kn } from "@/lib/i18n/locales/kn";
import { ml } from "@/lib/i18n/locales/ml";
import { pa } from "@/lib/i18n/locales/pa";
import { or } from "@/lib/i18n/locales/or";
import { as } from "@/lib/i18n/locales/as";
import { ur } from "@/lib/i18n/locales/ur";
import type { Strings, StringKey } from "@/lib/i18n/keys";

export type { StringKey };
export * from "@/lib/i18n/config";

const LOCALES: Record<Lang, Strings> = {
  en, hi, bn, mr, ta, te, gu, kn, ml, pa, or, as, ur,
};

/**
 * One string, in one language.
 *
 * Falls back to English rather than to the key. A language may therefore be
 * added a few strings at a time: an untranslated line reads as an English
 * sentence someone can still act on, never as `results.h1.targeted`.
 */
export function t(
  lang: Lang,
  key: StringKey,
  vars?: Record<string, string | number>,
): string {
  let text: string = LOCALES[lang]?.[key] ?? en[key] ?? key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replaceAll(`{${name}}`, String(value));
    }
  }
  return text;
}

/** A `t` bound to one language, for components that render many strings. */
export function translator(lang: Lang): Translate {
  return (key: StringKey, vars?: Record<string, string | number>) =>
    t(lang, key, vars);
}

/** The bound translator's type, so it can be passed to a child component. */
export type Translate = (
  key: StringKey,
  vars?: Record<string, string | number>,
) => string;

/** How complete a locale is — surfaced in the switcher, not hidden. */
export function coverage(lang: Lang): number {
  const total = Object.keys(en).length;
  const have = Object.keys(LOCALES[lang] ?? {}).length;
  return total === 0 ? 1 : have / total;
}

/**
 * Numbers in the Indian grouping system (1,20,000 — not 120,000).
 *
 * Latin digits everywhere on purpose: government forms, bank passbooks and SMS
 * from a bank all use them, so a figure shown in Devanagari or Bengali numerals
 * would not match the paper the reader is holding.
 */
export function formatNumber(lang: Lang, value: number): string {
  return new Intl.NumberFormat(`${lang}-IN`, {
    numberingSystem: "latn",
  }).format(value);
}
