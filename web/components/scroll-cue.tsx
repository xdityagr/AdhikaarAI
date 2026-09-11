"use client";

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { cn } from "@/lib/utils";

/**
 * Two small things at the bottom of the front page.
 *
 * A hint that there is more, and a soft edge so whatever is halfway down the
 * fold dissolves instead of being guillotined. A table sliced through the
 * middle by the bottom of the screen reads as a rendering fault; the same
 * table fading out reads as a page that continues.
 *
 * Both disappear once they have done their job: the hint the moment you
 * scroll at all, the fade when there is nothing left below to suggest.
 */
export function ScrollCue() {
  const { t } = useLanguage();
  const [atTop, setAtTop] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      setAtTop(window.scrollY < 40);
      const remaining =
        document.documentElement.scrollHeight -
        window.scrollY -
        window.innerHeight;
      setAtEnd(remaining < 120);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  return (
    <>
      <div
        aria-hidden
        className={cn(
          "pointer-events-none fixed inset-x-0 bottom-0 z-30 h-28 bg-gradient-to-t from-paper via-paper/75 to-transparent transition-opacity duration-500",
          atEnd ? "opacity-0" : "opacity-100",
        )}
      />
      <div
        aria-hidden
        className={cn(
          "pointer-events-none fixed inset-x-0 bottom-7 z-40 flex justify-center transition-opacity duration-500",
          atTop ? "opacity-100" : "opacity-0",
        )}
      >
        <span className="flex flex-col items-center gap-1.5 text-[0.8125rem] text-faint">
          {t("home.scroll")}
          <ChevronDown className="size-4 animate-bounce" />
        </span>
      </div>
    </>
  );
}
