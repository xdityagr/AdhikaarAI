"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

import {
  DEFAULT_LANG,
  LANG_COOKIE,
  LANGUAGE_META,
  type Lang,
} from "@/lib/i18n/config";
import { translator } from "@/lib/i18n";
import type { StringKey } from "@/lib/i18n/keys";

export { LANGUAGE_META };

interface LanguageValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  switching: boolean;
  t: (key: StringKey, vars?: Record<string, string | number>) => string;
}

const LanguageContext = createContext<LanguageValue>({
  lang: DEFAULT_LANG,
  setLang: () => {},
  switching: false,
  t: translator(DEFAULT_LANG),
});

export function useLanguage() {
  return useContext(LanguageContext);
}

/**
 * The chosen language, seeded by the server.
 *
 * The value arrives as a prop from the root layout, which read it from the
 * cookie — so the first paint is already in the right language and there is no
 * flicker.
 *
 * Changing it reloads the document rather than calling router.refresh(). That
 * looks heavy-handed and is not: refresh() only invalidates the route you are
 * standing on, so the moment you switched language and then navigated to the
 * scheme catalogue, Next served the payload it had already cached under the
 * previous cookie. The result was a page whose nav and filters were in Hindi
 * and whose heading was still in English — the language appearing to half
 * apply, which is worse than it not applying at all.
 *
 * A reload drops the router cache entirely, so every server-rendered page on
 * the site comes back in the new language. It happens once, on a deliberate
 * choice someone makes at most a handful of times.
 */
export function LanguageProvider({
  lang,
  children,
}: {
  lang: Lang;
  children: React.ReactNode;
}) {
  const [switching, setSwitching] = useState(false);

  const setLang = useCallback((next: Lang) => {
    // A year, because someone who has chosen once should not choose again.
    document.cookie = `${LANG_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = next;
    setSwitching(true);
    window.location.reload();
  }, []);

  const value = useMemo<LanguageValue>(
    () => ({ lang, setLang, switching, t: translator(lang) }),
    [lang, setLang, switching],
  );

  return (
    <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
  );
}
