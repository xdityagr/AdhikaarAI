"use client";

import { useSyncExternalStore } from "react";
import Link from "next/link";
import { ArrowRight, FileText, Trash2 } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";
import {
  heldCount,
  removeApplication,
  useApplications,
} from "@/lib/applications";

/**
 * The schemes somebody is part-way through.
 *
 * This is the half of "my applications" that did not exist. The tracker below
 * it handles applications that have been handed in and have a reference number
 * to chase; this handles the ones still being put together, which is where
 * almost everybody actually is — gathering a caste certificate takes weeks, and
 * for all of those weeks there was no page that remembered what you were doing.
 *
 * Each card shows how many papers are ticked, read from the checklist's own
 * store rather than a copy, and leads straight back to the form.
 */

/* The document ticks are a second external store, so changes to them have to
 * repaint this list. Subscribing to `storage` alone would miss same-tab edits;
 * the applications store already broadcasts, and the checklist writes to
 * localStorage, so a plain storage listener plus a focus nudge covers both a
 * second tab and a return from the apply page. */
function subscribeDocuments(listener: () => void): () => void {
  window.addEventListener("storage", listener);
  window.addEventListener("focus", listener);
  return () => {
    window.removeEventListener("storage", listener);
    window.removeEventListener("focus", listener);
  };
}

export function PreparingList({ className }: { className?: string }) {
  const { t } = useLanguage();
  const applications = useApplications();
  // Re-read on any storage or focus event; the value itself is read per card.
  useSyncExternalStore(
    subscribeDocuments,
    () => {
      try {
        return window.localStorage.getItem("yojnasetu.documents") ?? "";
      } catch {
        return "";
      }
    },
    () => "",
  );

  const preparing = applications.filter((a) => a.status === "preparing");
  if (!preparing.length) return null;

  return (
    <section className={className}>
      <h2 className="font-display text-[1.25rem] font-normal">
        {t("track.preparing.title")}
      </h2>
      <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">
        {t("track.preparing.lede")}
      </p>

      <ul className="mt-5 space-y-3">
        {preparing.map((application) => {
          const held = heldCount(application.slug);
          return (
            <li
              key={application.id}
              className="rounded-2xl border border-hairline bg-card p-5"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="font-display text-[1.0625rem] font-normal leading-snug">
                    {application.scheme}
                  </h3>
                  <p className="mt-1.5 flex items-center gap-1.5 text-[0.8125rem] text-muted-foreground">
                    <FileText className="size-3.5 shrink-0" />
                    {held > 0
                      ? t("track.preparing.papers", { count: held })
                      : t("track.preparing.noPapers")}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0 text-faint hover:text-foreground"
                  aria-label={t("track.preparing.remove")}
                  onClick={() => removeApplication(application.id)}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>

              {application.slug ? (
                <Link
                  href={`/apply/${encodeURIComponent(application.slug)}`}
                  className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline"
                >
                  {t("track.preparing.continue")}
                  <ArrowRight className="size-3.5" />
                </Link>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
