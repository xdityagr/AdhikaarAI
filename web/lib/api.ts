/**
 * The engine's HTTP surface, typed.
 *
 * Server components call the API directly on the loopback address; the browser
 * goes through the /api rewrite so it only ever sees one origin. Both paths end
 * at the same FastAPI process.
 */

const SERVER_ORIGIN = process.env.ADHIKAAR_API_ORIGIN ?? "http://127.0.0.1:8001";

function url(path: string): string {
  return typeof window === "undefined" ? `${SERVER_ORIGIN}${path}` : path;
}

export type MatchStrength = "ELIGIBLE" | "LIKELY" | "CHECK" | "NOT_MATCHED";

export interface DiscoveryMatch {
  scheme_uid: string;
  slug: string;
  name: string;
  strength: MatchStrength;
  level: string | null;
  state: string | null;
  categories: string[];
  brief: string | null;
  source_url: string;
  depth: "DEEP" | "DISCOVERY";
  matched_on: string[];
  unknown: string[];
  unmet: string[];
  relevance: number;
}

export interface DiscoveryResponse {
  matches: DiscoveryMatch[];
  not_matched: DiscoveryMatch[];
  total_considered: number;
  /** Matches before the list was trimmed for display — the headline figure. */
  total_matched: number;
  total_not_matched: number;
  /** Matches that name a group this person belongs to — caste, occupation,
   *  BPL. The number that actually means something to them. */
  total_targeted: number;
  corpus_available: boolean;
  counts: { eligible: number; likely: number; check: number };
}

export interface SchemeCard {
  slug: string;
  name: string;
  short_title: string | null;
  level: string | null;
  state: string | null;
  ministry: string | null;
  categories: string[];
  tags: string[];
  brief: string | null;
  source_url: string;
  has_detail: boolean;
}

export interface CatalogPage {
  items: SchemeCard[];
  total: number;
  page: number;
  page_size: number;
  corpus_available: boolean;
}

export interface CatalogMeta {
  corpus_available: boolean;
  total: number;
  with_structured_eligibility?: number;
  categories: { name: string; count: number }[];
  states: { name: string; count: number }[];
  levels: { name: string; count: number }[];
}

export interface SchemeDetail {
  slug: string;
  name: string;
  short_title: string | null;
  level: string | null;
  state: string | null;
  ministry: string | null;
  categories: string[];
  tags: string[];
  brief: string | null;
  details_md: string | null;
  benefits_md: string | null;
  eligibility_md: string | null;
  exclusions_md: string | null;
  application_md: string | null;
  documents_md: string | null;
  faqs: { question: string; answer: string }[];
  official_url: string | null;
  source_url: string;
  fetched_at: string | null;
  structured_eligibility?: Record<string, unknown>;
}

/**
 * The corpus is a build artifact and the engine is a separate process, so a
 * page must render even when either is missing. Every helper below returns a
 * usable empty value instead of throwing — a person looking for a pension
 * should see "we can't reach the scheme list right now", never a stack trace.
 */
async function getJson<T>(path: string, fallback: T, revalidate = 300): Promise<T> {
  try {
    const response = await fetch(url(path), { next: { revalidate } });
    if (!response.ok) return fallback;
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export const EMPTY_META: CatalogMeta = {
  corpus_available: false,
  total: 0,
  categories: [],
  states: [],
  levels: [],
};

export function getCatalogMeta(): Promise<CatalogMeta> {
  return getJson("/api/catalog/meta", EMPTY_META, 3600);
}

export function browseSchemes(params: {
  q?: string;
  state?: string;
  category?: string;
  level?: string;
  page?: number;
  page_size?: number;
  /**
   * myScheme's own translations, not machine ones — we hold roughly 4,730
   * schemes in each of nine languages. Omitting this left the browse grid in
   * English while the rest of the interface switched, which is most of what
   * "the schemes are not translated" looked like.
   */
  lang?: string;
}): Promise<CatalogPage> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  return getJson(`/api/catalog?${query}`, {
    items: [],
    total: 0,
    page: 1,
    page_size: 24,
    corpus_available: false,
  });
}

export async function getScheme(
  slug: string,
  lang = "en",
): Promise<SchemeDetail | null> {
  return getJson<SchemeDetail | null>(
    `/api/catalog/${encodeURIComponent(slug)}?lang=${lang}`,
    null,
  );
}

export interface SchemeVerdict {
  slug: string;
  name: string;
  state: string | null;
  brief: string | null;
  verdict: MatchStrength;
  meets: string[];
  unknown: string[];
  unmet: string[];
  source_url: string;
}

/** Does this person qualify for ONE named scheme, condition by condition? */
export async function checkScheme(
  slug: string,
  body: Record<string, unknown>,
): Promise<SchemeVerdict | null> {
  try {
    const response = await fetch(url(`/api/eligibility/${encodeURIComponent(slug)}`), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function discover(
  body: Record<string, unknown>,
): Promise<DiscoveryResponse> {
  const response = await fetch(url("/api/discover"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`Discovery failed (${response.status})`);
  return response.json();
}
