"use client";

import { useState, useSyncExternalStore } from "react";
import {
  Check,
  Circle,
  Clock,
  ExternalLink,
  FileWarning,
  Plus,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLanguage } from "@/components/language-provider";
import type { StringKey } from "@/lib/i18n";
import {
  type Application,
  getServerSnapshot,
  getSnapshot,
  save,
  subscribe,
} from "@/lib/applications";
import { cn } from "@/lib/utils";

/**
 * The stages use PFMS's own vocabulary rather than friendlier words of our own.
 * When someone checks the official portal, the words on their screen should be
 * the words they already read here — a mismatch is what makes people think
 * something has gone wrong.
 *
 * Keys rather than sentences. A person tracking their money is the last one who
 * should have to read English to find out which stage they have reached.
 */
const STAGES = [
  { id: "APPLIED", label: "track.stage.applied", expectedDays: 0 },
  { id: "DOCS_VERIFIED", label: "track.stage.docs", expectedDays: 15 },
  { id: "SANCTIONED", label: "track.stage.sanctioned", expectedDays: 45 },
  { id: "PFMS_VALIDATED", label: "track.stage.pfms", expectedDays: 60 },
  { id: "PAYMENT_INITIATED", label: "track.stage.payment", expectedDays: 75 },
  { id: "CREDITED", label: "track.stage.credited", expectedDays: 90 },
] as const satisfies readonly {
  id: string;
  label: StringKey;
  expectedDays: number;
}[];

/** Each stage's one-line explanation, keyed off the label. */
const detailKey = (label: StringKey) => `${label}.detail` as StringKey;

/* The clock, read the same way as any other external source.
 *
 * "How many days since I applied" depends on today's date, which is not a prop,
 * not state, and emphatically not something the server can know. Cached per
 * calendar day so the snapshot is stable between renders — an un-cached
 * `Date.now()` would return a new value every call and spin the store forever.
 */
let dayKey = "";
let dayValue = 0;

function subscribeToday(): () => void {
  return () => {};
}

function todaySnapshot(): number {
  const key = new Date().toDateString();
  if (key !== dayKey) {
    dayKey = key;
    dayValue = Date.parse(key);
  }
  return dayValue;
}

const todayServerSnapshot = (): number => 0;

export function ApplicationTracker({ className }: { className?: string }) {
  const all = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // Only the ones actually handed in. This tracker is a timeline of sanction
  // and disbursement, and a scheme still being prepared has no such timeline —
  // rendering one showed the same scheme twice on /track, once as "still
  // getting ready" and again as "Applied 0 days ago", which it had not been.
  const applications = all.filter((a) => a.status === "submitted");
  const [adding, setAdding] = useState(false);

  const add = (application: Omit<Application, "id" | "stageIndex" | "status">) => {
    save([
      ...all,
      {
        ...application,
        id: crypto.randomUUID(),
        stageIndex: 0,
        // This form asks for a reference number and an office, which you
        // only have once you have handed the papers in.
        status: "submitted" as const,
      },
    ]);
    setAdding(false);
  };

  const { t } = useLanguage();

  return (
    <div className={className}>
      {applications.length === 0 && !adding ? (
        <div className="rounded-2xl border border-dashed border-input p-12 text-center">
          <Clock className="mx-auto size-6 text-muted-foreground" />
          <h2 className="mt-3 font-display text-[1.25rem] font-normal">
            {t("track.empty.title")}
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
            {t("track.empty.body")}
          </p>
          <Button className="mt-6 h-11 rounded-full px-5" onClick={() => setAdding(true)}>
            <Plus className="size-4" />
            {t("track.add")}
          </Button>
        </div>
      ) : null}

      {adding ? <AddForm onAdd={add} onCancel={() => setAdding(false)} /> : null}

      <div className="space-y-6">
        {applications.map((application) => (
          <ApplicationCard
            key={application.id}
            application={application}
            onAdvance={(stageIndex) =>
              save(
                all.map((a) =>
                  a.id === application.id ? { ...a, stageIndex } : a,
                ),
              )
            }
            onRemove={() =>
              save(all.filter((a) => a.id !== application.id))
            }
          />
        ))}
      </div>

      {applications.length > 0 && !adding ? (
        <Button
          variant="outline"
          className="mt-6 h-11 rounded-full bg-card px-5"
          onClick={() => setAdding(true)}
        >
          <Plus className="size-4" />
          {t("track.add")}
        </Button>
      ) : null}

      <OfficialLinks className="mt-10" />
    </div>
  );
}

function AddForm({
  onAdd,
  onCancel,
}: {
  onAdd: (application: Omit<Application, "id" | "stageIndex" | "status">) => void;
  onCancel: () => void;
}) {
  const { t } = useLanguage();
  const [scheme, setScheme] = useState("");
  const [reference, setReference] = useState("");
  const [office, setOffice] = useState("");
  const today = useSyncExternalStore(
    subscribeToday, todaySnapshot, todayServerSnapshot,
  );
  const [appliedAt, setAppliedAt] = useState("");
  const defaultDate = today ? new Date(today).toISOString().slice(0, 10) : "";

  return (
    <form
      className="card-quiet mb-6 space-y-4 p-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (!scheme.trim()) return;
        onAdd({
          scheme: scheme.trim(),
          reference: reference.trim(),
          office: office.trim(),
          appliedAt: appliedAt || defaultDate,
        });
      }}
    >
      <h2 className="font-display text-[1.125rem] font-normal">{t("track.add")}</h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="scheme" className="text-sm font-medium">
            {t("track.form.scheme")}
          </Label>
          <Input
            id="scheme"
            required
            value={scheme}
            onChange={(event) => setScheme(event.target.value)}
            placeholder={t("track.form.scheme.placeholder")}
            className="mt-2 h-12 rounded-xl bg-paper text-base"
          />
        </div>
        <div>
          <Label htmlFor="reference" className="text-sm font-medium">
            {t("track.form.reference")}
          </Label>
          <Input
            id="reference"
            value={reference}
            onChange={(event) => setReference(event.target.value)}
            placeholder={t("track.form.reference.placeholder")}
            className="mt-2 h-12 rounded-xl bg-paper text-base"
          />
        </div>
        <div>
          <Label htmlFor="office" className="text-sm font-medium">
            {t("track.form.office")}
          </Label>
          <Input
            id="office"
            value={office}
            onChange={(event) => setOffice(event.target.value)}
            placeholder={t("track.form.office.placeholder")}
            className="mt-2 h-12 rounded-xl bg-paper text-base"
          />
        </div>
        <div>
          <Label htmlFor="date" className="text-sm font-medium">
            {t("track.form.date")}
          </Label>
          <Input
            id="date"
            type="date"
            value={appliedAt || defaultDate}
            onChange={(event) => setAppliedAt(event.target.value)}
            className="mt-2 h-12 rounded-xl bg-paper text-base"
          />
        </div>
      </div>

      <div className="flex gap-3">
        <Button type="submit" className="h-11 rounded-full px-5">
          {t("track.form.save")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="h-11 rounded-full px-5"
          onClick={onCancel}
        >
          {t("track.form.cancel")}
        </Button>
      </div>
    </form>
  );
}

function ApplicationCard({
  application,
  onAdvance,
  onRemove,
}: {
  application: Application;
  onAdvance: (stageIndex: number) => void;
  onRemove: () => void;
}) {
  const { t } = useLanguage();
  const stage = STAGES[application.stageIndex];
  const next = STAGES[application.stageIndex + 1];

  const today = useSyncExternalStore(
    subscribeToday, todaySnapshot, todayServerSnapshot,
  );
  // `appliedAt` is absent on an application that has not been handed in yet.
  // This card only renders submitted ones, but the type allows it and a NaN
  // here would print "NaN days ago" to somebody chasing their money.
  const daysSince =
    today && application.appliedAt
      ? Math.max(0, Math.floor((today - Date.parse(application.appliedAt)) / 86_400_000))
      : 0;

  // Overdue is measured against the stage the applicant should have reached by
  // now, not the one they are on — that is the gap worth escalating.
  const overdue = next ? daysSince > next.expectedDays : false;

  return (
    <article className="card-quiet p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-[1.125rem] font-normal">{application.scheme}</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {[
              application.office,
              application.reference &&
                t("track.card.ref", { reference: application.reference }),
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className="text-sm text-muted-foreground">
            {daysSince === 0
              ? t("track.card.applied.today")
              : daysSince === 1
                ? t("track.card.applied.one")
                : t("track.card.applied", { days: daysSince })}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onRemove}
          aria-label={t("track.card.remove")}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>

      <ol className="mt-6 space-y-0">
        {STAGES.map((entry, index) => {
          const done = index <= application.stageIndex;
          const current = index === application.stageIndex;
          return (
            <li key={entry.id} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full border",
                    done
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-card text-muted-foreground",
                  )}
                >
                  {done ? <Check className="size-3.5" /> : <Circle className="size-2" />}
                </span>
                {index < STAGES.length - 1 ? (
                  <span
                    className={cn(
                      "w-px flex-1",
                      index < application.stageIndex ? "bg-primary" : "bg-border",
                    )}
                  />
                ) : null}
              </div>
              <div className={cn("pb-5", index === STAGES.length - 1 && "pb-0")}>
                <p
                  className={cn(
                    "text-sm font-medium",
                    current && "text-primary",
                    !done && "text-muted-foreground",
                  )}
                >
                  {t(entry.label)}
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                  {t(detailKey(entry.label))}
                  {entry.expectedDays > 0
                    ? ` ${t("track.stage.usuallyBy", { days: entry.expectedDays })}`
                    : ""}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      <div className="mt-2 flex flex-wrap gap-3">
        {next ? (
          <Button
            className="h-10 px-4"
            onClick={() => onAdvance(application.stageIndex + 1)}
          >
            {t("track.card.mark", { stage: t(next.label) })}
          </Button>
        ) : (
          <p className="text-sm font-medium text-verified">
            {t("track.card.complete")}
          </p>
        )}
        {application.stageIndex > 0 ? (
          <Button
            variant="ghost"
            className="h-10 px-4"
            onClick={() => onAdvance(application.stageIndex - 1)}
          >
            {t("track.card.undo")}
          </Button>
        ) : null}
      </div>

      {overdue && next ? (
        <Escalation stage={t(stage.label)} next={t(next.label)} />
      ) : null}
    </article>
  );
}

function Escalation({ stage, next }: { stage: string; next: string }) {
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);

  const grievance = t("track.escalate.grievance", { stage, next });

  return (
    <div className="mt-5 rounded-xl border border-clay/25 bg-clay-soft p-5">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-clay">
        <FileWarning className="size-4" />
        {t("track.escalate.title")}
      </h3>
      <p className="mt-2 text-sm leading-relaxed text-clay/90">
        {t("track.escalate.body")}
      </p>

      <p className="mt-3 rounded-lg border border-clay/20 bg-paper p-3 text-sm leading-relaxed">
        {grievance}
      </p>

      <div className="mt-3 flex flex-wrap gap-3">
        <Button
          variant="outline"
          className="h-10 bg-paper px-4"
          onClick={() => {
            void navigator.clipboard?.writeText(grievance).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            });
          }}
        >
          {copied ? t("track.escalate.copied") : t("track.escalate.copy")}
        </Button>
        <Button
          variant="outline"
          className="h-10 bg-paper px-4"
          nativeButton={false}
          render={
            <a
              href="https://pgportal.gov.in/"
              target="_blank"
              rel="noopener noreferrer"
            />
          }
        >
          {t("track.escalate.file")}
          <ExternalLink className="size-3.5" />
        </Button>
      </div>
    </div>
  );
}

function OfficialLinks({ className }: { className?: string }) {
  const { t } = useLanguage();
  // Portal names stay in English — they are what the sign above the counter
  // and the browser tab actually say.
  const links = [
    {
      href: "https://pfms.nic.in/Users/LoginDetails/Login.aspx",
      title: "PFMS — Know Your Payment",
      body: t("track.official.pfms.body"),
    },
    {
      href: "https://dbtbharat.gov.in/",
      title: "DBT Bharat",
      body: t("track.official.dbt.body"),
    },
    {
      href: "https://pgportal.gov.in/",
      title: "CPGRAMS",
      body: t("track.official.cpgrams.body"),
    },
  ];

  return (
    <section className={className}>
      <h2 className="font-display text-[1.25rem] font-normal">
        {t("track.official.title")}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {t("track.official.body")}
      </p>
      <ul className="mt-4 grid gap-3 sm:grid-cols-3">
        {links.map((link) => (
          <li key={link.href}>
            <a
              href={link.href}
              target="_blank"
              rel="noopener noreferrer"
              className="flex h-full flex-col rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40"
            >
              <span className="flex items-center gap-1.5 font-medium">
                {link.title}
                <ExternalLink className="size-3.5 text-muted-foreground" />
              </span>
              <span className="mt-1 text-sm leading-relaxed text-muted-foreground">
                {link.body}
              </span>
            </a>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
        {t("track.nocredentials")}
      </p>
    </section>
  );
}
