"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { Bookmark, BookmarkCheck, ListChecks } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";
import {
  removeApplication,
  startApplication,
  useApplications,
} from "@/lib/applications";

/**
 * "Keep this one" — the step between reading a form and having applied.
 *
 * Without it the middle of the journey was unrecorded. Someone could open an
 * application, tick four of five documents, close the tab, and have nowhere to
 * look to answer "what was I applying for?". The ticks were saved the whole
 * time; there was simply no list that led back to them.
 *
 * Deliberately explicit rather than automatic. Opening a form to read what a
 * scheme wants is not the same as deciding to apply for it, and a list that
 * silently filled up with everything anyone had glanced at would be worth
 * nothing by the end of an afternoon.
 */
export function SaveApplication({
  slug,
  scheme,
}: {
  slug: string;
  scheme: string;
}) {
  const { t } = useLanguage();
  const applications = useApplications();
  const saved = useMemo(
    () => applications.find((a) => a.slug === slug),
    [applications, slug],
  );

  const toggle = useCallback(() => {
    if (saved) removeApplication(saved.id);
    else startApplication(slug, scheme);
  }, [saved, slug, scheme]);

  return (
    <div className="rounded-2xl border border-hairline bg-card p-5 print:hidden">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">
            {saved ? t("apply.saved.title") : t("apply.save.title")}
          </h2>
          <p className="mt-1 text-[0.8125rem] leading-relaxed text-muted-foreground">
            {saved ? t("apply.saved.body") : t("apply.save.body")}
          </p>
        </div>
        <Button
          type="button"
          variant={saved ? "outline" : "default"}
          onClick={toggle}
          className="h-10 shrink-0"
        >
          {saved ? (
            <BookmarkCheck className="size-4" />
          ) : (
            <Bookmark className="size-4" />
          )}
          {saved ? t("apply.save.remove") : t("apply.save.cta")}
        </Button>
      </div>

      {saved ? (
        <Link
          href="/track"
          className="mt-3 inline-flex items-center gap-1.5 text-[0.8125rem] font-medium text-leaf underline-offset-4 hover:underline"
        >
          <ListChecks className="size-3.5" />
          {t("apply.save.viewAll")}
        </Link>
      ) : null}
    </div>
  );
}
