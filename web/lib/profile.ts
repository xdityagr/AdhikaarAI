"use client";

/**
 * What someone has told us about themselves, kept on their own device.
 *
 * The gap this closes: the wizard already asks category, gender, state and
 * income, then throws the answers away on navigation. So the assistant asked
 * again, and the application pack could fill exactly one field. Everything the
 * product knew about a person lasted until they clicked a link.
 *
 * ON THE DEVICE, DELIBERATELY
 *
 * `localStorage`, not a cookie and not a row in our database. A cookie rides on
 * every request whether or not it is needed, and a row means we hold a poor
 * household's income and community on a server they cannot see. This travels
 * only when it is the point of the request — the matcher, or filling a form —
 * and clearing it is one button that actually clears it.
 *
 * That is also why there is no sync and no account. An account is a barrier for
 * someone borrowing a relative's phone, and this audience often is.
 *
 * NO AADHAAR NUMBER
 *
 * There is no field for it and there will not be. An Aadhaar number typed into
 * a website is what this audience is most often defrauded with, and no scheme
 * match needs it. Offline e-KYC fills the fields below from a UIDAI-signed
 * file that does not contain the number either — only the last four digits,
 * and we do not keep those.
 */

export interface Profile {
  full_name?: string;
  parent_name?: string;
  dob?: string;
  gender?: string;
  category?: string;
  address?: string;
  state?: string;
  district?: string;
  pincode?: string;
  mobile?: string;
  income?: string;
  purpose?: string;
  project_cost?: string;
  bank_name?: string;
  institution?: string;
  course?: string;
  year?: string;
  /** "verified" once offline e-KYC has signed for the name, DOB and gender. */
  proof?: "declared" | "verified";
}

const KEY = "adhikaar_profile";

/** The order the sheet asks in, and the order the printed form reads in. */
export const PROFILE_FIELDS: {
  key: keyof Profile;
  labelKey: string;
  type?: "text" | "date" | "tel" | "number";
}[] = [
  { key: "full_name", labelKey: "profile.full_name" },
  { key: "parent_name", labelKey: "profile.parent_name" },
  // Text, not `type="date"`. A date input renders BLANK unless the value is
  // exactly YYYY-MM-DD, and many Aadhaar cards carry only a year of birth —
  // so a perfectly good answer read off the card vanished into an empty box.
  // A picker is also the wrong control here: someone born in 1975 has to
  // scroll back fifty years on a phone.
  { key: "dob", labelKey: "profile.dob" },
  { key: "gender", labelKey: "profile.gender" },
  { key: "category", labelKey: "profile.category" },
  { key: "mobile", labelKey: "profile.mobile", type: "tel" },
  { key: "address", labelKey: "profile.address" },
  { key: "district", labelKey: "profile.district" },
  { key: "state", labelKey: "profile.state" },
  { key: "pincode", labelKey: "profile.pincode" },
  { key: "income", labelKey: "profile.income", type: "number" },
];

/**
 * Fields an Aadhaar card can never supply, whatever the scan does.
 *
 * The mobile number is in the QR only as a SHA-256 hash, never as digits.
 * Category and income are separate certificates — a caste certificate and an
 * income certificate — and are not in the Aadhaar record at all.
 *
 * Worth naming, because an empty box beside seven filled ones reads as the
 * scan having half-worked. "Your card does not carry this" and "we could not
 * read it" need to look different or people re-scan a good card.
 */
export const NEVER_ON_A_CARD: (keyof Profile)[] = ["mobile", "category", "income"];

const EMPTY: Profile = Object.freeze({});

let cache: Profile = EMPTY;
let raw: string | null = null;
const listeners = new Set<() => void>();

function load(): Profile {
  if (typeof window === "undefined") return EMPTY;
  let current: string | null = null;
  try {
    current = window.localStorage.getItem(KEY);
  } catch {
    // Private windows and blocked site data throw on access rather than
    // returning null. An unusable store is the same as an empty one.
    return EMPTY;
  }
  // The snapshot must be referentially stable between reads or
  // `useSyncExternalStore` re-renders forever.
  if (current === raw) return cache;
  raw = current;
  try {
    cache = current ? (JSON.parse(current) as Profile) : EMPTY;
  } catch {
    cache = EMPTY;
  }
  return cache;
}

export function readProfile(): Profile {
  return load();
}

/** The server renders with nothing; only the browser has this. */
export function serverProfile(): Profile {
  return EMPTY;
}

export function subscribeProfile(onChange: () => void): () => void {
  listeners.add(onChange);
  // Another tab editing the sheet should update this one.
  const onStorage = (event: StorageEvent) => {
    if (event.key === KEY) onChange();
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    listeners.delete(onChange);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

export function saveProfile(next: Profile): void {
  if (typeof window === "undefined") return;
  // Blank strings are absences, not answers. Storing them would make the pack
  // treat "" as filled and stop leaving the line blank on the printed sheet.
  const cleaned: Profile = {};
  for (const [key, value] of Object.entries(next)) {
    if (typeof value === "string" ? value.trim() : value) {
      (cleaned as Record<string, unknown>)[key] =
        typeof value === "string" ? value.trim() : value;
    }
  }
  try {
    window.localStorage.setItem(KEY, JSON.stringify(cleaned));
  } catch {
    // Out of quota, or blocked. The sheet still works for this page view.
  }
  raw = null;
  listeners.forEach((fn) => fn());
}

export function clearProfile(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    /* nothing to clear */
  }
  raw = null;
  listeners.forEach((fn) => fn());
}

/** How much of the sheet is answered, for the "n of 11" the launcher shows. */
export function profileFilled(profile: Profile): number {
  return PROFILE_FIELDS.filter(({ key }) => {
    const value = profile[key];
    return typeof value === "string" && value.trim() !== "";
  }).length;
}
