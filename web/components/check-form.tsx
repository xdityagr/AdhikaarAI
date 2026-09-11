"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { ArrowRight, Loader2, LocateFixed, MapPin } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { announcePlace } from "@/components/language-suggestion";
import { OptionRow } from "@/components/option-row";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CatalogMeta } from "@/lib/api";
import {
  CASTES,
  EMPLOYMENT,
  GENDERS,
  MARITAL,
  OCCUPATIONS,
  RESIDENCE,
  YES_NO,
  type Answers,
  answersToQuery,
  answersToPayload,
} from "@/lib/facets";
import { categoryLabel } from "@/lib/i18n/vocabulary";
import { cn } from "@/lib/utils";

export function CheckForm({
  meta,
  initialState,
  focusSlug,
  focusName,
  className,
}: {
  meta: CatalogMeta;
  /** Remembered from the location question, so it is not asked twice. */
  initialState?: string | null;
  /** Set when the person came from one scheme's page to check that scheme. */
  focusSlug?: string | null;
  /** That scheme's name, so the panel can show what is being checked. */
  focusName?: string | null;
  className?: string;
}) {
  const { lang, t } = useLanguage();
  const router = useRouter();
  const [answers, setAnswers] = useState<Answers>(
    initialState ? { state: initialState } : {},
  );
  const [matched, setMatched] = useState<number | null>(null);
  const [targeted, setTargeted] = useState(0);
  const [counting, setCounting] = useState(false);
  const [navigating, startNavigating] = useTransition();

  const set = useCallback(<K extends keyof Answers>(key: K, value: Answers[K]) => {
    setAnswers((prev) => {
      // Tapping the selected option again clears it. Every answer must be
      // retractable, or a mis-tap becomes a wrong result the person cannot undo.
      const next = { ...prev };
      if (prev[key] === value) delete next[key];
      else next[key] = value;
      return next;
    });
  }, []);

  // Live count. Debounced, and stale replies are dropped so a slow request
  // cannot overwrite the answer to a newer one.
  const requestId = useRef(0);
  useEffect(() => {
    const id = ++requestId.current;
    const timer = setTimeout(async () => {
      setCounting(true);
      try {
        const response = await fetch("/api/discover", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...answersToPayload(answers), limit: 1 }),
        });
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();
        if (id === requestId.current) {
          setMatched(data.total_matched ?? null);
          setTargeted(data.total_targeted ?? 0);
        }
      } catch {
        if (id === requestId.current) setMatched(null);
      } finally {
        if (id === requestId.current) setCounting(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [answers]);

  const answered = Object.keys(answers).length;

  const submit = () => {
    startNavigating(() => {
      const query = answersToQuery(answers);
      router.push(
        focusSlug
          ? `/check/results?${query}&scheme=${encodeURIComponent(focusSlug)}`
          : `/check/results?${query}`,
      );
    });
  };

  return (
    <div className={cn("grid gap-8 lg:grid-cols-[1fr_300px]", className)}>
      <form
        className="min-w-0 space-y-8"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <Section
          step={1}
          title={t("check.s1.title")}
          hint={t("check.s1.hint")}
        >
          <div className="flex flex-wrap gap-2">
            {meta.categories.map((category) => {
              const active = answers.categories?.includes(category.name);
              return (
                <button
                  key={category.name}
                  type="button"
                  onClick={() =>
                    setAnswers((prev) => {
                      const current = prev.categories ?? [];
                      const next = current.includes(category.name)
                        ? current.filter((c) => c !== category.name)
                        : [...current, category.name];
                      const copy = { ...prev };
                      if (next.length) copy.categories = next;
                      else delete copy.categories;
                      return copy;
                    })
                  }
                  className={cn(
                    "rounded-full border px-3.5 py-2 text-sm font-medium transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-card text-foreground hover:border-primary/40 hover:bg-accent",
                  )}
                >
                  {categoryLabel(lang, category.name)}
                </button>
              );
            })}
          </div>
        </Section>

        <Section
          step={2}
          title={t("check.s2.title")}
          hint={t("check.s2.hint")}
        >
          <LocationPicker
            meta={meta}
            state={answers.state}
            onState={(state) =>
              setAnswers((prev) => {
                const next = { ...prev };
                if (state) next.state = state;
                else delete next.state;
                return next;
              })
            }
          />
          <div className="mt-5">
            <OptionRow
              label={t("check.q.residence")}
              options={RESIDENCE}
              value={answers.residence}
              onSelect={(value) => set("residence", value)}
            />
          </div>
        </Section>

        <Section step={3} title={t("check.s3.title")}>
          <div className="space-y-5">
            <OptionRow
              label={t("check.q.caste")}
              options={CASTES}
              value={answers.caste}
              onSelect={(value) => set("caste", value)}
            />
            <OptionRow
              label={t("check.q.gender")}
              options={GENDERS}
              value={answers.gender}
              onSelect={(value) => set("gender", value)}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="age" className="text-sm font-medium">
                  {t("check.q.age")}
                </Label>
                <Input
                  id="age"
                  inputMode="numeric"
                  placeholder="e.g. 34"
                  className="mt-2 h-12 rounded-xl bg-card text-base"
                  value={answers.age ?? ""}
                  onChange={(event) => {
                    const value = event.target.value.replace(/\D/g, "");
                    setAnswers((prev) => {
                      const next = { ...prev };
                      if (value) next.age = value;
                      else delete next.age;
                      return next;
                    });
                  }}
                />
              </div>
              <div>
                <Label htmlFor="income" className="text-sm font-medium">
                  {t("check.q.income")}
                </Label>
                <Input
                  id="income"
                  inputMode="numeric"
                  placeholder="e.g. 180000"
                  className="mt-2 h-12 rounded-xl bg-card text-base"
                  value={answers.family_income ?? ""}
                  onChange={(event) => {
                    const value = event.target.value.replace(/[^\d]/g, "");
                    setAnswers((prev) => {
                      const next = { ...prev };
                      if (value) next.family_income = value;
                      else delete next.family_income;
                      return next;
                    });
                  }}
                />
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {t("check.q.income.hint")}
                </p>
              </div>
            </div>
          </div>
        </Section>

        <Section
          step={4}
          title={t("check.s4.title")}
          hint={t("check.s4.hint")}
        >
          <div className="space-y-5">
            <OptionRow
              label={t("check.q.bpl")}
              options={YES_NO}
              value={answers.is_bpl}
              onSelect={(value) => set("is_bpl", value)}
            />
            <OptionRow
              label={t("check.q.disability")}
              options={YES_NO}
              value={answers.disability}
              onSelect={(value) => set("disability", value)}
            />
            <OptionRow
              label={t("check.q.student")}
              options={YES_NO}
              value={answers.is_student}
              onSelect={(value) => set("is_student", value)}
            />
            <OptionRow
              label={t("check.q.marital")}
              options={MARITAL}
              value={answers.marital_status}
              onSelect={(value) => set("marital_status", value)}
            />
            <OptionRow
              label={t("check.q.employment")}
              options={EMPLOYMENT}
              value={answers.employment_status}
              onSelect={(value) => set("employment_status", value)}
            />
            <div>
              <Label htmlFor="occupation" className="text-sm font-medium">
                {t("check.q.occupation")}
              </Label>
              <select
                id="occupation"
                className="mt-2 h-12 w-full rounded-xl border border-input bg-card px-3.5 text-base"
                value={answers.occupation ?? ""}
                onChange={(event) => {
                  const value = event.target.value;
                  setAnswers((prev) => {
                    const next = { ...prev };
                    if (value) next.occupation = value;
                    else delete next.occupation;
                    return next;
                  });
                }}
              >
                <option value="">{t("check.occupation.none")}</option>
                {OCCUPATIONS.map((occupation) => (
                  <option key={occupation} value={occupation}>
                    {occupation}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </Section>

        <div className="lg:hidden">
          <SubmitButton navigating={navigating} onClick={submit} />
        </div>
      </form>

      <aside className="hidden lg:block">
        <div className="sticky top-24 space-y-4">
          <div className="card-quiet p-5">
            {focusName ? (
              <>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {t("check.focus.label")}
                </p>
                <p className="mt-2 font-display text-lg font-semibold leading-snug text-foreground">
                  {focusName}
                </p>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                  {t("check.focus.also")}
                  {matched !== null ? (
                    <>
                      {" — "}
                      <span className="tabular-nums text-foreground">
                        {matched.toLocaleString(`${lang}-IN`)}
                      </span>
                    </>
                  ) : null}
                </p>
              </>
            ) : (
              <>
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {t("check.matching")}
                </p>
                <p className="mt-2 font-display text-[2.5rem] font-light tabular-nums text-primary">
                  {counting && matched === null ? (
                    <Loader2 className="size-8 animate-spin" />
                  ) : (
                    (matched ?? meta.total).toLocaleString(`${lang}-IN`)
                  )}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {answered === 0
                    ? t("check.matching.none")
                    : t("check.matching.from")}
                </p>

                {targeted > 0 ? (
                  <p className="mt-3 rounded-lg bg-gold-soft px-3 py-2 text-sm font-medium text-gold-ink">
                    {t("check.matching.targeted", {
                      count: targeted.toLocaleString(`${lang}-IN`),
                    })}
                  </p>
                ) : null}
              </>
            )}

            <SubmitButton
              className="mt-5 w-full"
              navigating={navigating}
              onClick={submit}
              label={focusName ? t("check.focus.submit") : undefined}
            />
          </div>

          <p className="px-1 text-xs leading-relaxed text-muted-foreground">
            {t("check.privacy")}
          </p>
        </div>
      </aside>
    </div>
  );
}

function SubmitButton({
  navigating,
  onClick,
  className,
  label,
}: {
  navigating: boolean;
  onClick: () => void;
  className?: string;
  /** Overrides "Show my schemes" when one scheme is being checked. */
  label?: string;
}) {
  const { t } = useLanguage();
  return (
    <Button
      type="submit"
      size="lg"
      className={cn("h-12 rounded-full px-7 text-base", className)}
      onClick={onClick}
      disabled={navigating}
    >
      {navigating ? (
        <>
          <Loader2 className="size-4 animate-spin" />
          {t("check.submitting")}
        </>
      ) : (
        <>
          {label ?? t("check.submit")}
          <ArrowRight className="size-4" />
        </>
      )}
    </Button>
  );
}

function Section({
  step,
  title,
  hint,
  children,
}: {
  step: number;
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card-quiet p-6">
      <div className="flex items-baseline gap-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-bold text-primary">
          {step}
        </span>
        <div>
          <h2 className="font-display text-[1.25rem] font-normal">{title}</h2>
          {hint ? (
            <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
          ) : null}
        </div>
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

/**
 * Three ways in, hardest last: one tap for location, six digits for a PIN, or
 * a list of states that always works. The previous build offered five hardcoded
 * cities, which is not a location feature.
 */
function LocationPicker({
  meta,
  state,
  onState,
}: {
  meta: CatalogMeta;
  state?: string;
  onState: (state?: string) => void;
}) {
  const { t } = useLanguage();
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pin, setPin] = useState("");

  const states = useMemo(
    () => meta.states.filter((s) => s.name !== "All").map((s) => s.name),
    [meta.states],
  );

  const useMyLocation = () => {
    // Geolocation is gated on a secure context. Over plain HTTP the API is
    // still present but refuses without ever prompting, so checking for the
    // object alone would leave the person tapping a button that does nothing.
    if (!window.isSecureContext) {
      setStatus(t("check.location.insecure"));
      return;
    }
    if (!("geolocation" in navigator)) {
      setStatus(t("check.location.denied"));
      return;
    }
    setBusy(true);
    setStatus(null);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { latitude, longitude } = position.coords;
          const response = await fetch(
            `/api/geo/reverse?lat=${latitude}&lon=${longitude}`,
          );
          const place = await response.json();
          if (place.state) {
            onState(place.state);
            announcePlace(place.state);
            setStatus(
              place.district ? `${place.district}, ${place.state}` : place.state,
            );
          } else {
            setStatus(t("check.location.failed"));
          }
        } catch {
          setStatus(t("check.location.failed"));
        } finally {
          setBusy(false);
        }
      },
      () => {
        setBusy(false);
        setStatus(t("check.location.denied"));
      },
      { timeout: 10000, maximumAge: 300000 },
    );
  };

  const lookupPin = async (value: string) => {
    setBusy(true);
    setStatus(null);
    try {
      const response = await fetch(`/api/geo/pin/${value}`);
      const place = await response.json();
      if (place.state) {
        onState(place.state);
        announcePlace(place.state);
        setStatus(
          place.district ? `${place.district}, ${place.state}` : place.state,
        );
      } else {
        setStatus(t("check.location.badpin"));
      }
    } catch {
      setStatus(t("check.location.failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button
          type="button"
          variant="outline"
          className="h-12 justify-start rounded-xl bg-card px-4"
          onClick={useMyLocation}
          disabled={busy}
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <LocateFixed className="size-4" />
          )}
          {t("check.location.use")}
        </Button>

        <div className="flex gap-2">
          <Input
            inputMode="numeric"
            maxLength={6}
            placeholder={t("check.location.pin")}
            className="h-12 w-40 rounded-xl bg-card text-base"
            value={pin}
            aria-label={t("check.location.pin")}
            onChange={(event) => {
              const value = event.target.value.replace(/\D/g, "").slice(0, 6);
              setPin(value);
              if (value.length === 6) void lookupPin(value);
            }}
          />
        </div>
      </div>

      {status ? (
        <p className="mt-3 flex items-center gap-1.5 text-sm text-muted-foreground">
          <MapPin className="size-3.5" />
          {status}
        </p>
      ) : null}

      <div className="mt-4">
        <Label htmlFor="state" className="text-sm font-medium">
          {t("check.location.state")}
        </Label>
        <select
          id="state"
          className="mt-2 h-12 w-full rounded-xl border border-input bg-card px-3.5 text-base"
          value={state ?? ""}
          onChange={(event) => {
            const next = event.target.value || undefined;
            onState(next);
            announcePlace(next);
          }}
        >
          <option value="">{t("check.location.all")}</option>
          {states.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <p className="mt-1.5 text-xs text-muted-foreground">
          {t("check.location.central")}
        </p>
      </div>
    </div>
  );
}
