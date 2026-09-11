/**
 * The vocabulary of the eligibility questions.
 *
 * The values sent to the engine are the short machine ones ("sc", "female");
 * the engine translates those into myScheme's exact facet labels. The labels
 * shown to a person are written in plain words instead — "Scheduled Caste (SC)"
 * is how a database says it, not how anyone asks.
 */

export interface Option {
  /** The machine value sent to the engine. Never translated. */
  value: string;
  /** Dictionary key for what the person reads. */
  key: string;
}

export const CASTES: Option[] = [
  { value: "sc", key: "opt.caste.sc" },
  { value: "st", key: "opt.caste.st" },
  { value: "obc", key: "opt.caste.obc" },
  { value: "pvtg", key: "opt.caste.pvtg" },
  { value: "dnt", key: "opt.caste.dnt" },
  { value: "general", key: "opt.caste.general" },
];

export const GENDERS: Option[] = [
  { value: "female", key: "opt.gender.female" },
  { value: "male", key: "opt.gender.male" },
  { value: "transgender", key: "opt.gender.transgender" },
];

export const RESIDENCE: Option[] = [
  { value: "rural", key: "opt.residence.rural" },
  { value: "urban", key: "opt.residence.urban" },
];

export const YES_NO: Option[] = [
  { value: "yes", key: "opt.yes" },
  { value: "no", key: "opt.no" },
];

export const MARITAL: Option[] = [
  { value: "never married", key: "opt.marital.never" },
  { value: "married", key: "opt.marital.married" },
  { value: "widowed", key: "opt.marital.widowed" },
  { value: "divorced", key: "opt.marital.divorced" },
  { value: "separated", key: "opt.marital.separated" },
];

export const EMPLOYMENT: Option[] = [
  { value: "unemployed", key: "opt.work.unemployed" },
  { value: "employed", key: "opt.work.employed" },
  { value: "self-employed", key: "opt.work.self" },
];

/**
 * Verbatim from the corpus. These are matched as exact strings, so a tidied-up
 * spelling here would simply return nothing — "Safai Karamchari" cannot become
 * "Sanitation worker" without breaking the filter.
 */
export const OCCUPATIONS = [
  "Farmer",
  "Construction Worker",
  "Unorganized Worker",
  "Fishermen",
  "Artists",
  "Artisans, Spinners & Weavers",
  "Student",
  "Organized Worker",
  "Sportsperson",
  "Ex Servicemen",
  "Journalist",
  "Dairy Farmer",
  "Safai Karamchari",
  "Teacher / Faculty",
  "Coir Worker",
  "Street Vendor",
  "Health Worker",
  "Khadi Artisan",
  "Lawyer / Law Graduate / Advocate",
];

export interface Answers {
  categories?: string[];
  state?: string;
  residence?: string;
  caste?: string;
  gender?: string;
  age?: string;
  family_income?: string;
  is_bpl?: string;
  disability?: string;
  is_student?: string;
  marital_status?: string;
  employment_status?: string;
  occupation?: string;
  /** Owning things, read out of scheme prose by `src/corpus/assets.py`.
   *  Kept as "yes"/"no" strings like every other answer here so the option
   *  rows and the query string need no special case. */
  owns_pucca_house?: string;
  owns_boat?: string;
}

const BOOLEAN_KEYS = ["is_bpl", "disability", "is_student",
                      "owns_pucca_house", "owns_boat"] as const;

/**
 * Answers to a request body.
 *
 * Absent keys are left absent rather than sent as null: the engine treats an
 * absent facet as "not asked" and a present one as a filter, and that
 * distinction is the whole reason an unanswered question never hides a scheme.
 */
export function answersToPayload(answers: Answers): Record<string, unknown> {
  const payload: Record<string, unknown> = {};

  for (const [key, value] of Object.entries(answers)) {
    if (value === undefined || value === "") continue;
    if (key === "categories") {
      if (Array.isArray(value) && value.length) payload.categories = value;
      continue;
    }
    if ((BOOLEAN_KEYS as readonly string[]).includes(key)) {
      payload[key] = value === "yes";
      continue;
    }
    if (key === "age" || key === "family_income") {
      const numeric = Number(value);
      if (Number.isFinite(numeric) && numeric > 0) payload[key] = numeric;
      continue;
    }
    payload[key] = value;
  }

  // A pucca house IS a house, so answering yes to the narrow question also
  // answers the wide one — and seventeen schemes split across the two.
  //
  // The reverse is NOT derived, deliberately. "No pucca house" says nothing
  // about a kutcha one, and asserting owns_house=false there would hand a
  // definite answer to a question nobody asked.
  if (payload.owns_pucca_house === true) payload.owns_house = true;

  return payload;
}

export function answersToQuery(answers: Answers): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(answers)) {
    if (value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) query.append(key, item);
    } else {
      query.set(key, value);
    }
  }
  return query.toString();
}

/** The reverse trip, so a results URL can be shared, bookmarked and reopened. */
export function queryToAnswers(params: {
  [key: string]: string | string[] | undefined;
}): Answers {
  const answers: Answers = {};
  const single = (key: string) => {
    const value = params[key];
    return Array.isArray(value) ? value[0] : value;
  };

  const categories = params.categories;
  if (categories) {
    answers.categories = Array.isArray(categories) ? categories : [categories];
  }

  for (const key of [
    "state", "residence", "caste", "gender", "age", "family_income",
    "is_bpl", "disability", "is_student", "marital_status",
    "employment_status", "occupation", "owns_pucca_house", "owns_boat",
  ] as const) {
    const value = single(key);
    if (value) answers[key] = value;
  }

  return answers;
}
