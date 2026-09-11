"use client";

import { useSyncExternalStore } from "react";

import { type Answers } from "@/lib/facets";
import { readProfile } from "@/lib/profile";

/**
 * Everyone under one roof, and what each of them can claim.
 *
 * The eligibility check answers "what do *I* qualify for?". That is the wrong
 * unit for how this money is actually found. A pension for the grandmother, a
 * scholarship for the daughter and a tool kit for the father are three
 * different schemes with three different rule sets, and the person holding the
 * phone is usually looking on behalf of all of them — so asking them to clear
 * the form and re-answer as somebody else, three times, is the product making
 * them do the work.
 *
 * WHAT IS SHARED AND WHAT IS NOT
 *
 * Income, state, residence and the BPL card are properties of the HOUSEHOLD.
 * They are the same number and the same card whoever is asking, and a scheme's
 * income ceiling is written against the household anyway. Asking each member
 * separately would be tedious and would also invite four different answers to
 * one question.
 *
 * Caste sits here too. It is the common case by a wide margin, it is what the
 * certificate is issued against, and putting it per-member would double the
 * questions for something that almost never varies within one house.
 *
 * Age, gender, disability, studying, work and marital status are per person.
 * They are also precisely the facets that decide which of the three schemes
 * above each person can claim, which is why the split is drawn here.
 *
 * STILL NOTHING ON A SERVER
 *
 * localStorage, like the profile and the applications list. A roster of a
 * household — ages, genders, disabilities, caste, income — is the most
 * sensitive record this product could hold, and it is exactly the record that
 * must not exist anywhere but the phone it was made on. The matcher sees one
 * member's facets at a time, for the length of one request, and keeps none of
 * it.
 */

/** The facets that are the same for everyone in the house. */
export interface Shared {
  state?: string;
  residence?: string;
  caste?: string;
  family_income?: string;
  is_bpl?: string;
  /** A house belongs to the house. Asking each member whether the family owns
   *  one would be four answers to one question. */
  owns_pucca_house?: string;
}

/** The facets that differ from person to person. */
export interface Member {
  id: string;
  /** What this person is called in the house. Never leaves the device. */
  name: string;
  age?: string;
  gender?: string;
  disability?: string;
  is_student?: string;
  occupation?: string;
  marital_status?: string;
  employment_status?: string;
}

export interface Household {
  shared: Shared;
  members: Member[];
}

export const SHARED_KEYS = [
  "state", "residence", "caste", "family_income", "is_bpl",
  "owns_pucca_house",
] as const;

export const MEMBER_KEYS = [
  "age", "gender", "disability", "is_student", "occupation",
  "marital_status", "employment_status",
] as const;

const KEY = "yojnasetu.household";

const EMPTY: Household = Object.freeze({ shared: {}, members: [] });

/* ---------------------------------------------------------------------------
 * External state, read through useSyncExternalStore — the same shape as
 * applications.ts. Loading in an effect paints an empty house first and fills
 * it a moment later, which reads as "my family is gone".
 * ------------------------------------------------------------------------ */

const listeners = new Set<() => void>();
let snapshot: Household = EMPTY;
let raw: string | null = null;

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (typeof window !== "undefined") {
    window.addEventListener("storage", listener);
  }
  return () => {
    listeners.delete(listener);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", listener);
    }
  };
}

export function getSnapshot(): Household {
  let current: string | null = null;
  try {
    current = window.localStorage.getItem(KEY);
  } catch {
    return EMPTY;
  }
  // Reparsed only when the stored text changed: React compares snapshots by
  // identity, so a fresh object every call spins forever.
  if (current !== raw) {
    raw = current;
    try {
      const parsed = current ? (JSON.parse(current) as Partial<Household>) : null;
      snapshot = parsed
        ? { shared: parsed.shared ?? {}, members: parsed.members ?? [] }
        : EMPTY;
    } catch {
      snapshot = EMPTY;
    }
  }
  return snapshot;
}

export const getServerSnapshot = (): Household => EMPTY;

export function save(next: Household): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Out of quota, or blocked. Usable this visit; gone tomorrow.
  }
  raw = null;
  for (const listener of listeners) listener();
}

export function useHousehold(): Household {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/* ------------------------------------------------------------------ editing */

export function addMember(name: string, fields: Partial<Member> = {}): Member {
  const member: Member = { id: crypto.randomUUID(), name: name.trim(), ...fields };
  const house = getSnapshot();
  save({ ...house, members: [...house.members, member] });
  return member;
}

export function updateMember(id: string, patch: Partial<Member>): void {
  const house = getSnapshot();
  save({
    ...house,
    members: house.members.map((m) => (m.id === id ? { ...m, ...patch } : m)),
  });
}

export function removeMember(id: string): void {
  const house = getSnapshot();
  save({ ...house, members: house.members.filter((m) => m.id !== id) });
}

export function saveShared(shared: Shared): void {
  save({ ...getSnapshot(), shared });
}

/**
 * The first member, from what the person already told us about themselves.
 *
 * Someone who has filled in "About you" has answered most of this once. Making
 * them type their own name, state and income again to see their own household
 * is the product forgetting a conversation it has just had.
 *
 * Only the fields that map without guessing are carried across. `category` on
 * the profile is a free text box — somebody may have typed "OBC (Non-Creamy
 * Layer)" — so it is matched against the known values and otherwise left for
 * them to choose, rather than sent to the engine as a string that will match
 * nothing.
 */
export function seedFromProfile(): Household {
  const profile = readProfile();
  const shared: Shared = {};
  if (profile.state) shared.state = profile.state;
  if (profile.income) shared.family_income = profile.income;

  const caste = (profile.category || "").toLowerCase();
  for (const known of ["sc", "st", "obc", "pvtg", "dnt", "general"]) {
    // Word boundaries: "sc" must not match inside "scheduled" or "general".
    if (new RegExp(`\\b${known}\\b`).test(caste)) {
      shared.caste = known;
      break;
    }
  }

  const gender = (profile.gender || "").toLowerCase();
  const member: Member = {
    id: crypto.randomUUID(),
    name: (profile.full_name || "").trim(),
    ...(["female", "male", "transgender"].includes(gender) ? { gender } : {}),
    ...(ageFromDob(profile.dob) ? { age: ageFromDob(profile.dob) } : {}),
  };
  return { shared, members: [member] };
}

/**
 * Years, from whatever the card said.
 *
 * Many Aadhaar cards carry only a year of birth, and the profile sheet stores
 * the date as typed rather than as a date input for exactly that reason — so
 * this has to cope with "1975" as well as "1975-06-02", and return nothing at
 * all rather than a wrong number when it cannot tell.
 */
export function ageFromDob(dob?: string): string | undefined {
  if (!dob) return undefined;
  const year = Number((dob.match(/\b(19|20)\d{2}\b/) || [])[0]);
  if (!year) return undefined;
  const age = new Date().getFullYear() - year;
  return age >= 0 && age <= 120 ? String(age) : undefined;
}

/** One member's answers, as the engine wants them: their own plus the house's. */
export function memberAnswers(house: Household, member: Member): Answers {
  const answers: Answers = {};
  for (const key of SHARED_KEYS) {
    const value = house.shared[key];
    if (value) answers[key] = value;
  }
  for (const key of MEMBER_KEYS) {
    const value = member[key];
    if (value) answers[key] = value;
  }
  return answers;
}
