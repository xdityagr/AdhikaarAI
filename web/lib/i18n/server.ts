import { cookies, headers } from "next/headers";

import {
  DEFAULT_LANG,
  isLang,
  LANG_COOKIE,
  languageFromAcceptHeader,
  PLACE_COOKIE,
  type Lang,
} from "@/lib/i18n/config";
import { translator } from "@/lib/i18n";

/**
 * The language for this request.
 *
 * Order matters, and it is an order of increasing presumption:
 *
 * 1. The cookie — an explicit choice, which nothing may override.
 * 2. `Accept-Language` — not a choice about this site, but a real choice the
 *    person made about their phone. It costs them no permission prompt and no
 *    request, and it is the signal most likely to be right.
 * 3. English.
 *
 * Location never appears here. Where someone is standing says less about what
 * they read than their own device settings do, and a page that silently
 * switches language on them is worse than one that stays in English — so
 * location only ever produces a suggestion they can decline.
 */
export async function getLang(): Promise<Lang> {
  const store = await cookies();
  const chosen = store.get(LANG_COOKIE)?.value;
  if (isLang(chosen)) return chosen;

  const header = (await headers()).get("accept-language");
  return languageFromAcceptHeader(header) ?? DEFAULT_LANG;
}

/** Whether the language came from a choice, or was merely inferred. */
export async function langWasChosen(): Promise<boolean> {
  const store = await cookies();
  return isLang(store.get(LANG_COOKIE)?.value);
}

/**
 * The state this person told us they are in, if they have.
 *
 * Read on the server so the wizard arrives already filled in rather than
 * filling itself in after a repaint — and so someone who answered the question
 * once never answers it again.
 */
export async function getPlace(): Promise<string | null> {
  const store = await cookies();
  const value = store.get(PLACE_COOKIE)?.value;
  return value ? decodeURIComponent(value) : null;
}

/** `const t = await getT()` inside a server component. */
export async function getT() {
  return translator(await getLang());
}
