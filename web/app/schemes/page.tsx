import Link from "next/link";
import { Search } from "lucide-react";

import { FilterDisclosure } from "@/components/filter-disclosure";
import { PageHeader } from "@/components/page-header";
import { SchemeFilters } from "@/components/scheme-filters";
import { Button } from "@/components/ui/button";
import { ButtonLink } from "@/components/ui/button-link";
import { Input } from "@/components/ui/input";
import { browseSchemes, getCatalogMeta, type SchemeCard } from "@/lib/api";
import { formatNumber } from "@/lib/i18n";
import { getLang, getT } from "@/lib/i18n/server";
import { categoryLabel, levelLabel } from "@/lib/i18n/vocabulary";
import { translator, type Translate } from "@/lib/i18n";
import type { Lang } from "@/lib/i18n/config";

export async function generateMetadata() {
  const t = await getT();
  return {
    title: t("schemes.h1"),
    description: t("schemes.meta.description"),
  };
}

const PAGE_SIZE = 24;

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function SchemesPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const q = one(params.q) ?? "";
  const category = one(params.category);
  const state = one(params.state);
  const level = one(params.level);
  const page = Math.max(1, Number(one(params.page) ?? 1) || 1);

  // The language is needed before the query, not alongside it: the catalogue
  // is served in myScheme's own translations, so `lang` decides what comes
  // back rather than only how it is labelled.
  const lang = await getLang();
  const [meta, results] = await Promise.all([
    getCatalogMeta(),
    browseSchemes({ q, category, state, level, page, page_size: PAGE_SIZE, lang }),
  ]);
  const t = translator(lang);

  const lastPage = Math.max(1, Math.ceil(results.total / PAGE_SIZE));
  const filtered = Boolean(q || category || state || level);

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("nav.schemes")}
        title={t("schemes.h1")}
        lede={t("schemes.lede", { count: formatNumber(lang, meta.total) })}
      />

      <div className="mx-auto max-w-6xl px-5 sm:px-6">
      {/* Search is a plain GET form so it works before JavaScript loads and the
          URL stays shareable — a field worker can send a filtered link on. */}
      <form method="GET" className="mx-auto flex max-w-2xl flex-col gap-2.5 sm:flex-row">
        {category ? <input type="hidden" name="category" value={category} /> : null}
        {state ? <input type="hidden" name="state" value={state} /> : null}
        {level ? <input type="hidden" name="level" value={level} /> : null}
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute start-4 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <Input
            name="q"
            defaultValue={q}
            placeholder={t("schemes.search.placeholder")}
            className="h-12 rounded-full border-border bg-card ps-11 text-base shadow-[0_1px_2px_rgb(28_26_23/0.04)]"
            aria-label={t("schemes.search.button")}
          />
        </div>
        <Button type="submit" size="pill-lg">
          {t("schemes.search.button")}
        </Button>
      </form>

      <div className="mt-14 grid gap-10 lg:grid-cols-[240px_1fr]">
        {/*
          A sticky column must be told how tall it may get. Without the max
          height and its own overflow, the sidebar pins at top-24 and anything
          below the fold is unreachable — the page scroll moves the results
          column, not this one — so the last few categories could be seen but
          never clicked. `overscroll-contain` stops a flick inside the list
          from scrolling the page out from under it.
        */}
        <aside
          className="lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:self-start
                     lg:overflow-y-auto lg:overscroll-contain lg:pr-2"
        >
          <FilterDisclosure
            activeCount={[category, state, level].filter(Boolean).length}
          >
            <SchemeFilters
              meta={meta}
              active={{ q, category, state, level }}
              className="mt-4"
              lang={lang}
              t={t}
            />
          </FilterDisclosure>
        </aside>

        <section>
          <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-border pb-3">
            <p className="text-[0.9375rem] text-muted-foreground">
              {results.total === 0 ? (
                t("schemes.none")
              ) : (
                <>
                  <span className="tnum font-medium text-foreground">
                    {formatNumber(lang, results.total)}
                  </span>{" "}
                  · {t("schemes.page")} {results.page} {t("schemes.of")}{" "}
                  {lastPage}
                </>
              )}
            </p>
            {filtered ? (
              <Link
                href="/schemes"
                className="text-[0.9375rem] text-leaf underline-offset-4 hover:underline"
              >
                {t("schemes.filter.clear")}
              </Link>
            ) : null}
          </div>

          {!results.corpus_available ? (
            <p className="mt-8 border-s-2 border-clay ps-5 text-[0.9375rem] leading-relaxed text-clay">
              The scheme list is not available right now. It is a local copy that
              may be rebuilding — searching again in a minute usually works.
            </p>
          ) : null}

          {results.items.length === 0 && results.corpus_available ? (
            <EmptyState t={t} />
          ) : (
            <ul className="mt-2 border-t border-border">
              {results.items.map((scheme) => (
                <SchemeListCard
                  key={scheme.slug}
                  scheme={scheme}
                  lang={lang}
                  t={t}
                />
              ))}
            </ul>
          )}

          <Pagination
            page={results.page}
            lastPage={lastPage}
            params={{ q, category, state, level }}
          />
        </section>
      </div>
      </div>
    </div>
  );
}

/**
 * One scheme, as a ruled row.
 *
 * Cards were wrong for this list. Official scheme names run to fifteen words —
 * "Immediate Relief Assistance under Welfare and Relief for Fishermen During
 * Lean Seasons and Natural Calamities Scheme" — and a two-column card grid
 * either clips them or grows a card to twice the height of the one beside it.
 * A row gives the name the full measure and lets the eye run down the list.
 */
function SchemeListCard({
  scheme,
  lang,
  t,
}: {
  scheme: SchemeCard;
  lang: Lang;
  t: Translate;
}) {
  return (
    <li className="group border-b border-border">
      <Link
        href={`/schemes/${scheme.slug}`}
        className="-mx-3 block rounded-xl px-3 py-6 transition-colors duration-200 hover:bg-accent/50"
      >
        <p className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[0.8125rem] text-faint">
          <span className="text-leaf">
            {scheme.level ? levelLabel(lang, scheme.level) : t("scheme.level")}
          </span>
          {scheme.state && scheme.state !== "All" ? (
            <>
              <span aria-hidden>·</span>
              <span>{scheme.state}</span>
            </>
          ) : null}
          {scheme.categories.slice(0, 2).map((category) => (
            <span key={category} className="flex items-center gap-2.5">
              <span aria-hidden>·</span>
              {categoryLabel(lang, category)}
            </span>
          ))}
        </p>

        <h3 className="mt-2 font-display text-[1.1875rem] font-normal leading-snug tracking-[-0.015em] transition-colors group-hover:text-leaf">
          {scheme.name.trim()}
        </h3>

        {scheme.brief ? (
          <p className="mt-1.5 line-clamp-2 max-w-[80ch] text-[0.9375rem] leading-relaxed text-muted-foreground">
            {scheme.brief}
          </p>
        ) : null}
      </Link>
    </li>
  );
}

function EmptyState({ t }: { t: Translate }) {
  return (
    <div className="mt-12 border-t border-border pt-16 text-center">
      <p className="font-display text-[1.375rem] font-normal">
        {t("schemes.empty.title")}
      </p>
      <p className="mx-auto mt-3 max-w-[52ch] text-[0.9375rem] leading-relaxed text-muted-foreground">
        {t("schemes.empty.body")}
      </p>
      <ButtonLink href="/check" size="pill" className="mt-7">
        {t("home.cta.primary")}
      </ButtonLink>
    </div>
  );
}

function Pagination({
  page,
  lastPage,
  params,
}: {
  page: number;
  lastPage: number;
  params: Record<string, string | undefined>;
}) {
  if (lastPage <= 1) return null;

  const href = (target: number) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value) query.set(key, value);
    }
    query.set("page", String(target));
    return `/schemes?${query}`;
  };

  return (
    <nav
      className="mt-12 flex items-center justify-between"
      aria-label="Pagination"
    >
      {page > 1 ? (
        <ButtonLink href={href(page - 1)} variant="outline" size="pill-sm" className="bg-card">
          Previous
        </ButtonLink>
      ) : (
        <span />
      )}
      <span className="tnum text-[0.875rem] text-faint">
        {page} / {lastPage}
      </span>
      {page < lastPage ? (
        <ButtonLink href={href(page + 1)} variant="outline" size="pill-sm" className="bg-card">
          Next
        </ButtonLink>
      ) : (
        <span />
      )}
    </nav>
  );
}
