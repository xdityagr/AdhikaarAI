"use client";

import Image from "next/image";
import { useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Loader2,
  LocateFixed,
  MapPin,
  ShieldAlert,
} from "lucide-react";

import { announcePlace } from "@/components/language-suggestion";
import { OptionRow } from "@/components/option-row";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLanguage } from "@/components/language-provider";
import { MapCard } from "@/components/map-card";
import { cn } from "@/lib/utils";

type T = ReturnType<typeof useLanguage>["t"];

interface Scheme {
  scheme_id: string;
  name: string;
  rate: number;
  why_eligible: string;
  loan_amount: number;
  instalment_amount: number;
  instalment_frequency: string;
  instalment_count: number;
  monthly_equivalent: number;
  total_payable: number;
  total_interest: number;
  moratorium_months?: number;
  tenure_years?: number;
}

interface Partner {
  partner_id: string;
  name: string;
  district: string;
  state: string;
  distance_km: number;
  rate: number;
  note: string;
  confidence: string;
}

interface Recommendation {
  eligible: boolean;
  category_note: string;
  schemes: Scheme[];
  rejections: { name: string; reason: string }[];
  scheme_comparison: string;
  fraud_shield: string;
  partners: Partner[];
  excluded_partners: { name: string; reason: string }[];
  cheapest_route: string;
  routing_disclosure: string;
  map_url: string | null;
}

const PURPOSES = [
  { value: "business", key: "opt.purpose.business" },
  { value: "education", key: "opt.purpose.education" },
];

// NSFDC's own category codes, so these are upper-case where the wizard's are
// lower-case machine values. Only the label is shared.
const CATEGORIES = [
  { value: "SC", key: "opt.caste.sc" },
  { value: "ST", key: "opt.caste.st" },
  { value: "OBC", key: "opt.caste.obc" },
  { value: "GENERAL", key: "opt.caste.general" },
];

const GENDERS = [
  { value: "female", key: "opt.gender.female" },
  { value: "male", key: "opt.gender.male" },
  { value: "other", key: "opt.gender.other" },
];

const rupees = (value: number) =>
  `₹${Math.round(value).toLocaleString("en-IN")}`;

export function CreditForm({ className }: { className?: string }) {
  const [purpose, setPurpose] = useState("business");
  const [cost, setCost] = useState("120000");
  const [income, setIncome] = useState("280000");
  const [category, setCategory] = useState("SC");
  const [gender, setGender] = useState("female");
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [place, setPlace] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  const [result, setResult] = useState<Recommendation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const locate = () => {
    if (!window.isSecureContext) {
      setPlace("Location needs https — enter your district below");
      return;
    }
    if (!("geolocation" in navigator)) return;
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setCoords({ lat: latitude, lon: longitude });
        try {
          const response = await fetch(
            `/api/geo/reverse?lat=${latitude}&lon=${longitude}`,
          );
          const data = await response.json();
          setPlace(
            [data.district, data.state].filter(Boolean).join(", ") || null,
          );
          announcePlace(data.state);
        } catch {
          setPlace(null);
        } finally {
          setLocating(false);
        }
      },
      () => setLocating(false),
      { timeout: 10000, maximumAge: 300000 },
    );
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_type: purpose,
          project_cost: Number(cost) || 0,
          annual_income: Number(income) || 0,
          category,
          gender,
          latitude: coords?.lat,
          longitude: coords?.lon,
        }),
      });
      if (!response.ok) throw new Error(String(response.status));
      setResult(await response.json());
    } catch {
      setError(
        t("credit.failed"),
      );
    } finally {
      setBusy(false);
    }
  };

  const { t } = useLanguage();

  return (
    <div className={cn("grid gap-8 lg:grid-cols-[360px_1fr]", className)}>
      <form onSubmit={submit} className="card-quiet h-fit space-y-5 p-6">
        <OptionRow
          label={t("credit.purpose")}
          options={PURPOSES}
          value={purpose}
          onSelect={setPurpose}
        />

        <div>
          <Label htmlFor="cost" className="text-sm font-medium">
            {t("credit.cost")}
          </Label>
          <Input
            id="cost"
            inputMode="numeric"
            className="mt-2 h-12 rounded-xl bg-paper text-base"
            value={cost}
            onChange={(event) => setCost(event.target.value.replace(/\D/g, ""))}
          />
        </div>

        <div>
          <Label htmlFor="income" className="text-sm font-medium">
            {t("credit.income")}
          </Label>
          <Input
            id="income"
            inputMode="numeric"
            className="mt-2 h-12 rounded-xl bg-paper text-base"
            value={income}
            onChange={(event) => setIncome(event.target.value.replace(/\D/g, ""))}
          />
          <p className="mt-1.5 text-xs text-muted-foreground">
            {t("credit.income.hint")}
          </p>
        </div>

        <OptionRow
          label={t("credit.category")}
          options={CATEGORIES}
          value={category}
          onSelect={setCategory}
        />
        <OptionRow label={t("credit.gender")} options={GENDERS} value={gender} onSelect={setGender} />

        <div>
          <p className="text-sm font-medium">{t("credit.where")}</p>
          <Button
            type="button"
            variant="outline"
            className="mt-2 h-12 w-full justify-start rounded-xl bg-paper"
            onClick={locate}
            disabled={locating}
          >
            {locating ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <LocateFixed className="size-4" />
            )}
            {place ?? t("credit.locate")}
          </Button>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {t("credit.where.hint")}
          </p>
        </div>

        <Button type="submit" size="lg" className="h-12 w-full rounded-full text-base" disabled={busy}>
          {busy ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              {t("credit.submitting")}
            </>
          ) : (
            <>
              {t("credit.submit")}
              <ArrowRight className="size-4" />
            </>
          )}
        </Button>
      </form>

      <div className="min-w-0">
        {error ? (
          <p className="rounded-xl border border-border bg-clay-soft p-4 text-sm text-clay">
            {error}
          </p>
        ) : null}

        {!result ? (
          <Placeholder t={t} />
        ) : (
          <Results result={result} t={t} />
        )}
      </div>
    </div>
  );
}

function Placeholder({ t }: { t: T }) {
  return (
    <div className="rounded-2xl border border-dashed border-input p-12 text-center">
      <h2 className="font-display text-[1.25rem] font-normal">
        {t("credit.placeholder.h2")}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
        {t("credit.placeholder.body")}
      </p>
    </div>
  );
}

function Results({ result, t }: { result: Recommendation; t: T }) {
  if (!result.eligible) {
    return (
      <div className="card-quiet p-6 sm:p-7">
        <h2 className="font-display text-[1.25rem] font-normal">
          {t("credit.noroute.h2")}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {result.category_note ||
            t("credit.noroute.body")}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="space-y-4">
        {result.schemes.map((scheme, index) => (
          <div
            key={scheme.scheme_id}
            className={cn(
              "rounded-xl border bg-card p-5",
              index === 0 ? "border-primary" : "border-border",
            )}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h3 className="font-display text-[1.125rem] font-normal">{scheme.name}</h3>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {rupees(scheme.loan_amount)} at {scheme.rate}% ·{" "}
                  {scheme.instalment_frequency}
                </p>
              </div>
              {index === 0 ? (
                <span className="rounded-md bg-gold-soft px-2.5 py-1 text-[0.6875rem] font-semibold uppercase tracking-[0.09em] text-gold-ink">
                  {t("chat.cheapest")}
                </span>
              ) : null}
            </div>

            <dl className="mt-4 grid gap-3 sm:grid-cols-3">
              <Figure
                label={t("credit.instalment", { n: scheme.instalment_count })}
                value={rupees(scheme.instalment_amount)}
              />
              <Figure
                label={t("chat.interest")}
                value={rupees(scheme.total_interest)}
              />
              <Figure label={t("credit.repay")} value={rupees(scheme.total_payable)} />
            </dl>

            <p className="mt-4 border-t border-border pt-3 text-sm leading-relaxed text-muted-foreground">
              {scheme.why_eligible}
            </p>
          </div>
        ))}
      </section>

      {result.scheme_comparison ? (
        <PlainBlock title={t("credit.compare")} body={result.scheme_comparison} />
      ) : null}

      {result.rejections.length > 0 ? (
        <section className="rounded-2xl bg-muted/50 p-5 sm:p-6">
          <h2 className="text-sm font-semibold">{t("chat.notOffered")}</h2>
          <ul className="mt-2 space-y-1.5">
            {result.rejections.map((rejection) => (
              <li key={rejection.name} className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{rejection.name}</span>{" "}
                — {rejection.reason}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.fraud_shield ? (
        <section className="flex gap-3 rounded-xl border border-clay/25 bg-clay-soft p-5">
          <ShieldAlert className="mt-0.5 size-5 shrink-0 text-clay" />
          <p className="text-sm leading-relaxed text-clay">
            {result.fraud_shield.replace(/[*⚠️]/g, "").trim()}
          </p>
        </section>
      ) : null}

      {result.partners.length > 0 ? (
        <section className="card-quiet p-5 sm:p-6">
          <h2 className="flex items-center gap-2 font-display text-[1.125rem] font-normal">
            <MapPin className="size-4" />
            {t("chat.whereToApply")}
          </h2>
          {result.cheapest_route ? (
            <p className="mt-2 text-sm text-muted-foreground">
              {result.cheapest_route}
            </p>
          ) : null}

          <ul className="mt-4 space-y-3">
            {result.partners.map((partner) => (
              <li
                key={partner.partner_id}
                className="flex flex-wrap items-baseline justify-between gap-2 border-t border-border pt-3 first:border-0 first:pt-0"
              >
                <div>
                  <p className="font-medium">{partner.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {partner.district}, {partner.state} ·{" "}
                    {partner.distance_km.toFixed(1)} km
                  </p>
                  {partner.note ? (
                    <p className="text-xs text-muted-foreground">{partner.note}</p>
                  ) : null}
                </div>
                <span className="text-sm font-semibold tabular-nums">
                  {partner.rate}%
                </span>
              </li>
            ))}
          </ul>

          {result.map_url ? (
            <MapCard
              className="mt-4"
              url={result.map_url}
              alt={t("chat.map.alt")}
              caption={t("chat.map.caption")}
            />
          ) : null}
        </section>
      ) : null}

      {result.excluded_partners.length > 0 ? (
        <section className="rounded-2xl bg-muted/50 p-5 sm:p-6">
          <h2 className="text-sm font-semibold">{t("chat.ruledOut")}</h2>
          <ul className="mt-2 space-y-1.5">
            {result.excluded_partners.map((partner) => (
              <li key={partner.name} className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{partner.name}</span>{" "}
                — {partner.reason}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result.routing_disclosure ? (
        <p className="flex gap-2 rounded-xl bg-muted/50 p-4 text-xs leading-relaxed text-muted-foreground">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          {result.routing_disclosure}
        </p>
      ) : null}
    </div>
  );
}

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/60 px-3 py-2.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-0.5 font-display text-[1.125rem] font-normal tabular-nums">
        {value}
      </dd>
    </div>
  );
}

/**
 * The engine writes these blocks for WhatsApp, where *stars* mean bold. Here we
 * strip the markers and keep the text exactly as written — rewriting it in the
 * browser is how the two channels would start quoting different numbers.
 */
function PlainBlock({ title, body }: { title: string; body: string }) {
  const lines = body
    .split("\n")
    .map((line) => line.replace(/\*/g, "").trim())
    .filter(Boolean);
  const [, ...rest] = lines;

  return (
    <section className="card-quiet p-5 sm:p-6">
      <h2 className="font-display text-[1.125rem] font-normal">{title}</h2>
      <ul className="mt-3 space-y-1.5">
        {rest.map((line, index) => (
          <li key={index} className="text-sm leading-relaxed text-muted-foreground">
            {line.replace(/^•\s*/, "")}
          </li>
        ))}
      </ul>
    </section>
  );
}
