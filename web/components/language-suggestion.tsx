"use client";

import { useCallback, useEffect, useState } from "react";
import { Languages, X } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";
import {
  LANGUAGE_META,
  LANG_PROMPT_COOKIE,
  languageForState,
  type Lang,
} from "@/lib/i18n/config";
import { t as translate } from "@/lib/i18n";

/**
 * "Would you rather read this in Odia?"
 *
 * Offered, never applied. When someone shares their location or types a PIN
 * code we learn which state they are in, and a state tells us what its own
 * government publishes and administers in — but it does not tell us what this
 * particular person reads. A Tamil speaker in Delhi and a Hindi speaker in
 * Chennai both exist, and silently switching the page under either of them is
 * worse than leaving it alone.
 *
 * So this is a bar with a yes and a no, written in the language being offered,
 * because a prompt in a language you cannot read is not a prompt. Declining is
 * remembered: nobody should be asked twice.
 */
export function LanguageSuggestion() {
  const { lang, setLang } = useLanguage();
  const [suggested, setSuggested] = useState<Lang | null>(null);

  const dismiss = useCallback((remember: boolean) => {
    setSuggested(null);
    if (remember) {
      document.cookie = `${LANG_PROMPT_COOKIE}=1; path=/; max-age=31536000; samesite=lax`;
    }
  }, []);

  useEffect(() => {
    const alreadyAsked = document.cookie.includes(`${LANG_PROMPT_COOKIE}=1`);

    const onPlace = (event: Event) => {
      if (alreadyAsked) return;
      const state = (event as CustomEvent<{ state?: string }>).detail?.state;
      const candidate = languageForState(state);
      // Nothing to offer if we cannot place the state, or they are already
      // reading in that language.
      if (!candidate || candidate === lang) return;
      setSuggested(candidate);
    };

    window.addEventListener("yojnasetu:place", onPlace);
    return () => window.removeEventListener("yojnasetu:place", onPlace);
  }, [lang]);

  if (!suggested) return null;

  const meta = LANGUAGE_META[suggested];

  return (
    <div
      dir={meta.dir}
      lang={suggested}
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-card p-4 shadow-lg sm:inset-x-auto sm:bottom-5 sm:left-5 sm:max-w-sm sm:rounded-xl sm:border"
      role="status"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
          <Languages className="size-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-relaxed">
            {translate(suggested, "lang.suggest", { language: meta.native })}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              className="h-9 px-4"
              onClick={() => {
                setLang(suggested);
                dismiss(true);
              }}
            >
              {translate(suggested, "lang.suggest.yes")}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-9 px-4"
              onClick={() => dismiss(true)}
            >
              {translate(suggested, "lang.suggest.no")}
            </Button>
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="size-8 shrink-0"
          onClick={() => dismiss(true)}
          aria-label={translate(suggested, "lang.suggest.no")}
        >
          <X className="size-4" />
        </Button>
      </div>
    </div>
  );
}

/**
 * Announce a place the interface has just learned.
 *
 * An event rather than shared state because the two things that discover a
 * location — the wizard and the credit form — are unrelated to the thing that
 * reacts to it, and neither should have to know the suggestion bar exists.
 */
export function announcePlace(state: string | null | undefined): void {
  if (!state) return;
  window.dispatchEvent(
    new CustomEvent("yojnasetu:place", { detail: { state } }),
  );
}
