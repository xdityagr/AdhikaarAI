"use client";

import { useState } from "react";
import { Check, Languages } from "lucide-react";

import { LANGUAGE_META, useLanguage } from "@/components/language-provider";
import { LANGS, type Lang } from "@/lib/i18n/config";
import { cn } from "@/lib/utils";

/**
 * Languages are listed in their own script — never "Hindi", always "हिन्दी".
 * Someone who reads only Hindi cannot find "Hindi" in a list, which makes an
 * English-labelled language menu useless to exactly the person who needs it.
 */
export function LanguageSwitcher({ className }: { className?: string }) {
  const { lang, setLang, t, switching } = useLanguage();
  const [open, setOpen] = useState(false);

  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={t("lang.change")}
        disabled={switching}
        /* Quiet on purpose. There is one button in the header and it is "find
           my schemes"; a second pill beside it makes the reader choose between
           two things that are not comparable. */
        className="flex h-9 items-center gap-1.5 rounded-full px-3 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground disabled:opacity-60"
      >
        <Languages className="size-4" />
        <span className="hidden sm:inline">{LANGUAGE_META[lang].native}</span>
      </button>

      {open ? (
        <>
          {/* Tapping anywhere else closes it — a menu with no way out is a trap
              on a phone, where there is no Escape key in reach. */}
          <div
            className="fixed inset-0 z-40"
            aria-hidden
            onClick={() => setOpen(false)}
          />
          <ul
            role="listbox"
            className="absolute end-0 z-50 mt-2 max-h-[70vh] w-48 overflow-y-auto rounded-2xl border border-border bg-card py-1.5 shadow-[0_1px_2px_rgb(28_26_23/0.04),0_24px_56px_-24px_rgb(28_26_23/0.28)]"
          >
            {(LANGS as readonly Lang[]).map((code) => (
              <li key={code}>
                <button
                  type="button"
                  role="option"
                  aria-selected={code === lang}
                  lang={code}
                  onClick={() => {
                    setLang(code);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between px-3.5 py-2.5 text-start text-sm transition-colors hover:bg-accent",
                    code === lang && "font-medium text-primary",
                  )}
                >
                  <span>{LANGUAGE_META[code].native}</span>
                  {code === lang ? <Check className="size-4" /> : null}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
