import Link from "next/link";
import { ChevronDown, X } from "lucide-react";

import type { CatalogMeta } from "@/lib/api";
import type { Lang } from "@/lib/i18n/config";
import type { Translate } from "@/lib/i18n";
import { categoryLabel, levelLabel } from "@/lib/i18n/vocabulary";
import { cn } from "@/lib/utils";

interface Active {
  q?: string;
  category?: string;
  state?: string;
  level?: string;
}

function hrefWith(active: Active, key: keyof Active, value?: string): string {
  const query = new URLSearchParams();
  const next = { ...active, [key]: value };
  for (const [k, v] of Object.entries(next)) {
    if (v) query.set(k, v);
  }
  const search = query.toString();
  return search ? `/schemes?${search}` : "/schemes";
}

/**
 * One collapsible group of options.
 *
 * A native `<details>` rather than a React toggle. This is a server component
 * inside a page whose filters are plain links, and the whole column has to keep
 * working before — or without — any JavaScript arriving. The browser opens and
 * closes these on its own, keyboard included, for nothing.
 *
 * The long tail of a group hides inside a second `<details>` rather than being
 * cut off. Thirty-six states listed flat is why this column needed a scrollbar
 * of its own; twelve and a "show the rest" is the same information without the
 * wall.
 */
function FilterGroup({
  title,
  options,
  activeValue,
  onKey,
  active,
  limit,
  lang,
  label,
  open = true,
  t,
}: {
  title: string;
  options: { name: string; count: number }[];
  activeValue?: string;
  onKey: keyof Active;
  active: Active;
  limit?: number;
  lang: Lang;
  /**
   * How to show this option's name. The VALUE stays the English one the
   * corpus is indexed by — translate that and `?category=…` matches nothing,
   * silently — so only what the reader sees is swapped.
   */
  label?: (lang: Lang, name: string) => string;
  open?: boolean;
  t: Translate;
}) {
  if (options.length === 0) return null;

  const selected = options.find((o) => o.name === activeValue);
  const head = limit ? options.slice(0, limit) : options;
  // A chosen value that falls outside the visible slice is pulled to the top.
  // A filter that vanishes from its own list reads as having been forgotten.
  const visible =
    selected && !head.some((o) => o.name === selected.name)
      ? [selected, ...head]
      : head;
  const rest = options.filter((o) => !visible.includes(o));

  const row = (option: { name: string; count: number }) => {
    const isActive = option.name === activeValue;
    return (
      <li key={option.name}>
        <Link
          href={hrefWith(active, onKey, isActive ? undefined : option.name)}
          aria-current={isActive ? "true" : undefined}
          className={cn(
            "flex items-start justify-between gap-3 rounded-lg px-2.5 py-2 text-[0.875rem] transition-colors",
            isActive
              ? "bg-mint font-medium text-leaf"
              : "text-foreground/85 hover:bg-accent",
          )}
        >
          {/* Not truncated. A category whose name is cut at "समाज कल्याण और सश…"
              is one a reader has to guess at, and the guess is the whole point
              of the filter. */}
          <span className="min-w-0 leading-snug">
            {label ? label(lang, option.name) : option.name}
          </span>
          <span className="tnum mt-px shrink-0 text-[0.75rem] text-faint">
            {isActive ? (
              <X className="size-3.5" aria-hidden />
            ) : (
              option.count.toLocaleString(`${lang}-IN`)
            )}
          </span>
        </Link>
      </li>
    );
  };

  return (
    <details
      open={open || Boolean(selected)}
      className="group border-b border-border py-3 last:border-b-0"
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 [&::-webkit-details-marker]:hidden">
        <span className="meta">{title}</span>
        <ChevronDown className="size-3.5 shrink-0 text-faint transition-transform duration-200 group-open:rotate-180" />
      </summary>

      <ul className="mt-2 space-y-0.5">{visible.map(row)}</ul>

      {rest.length > 0 ? (
        <details className="group/more mt-1">
          <summary className="cursor-pointer list-none rounded-lg px-2.5 py-2 text-[0.8125rem] text-leaf underline-offset-4 hover:underline [&::-webkit-details-marker]:hidden">
            {t("schemes.filter.showAll", { count: options.length })}
          </summary>
          <ul className="mt-0.5 space-y-0.5">{rest.map(row)}</ul>
        </details>
      ) : null}
    </details>
  );
}

/**
 * What is currently narrowing the list, and how to undo it.
 *
 * The old column gave no answer to "why am I seeing 334 of 4,736" except a
 * faint highlight somewhere in a list of twenty-nine rows. Stating it at the
 * top — and making each statement the thing you click to undo — is most of
 * what makes a filter panel usable.
 */
function AppliedFilters({
  active,
  lang,
  t,
}: {
  active: Active;
  lang: Lang;
  t: Translate;
}) {
  const chips: { key: keyof Active; text: string }[] = [];
  if (active.category)
    chips.push({ key: "category", text: categoryLabel(lang, active.category) });
  if (active.level)
    chips.push({ key: "level", text: levelLabel(lang, active.level) });
  if (active.state) chips.push({ key: "state", text: active.state });
  if (active.q) chips.push({ key: "q", text: `“${active.q}”` });

  if (chips.length === 0) return null;

  return (
    <div className="border-b border-border pb-4">
      <p className="meta px-2.5">{t("schemes.filter.applied")}</p>
      <ul className="mt-2.5 flex flex-wrap gap-1.5 px-2.5">
        {chips.map((chip) => (
          <li key={chip.key}>
            <Link
              href={hrefWith(active, chip.key, undefined)}
              className="flex items-center gap-1.5 rounded-full bg-mint py-1 ps-3 pe-2 text-[0.8125rem] text-leaf transition-colors hover:bg-[color-mix(in_oklch,var(--mint),var(--leaf)_10%)]"
            >
              <span className="max-w-[14ch] truncate">{chip.text}</span>
              <X className="size-3.5 shrink-0" aria-hidden />
              <span className="sr-only">{t("schemes.filter.clear")}</span>
            </Link>
          </li>
        ))}
        {chips.length > 1 ? (
          <li>
            <Link
              href="/schemes"
              className="flex items-center rounded-full px-3 py-1 text-[0.8125rem] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              {t("schemes.filter.clear")}
            </Link>
          </li>
        ) : null}
      </ul>
    </div>
  );
}

export function SchemeFilters({
  meta,
  active,
  className,
  lang,
  t,
}: {
  meta: CatalogMeta;
  active: Active;
  className?: string;
  lang: Lang;
  t: Translate;
}) {
  // "All" is not a state a person lives in — it is how the corpus marks a
  // central scheme, and those are already included in every state's results.
  const states = meta.states.filter((s) => s.name !== "All");

  return (
    <div className={cn("-mx-2.5 text-sm", className)}>
      <AppliedFilters active={active} lang={lang} t={t} />

      <FilterGroup
        title={t("schemes.filter.category")}
        options={meta.categories}
        activeValue={active.category}
        onKey="category"
        active={active}
        limit={8}
        lang={lang}
        label={categoryLabel}
        t={t}
      />
      <FilterGroup
        title={t("schemes.filter.level")}
        options={meta.levels}
        activeValue={active.level}
        onKey="level"
        active={active}
        lang={lang}
        label={levelLabel}
        t={t}
      />
      {/* State names are proper nouns and stay as published. Closed by default:
          it is the longest group by far and the least often the first thing
          someone reaches for. */}
      <FilterGroup
        title={t("schemes.filter.state")}
        options={states}
        activeValue={active.state}
        onKey="state"
        active={active}
        limit={8}
        lang={lang}
        open={false}
        t={t}
      />

      <p className="px-2.5 pt-3 text-[0.75rem] leading-relaxed text-faint">
        {t("check.location.central")}
      </p>
    </div>
  );
}
