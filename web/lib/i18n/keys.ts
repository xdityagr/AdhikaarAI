/**
 * Every string key in the interface.
 *
 * Derived from the English locale, which is the only one required to be
 * complete: `t()` falls back to English, so a language may be added a few
 * strings at a time without ever showing a raw key to a person.
 */

import { en } from "@/lib/i18n/locales/en";

export type StringKey = keyof typeof en;

/** A locale need not be complete; what it does carry must be a real key. */
export type Strings = Partial<Record<StringKey, string>>;

export { en };
