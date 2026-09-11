"use client";

import { useLanguage } from "@/components/language-provider";
import type { Option } from "@/lib/facets";
import type { StringKey } from "@/lib/i18n/keys";
import { cn } from "@/lib/utils";

/**
 * A row of tappable answers.
 *
 * Buttons rather than a dropdown because the options are visible without a
 * tap, the targets are large enough for a thumb, and there is no hidden state
 * on a small screen. Selecting the chosen option again clears it — the answer
 * has to be retractable, since "I'd rather not say" is a legitimate answer to
 * every question here.
 */
export function OptionRow({
  label,
  options,
  value,
  onSelect,
  className,
}: {
  label: string;
  options: Option[];
  value?: string;
  onSelect: (value: string) => void;
  className?: string;
}) {
  const { t } = useLanguage();
  return (
    <div className={className}>
      <p className="text-sm font-medium">{label}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {options.map((option) => {
          const active = value === option.value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={active}
              onClick={() => onSelect(option.value)}
              className={cn(
                "rounded-lg border px-3.5 py-2 text-sm font-medium transition-colors",
                active
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-card text-foreground hover:border-primary/40 hover:bg-accent",
              )}
            >
              {t(option.key as StringKey)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
