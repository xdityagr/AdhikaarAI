"use client";

import { useSyncExternalStore } from "react";

/**
 * The schemes a person is working on, in both of the states that matters.
 *
 * The tracker only ever knew about applications that had already been
 * SUBMITTED — it asks for a reference number from the office, which you only
 * have once you have been. So the whole middle of the journey was invisible:
 * you could read a scheme, open its form, tick off four of five documents, and
 * then have nowhere to look to answer "what was I applying for again?". The
 * work was saved, and unreachable.
 *
 * An application now has two lives:
 *
 *   preparing  — you have decided to apply and are gathering papers
 *   submitted  — you have a reference number, and the stage tracker takes over
 *
 * One list, because that is how a person thinks about it. "My applications" is
 * not two different questions.
 *
 * STILL NOTHING ON A SERVER. This is localStorage, like the profile and the
 * document ticks. A list of which welfare schemes a household is chasing is
 * exactly the sort of record that should not exist anywhere but the phone it
 * was made on.
 */

export type ApplicationStatus = "preparing" | "submitted";

export interface Application {
  id: string;
  /** The corpus slug, so the card can link back to the form and the papers. */
  slug?: string;
  scheme: string;
  status: ApplicationStatus;
  /** Only once it has actually been handed in. */
  reference?: string;
  office?: string;
  appliedAt?: string;
  /** Where it has reached, for submitted ones. */
  stageIndex: number;
  /** When the person first said "I want this one". */
  startedAt?: string;
}

const KEY = "yojnasetu.applications";
const DOCUMENTS_KEY = "yojnasetu.documents";

/* ---------------------------------------------------------------------------
 * External state, read through useSyncExternalStore. Loading it in an effect
 * and calling setState paints an empty list first and fills it a moment later,
 * which reads as "my application is gone" to someone anxiously checking on
 * their money — the reason the tracker did it this way to begin with.
 * ------------------------------------------------------------------------ */

const listeners = new Set<() => void>();
let snapshot: Application[] = [];
let raw: string | null = null;

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function getSnapshot(): Application[] {
  let current: string | null = null;
  try {
    current = window.localStorage.getItem(KEY);
  } catch {
    current = null;
  }
  // Reparsed only when the stored text actually changed: React compares
  // snapshots by identity, so a fresh array every call spins forever.
  if (current !== raw) {
    raw = current;
    try {
      const parsed = current ? (JSON.parse(current) as Application[]) : [];
      // Records written before `status` existed are submitted ones — that was
      // the only kind the tracker could make. Defaulting them to "preparing"
      // would quietly move somebody's filed application back into a to-do list.
      snapshot = parsed.map((a) => ({
        ...a,
        status: a.status ?? "submitted",
        stageIndex: a.stageIndex ?? 0,
      }));
    } catch {
      snapshot = [];
    }
  }
  return snapshot;
}

const NONE: Application[] = [];
export const getServerSnapshot = (): Application[] => NONE;

export function save(next: Application[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Still usable this visit; it just will not be here tomorrow.
  }
  raw = null;
  for (const listener of listeners) listener();
}

export function useApplications(): Application[] {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** Whether this scheme is already on the list, and as what. */
export function findBySlug(slug: string): Application | undefined {
  return getSnapshot().find((a) => a.slug === slug);
}

/**
 * Put a scheme on the list, or leave it alone if it is already there.
 *
 * Idempotent on purpose: opening the same application form twice must not
 * produce two cards, and it must never reset a submitted one back to
 * "preparing" — someone who has filed and come back to re-read the papers has
 * not un-filed it.
 */
export function startApplication(slug: string, scheme: string): Application {
  const existing = findBySlug(slug);
  if (existing) return existing;
  const application: Application = {
    id: crypto.randomUUID(),
    slug,
    scheme,
    status: "preparing",
    stageIndex: 0,
    startedAt: new Date().toISOString(),
  };
  save([...getSnapshot(), application]);
  return application;
}

export function removeApplication(id: string): void {
  save(getSnapshot().filter((a) => a.id !== id));
}

export function updateApplication(id: string, patch: Partial<Application>): void {
  save(getSnapshot().map((a) => (a.id === id ? { ...a, ...patch } : a)));
}

/* ---------------------------------------------------------------------------
 * Document progress
 *
 * Read from the checklist's own store rather than copied into this one. Two
 * records of the same fact drift, and the one that drifts here would tell
 * somebody they had four of five papers when they had three.
 * ------------------------------------------------------------------------ */

export function heldCount(slug?: string): number {
  if (!slug) return 0;
  try {
    const all = JSON.parse(window.localStorage.getItem(DOCUMENTS_KEY) || "{}");
    return Object.values(all[slug] ?? {}).filter(Boolean).length;
  } catch {
    return 0;
  }
}
