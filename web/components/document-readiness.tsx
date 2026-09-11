"use client";

import {
  useCallback,
  useMemo,
  useState,
  useSyncExternalStore,
} from "react";
import { Camera, Check, Loader2 } from "lucide-react";

import { DocumentCapture } from "@/components/document-capture";
import { useLanguage } from "@/components/language-provider";
import { documentLabel } from "@/lib/i18n/vocabulary";
import { Button } from "@/components/ui/button";

/**
 * "Have I got everything?" — the question people ask at the door, answered
 * before they leave the house.
 *
 * Someone turned away from an office for a missing paper often does not come
 * back, so a checklist is the highest-value thing this product can put in a
 * hand. The scheme's own published list drives it; a photograph can tick a line
 * off; and every tick can be undone by tapping it, because the classifier is
 * allowed to be wrong and the person is not.
 *
 * WHAT IS STORED, AND WHERE
 *
 * The ticks live in this browser under one key per scheme. They are not sent
 * anywhere except back to the pack endpoint when the sheet is printed, and they
 * are not a row on a server: a list of what a poor household does not have is
 * exactly the sort of thing that should not exist outside the phone it was
 * typed into.
 */

type Held = Record<string, boolean>;

const KEY = "yojnasetu.documents";

/* ---------------------------------------------------------------------------
 * The ticks are external state, read the same way `application-tracker.tsx`
 * reads applications. Loading them in an effect and calling setState would
 * paint an empty checklist first and fill it a moment later, which reads as
 * "it forgot what I told it" to someone who is checking precisely because they
 * are anxious about a trip to an office.
 * ------------------------------------------------------------------------- */

const listeners = new Set<() => void>();
let snapshot: Record<string, Held> = {};
let raw: string | null = null;

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function getSnapshot(): Record<string, Held> {
  let current: string | null = null;
  try {
    current = window.localStorage.getItem(KEY);
  } catch {
    // Private windows, cleared site data, a full quota. A checklist that
    // forgets is annoying; one that throws takes the page with it.
    current = null;
  }
  // Only reparse when the stored text actually changed — a fresh object every
  // call would spin the store forever, since React compares by identity.
  if (current !== raw) {
    raw = current;
    try {
      snapshot = current ? (JSON.parse(current) as Record<string, Held>) : {};
    } catch {
      snapshot = {};
    }
  }
  return snapshot;
}

const NONE: Record<string, Held> = {};
const getServerSnapshot = (): Record<string, Held> => NONE;

function persist(all: Record<string, Held>) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* see getSnapshot() */
  }
  raw = null;                       // force a reparse on the next read
  listeners.forEach((listener) => listener());
}

export function DocumentReadiness({
  slug,
  requirements,
}: {
  slug: string;
  requirements: string[];
}) {
  const { lang, t } = useLanguage();
  const all = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const held = useMemo<Held>(() => all[slug] ?? {}, [all, slug]);
  const [capturing, setCapturing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const update = useCallback(
    (next: Held) => {
      persist({ ...getSnapshot(), [slug]: next });
    },
    [slug],
  );

  const toggle = useCallback(
    (requirement: string) => {
      const next = { ...held };
      if (next[requirement]) delete next[requirement];
      else next[requirement] = true;
      update(next);
    },
    [held, update],
  );

  const identify = useCallback(
    async (blob: Blob) => {
      setBusy(true);
      setMessage(null);
      try {
        const body = new FormData();
        body.append("image", blob, "document.jpg");
        body.append("slug", slug);
        const response = await fetch("/api/documents/identify", {
          method: "POST",
          body,
        });
        const data = await response.json();

        if (data.unclear || !data.label) {
          setMessage(data.note || t("documents.unclear"));
          return;
        }
        if (data.matched_index === null || data.matched_index === undefined) {
          // A real document that this scheme did not ask for. Saying so is more
          // useful than silence — it is how someone learns they are carrying
          // something they do not need, or that they picked the wrong scheme.
          setMessage(
            t("documents.notOnList", {
              name: documentLabel(lang, String(data.label)),
            }),
          );
          return;
        }
        const requirement = requirements[data.matched_index];
        update({ ...held, [requirement]: true });
        setMessage(
          t("documents.ticked", {
            name: documentLabel(lang, String(data.label)),
          }),
        );
      } catch {
        setMessage(t("documents.failed"));
      } finally {
        setBusy(false);
        setCapturing(false);
      }
    },
    [held, lang, requirements, slug, t, update],
  );

  const missing = useMemo(
    () => requirements.filter((r) => !held[r]),
    [requirements, held],
  );

  if (!requirements.length) return null;

  return (
    <section className="rounded-2xl border border-hairline bg-card p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-lg font-medium">
          {t("documents.title")}
        </h2>
        <p className="text-[0.8125rem] text-muted-foreground">
          {missing.length === 0
            ? t("documents.allHere")
            : t("documents.stillMissing", { count: missing.length })}
        </p>
      </div>

      <ul className="mt-4 space-y-2">
        {requirements.map((requirement) => {
          const have = Boolean(held[requirement]);
          return (
            <li key={requirement}>
              <button
                type="button"
                onClick={() => toggle(requirement)}
                aria-pressed={have}
                className="flex w-full items-start gap-3 rounded-xl px-2 py-2 text-left hover:bg-muted/60"
              >
                <span
                  aria-hidden
                  className={`mt-0.5 grid size-5 shrink-0 place-items-center rounded-[0.3rem] border ${
                    have
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-foreground/30"
                  }`}
                >
                  {have ? <Check className="size-3.5" /> : null}
                </span>
                <span
                  className={`text-sm leading-relaxed ${
                    have ? "text-muted-foreground line-through" : "text-foreground"
                  }`}
                >
                  {requirement}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {message ? (
        <p className="mt-3 rounded-lg bg-mint px-3 py-2 text-[0.8125rem] text-leaf">
          {message}
        </p>
      ) : null}

      <div className="mt-4">
        {capturing ? (
          <DocumentCapture
            busy={busy}
            label={t("documents.captureLabel")}
            privacyNote={t("documents.privacy")}
            onCaptured={identify}
            onClose={() => setCapturing(false)}
          />
        ) : (
          <Button
            type="button"
            variant="outline"
            onClick={() => setCapturing(true)}
            className="w-full"
          >
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Camera className="size-4" />
            )}
            {t("documents.identify")}
          </Button>
        )}
      </div>
    </section>
  );
}
