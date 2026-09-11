"use client";

import { useState } from "react";
import { ChevronDown, SlidersHorizontal } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { cn } from "@/lib/utils";

/**
 * Filters: a sidebar on a desktop, a collapsed drawer on a phone.
 *
 * Left expanded on a small screen, this column pushes the actual results a
 * full screen down — someone on a phone scrolls past fifteen categories and
 * twelve states before seeing a single scheme, and concludes there are none.
 */
export function FilterDisclosure({
  activeCount,
  children,
}: {
  activeCount: number;
  children: React.ReactNode;
}) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between rounded-lg border border-border bg-card px-4 py-3 text-sm font-semibold lg:hidden"
      >
        <span className="flex items-center gap-2">
          <SlidersHorizontal className="size-4" />
          {t("schemes.filter")}
          {activeCount > 0 ? (
            <span className="rounded-full bg-primary px-2 py-0.5 text-xs font-bold text-primary-foreground">
              {activeCount}
            </span>
          ) : null}
        </span>
        <ChevronDown
          className={cn("size-4 transition-transform", open && "rotate-180")}
        />
      </button>

      <h2 className="hidden items-center gap-2 text-sm font-semibold lg:flex">
        <SlidersHorizontal className="size-4" />
        {t("schemes.filter")}
      </h2>

      <div className={cn(open ? "block" : "hidden", "lg:block")}>{children}</div>
    </div>
  );
}
