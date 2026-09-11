/**
 * Language configuration, shared by server and client.
 *
 * The set is not arbitrary. myScheme — the Government of India's own scheme
 * portal — publishes official translations of scheme text in fourteen Indian
 * languages, verified against the API rather than assumed. Every language here
 * is one where a person reads the *scheme itself* in their language, not just
 * our buttons; offering an interface in a language whose scheme text we could
 * only show in English would be a hollow kind of support.
 *
 * The chosen language lives in a cookie rather than only in localStorage,
 * because most of this site is rendered on the server. A preference the server
 * cannot read would leave every page arriving in English and flipping a moment
 * later.
 */

export const LANGS = [
  "en", "hi", "bn", "mr", "te", "ta", "gu", "kn", "ml", "pa", "or", "as", "ur",
] as const;

export type Lang = (typeof LANGS)[number];

export interface LanguageMeta {
  /** The English name, for developers and for `lang` attributes. */
  name: string;
  /** How the language names itself. This is what a reader is shown. */
  native: string;
  /** Urdu is written right to left; everything else here is not. */
  dir: "ltr" | "rtl";
}

export const LANGUAGE_META: Record<Lang, LanguageMeta> = {
  en: { name: "English", native: "English", dir: "ltr" },
  hi: { name: "Hindi", native: "हिन्दी", dir: "ltr" },
  bn: { name: "Bengali", native: "বাংলা", dir: "ltr" },
  mr: { name: "Marathi", native: "मराठी", dir: "ltr" },
  te: { name: "Telugu", native: "తెలుగు", dir: "ltr" },
  ta: { name: "Tamil", native: "தமிழ்", dir: "ltr" },
  gu: { name: "Gujarati", native: "ગુજરાતી", dir: "ltr" },
  kn: { name: "Kannada", native: "ಕನ್ನಡ", dir: "ltr" },
  ml: { name: "Malayalam", native: "മലയാളം", dir: "ltr" },
  pa: { name: "Punjabi", native: "ਪੰਜਾਬੀ", dir: "ltr" },
  or: { name: "Odia", native: "ଓଡ଼ିଆ", dir: "ltr" },
  as: { name: "Assamese", native: "অসমীয়া", dir: "ltr" },
  ur: { name: "Urdu", native: "اردو", dir: "rtl" },
};

export const LANG_COOKIE = "adhikaar_lang";

/** Set when a suggestion has been shown and dismissed, so it is not repeated. */
export const LANG_PROMPT_COOKIE = "adhikaar_lang_asked";

/** The state we learned, remembered so we ask once and pre-fill everywhere. */
export const PLACE_COOKIE = "adhikaar_state";
/** Set when the location question has been answered or skipped. */
export const PLACE_ASKED_COOKIE = "adhikaar_state_asked";

export const DEFAULT_LANG: Lang = "en";

export function isLang(value: unknown): value is Lang {
  return typeof value === "string" && (LANGS as readonly string[]).includes(value);
}

/** The remembered state, read in the browser. Server code uses getPlace(). */
export function readPlaceCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|; )${PLACE_COOKIE}=([^;]*)`),
  );
  return match ? decodeURIComponent(match[1]) : null;
}

export function dirFor(lang: Lang): "ltr" | "rtl" {
  return LANGUAGE_META[lang].dir;
}

/* ---------------------------------------------------------------------------
 * Where someone is, and what they most likely read.
 *
 * State language policy, not ethnography: this is the language a state
 * government actually publishes and administers in, which is the language its
 * scheme forms and its counter staff will use. It is a *suggestion* only — a
 * Tamil speaker in Delhi and a Hindi speaker in Chennai both exist, so this
 * never overrides a choice and never switches anything silently.
 *
 * States whose principal language we cannot show scheme text in — Manipuri,
 * Khasi, Mizo, Nagamese, Nepali, Konkani — are deliberately absent rather than
 * mapped to a neighbour's language. Guessing wrong there is worse than not
 * guessing: it tells someone this product has decided what they speak.
 * ------------------------------------------------------------------------- */

export const STATE_LANGUAGE: Record<string, Lang> = {
  "Andhra Pradesh": "te",
  Telangana: "te",
  Assam: "as",
  Bihar: "hi",
  Chhattisgarh: "hi",
  Delhi: "hi",
  Haryana: "hi",
  "Himachal Pradesh": "hi",
  Jharkhand: "hi",
  "Madhya Pradesh": "hi",
  Rajasthan: "hi",
  "Uttar Pradesh": "hi",
  Uttarakhand: "hi",
  Gujarat: "gu",
  "Dadra & Nagar Haveli and Daman & Diu": "gu",
  Karnataka: "kn",
  Kerala: "ml",
  Lakshadweep: "ml",
  Maharashtra: "mr",
  Goa: "mr",
  Odisha: "or",
  Punjab: "pa",
  Chandigarh: "pa",
  "Tamil Nadu": "ta",
  Puducherry: "ta",
  "West Bengal": "bn",
  Tripura: "bn",
  "Andaman and Nicobar Islands": "bn",
  "Jammu and Kashmir": "ur",
};

/** The language a state administers in, if we can show scheme text in it. */
export function languageForState(state: string | null | undefined): Lang | null {
  if (!state) return null;
  const exact = STATE_LANGUAGE[state.trim()];
  if (exact) return exact;
  const wanted = state.trim().toLowerCase();
  for (const [name, lang] of Object.entries(STATE_LANGUAGE)) {
    if (name.toLowerCase() === wanted) return lang;
  }
  return null;
}

/**
 * The best supported language from an Accept-Language header.
 *
 * Used only when no choice has been made. It costs the reader nothing — no
 * permission prompt, no request — and it is the signal most likely to be right,
 * because it is the language they already chose for their phone.
 */
export function languageFromAcceptHeader(header: string | null): Lang | null {
  if (!header) return null;
  const ranked = header
    .split(",")
    .map((part) => {
      const [tag, ...params] = part.trim().split(";");
      const q = params
        .map((p) => p.trim())
        .find((p) => p.startsWith("q="));
      return { tag: tag.trim().toLowerCase(), q: q ? Number(q.slice(2)) : 1 };
    })
    .filter((entry) => entry.tag && !Number.isNaN(entry.q))
    .sort((a, b) => b.q - a.q);

  for (const { tag } of ranked) {
    const base = tag.split("-")[0];
    if (isLang(base)) return base;
  }
  return null;
}
