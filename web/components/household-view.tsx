"use client";

import { useState } from "react";
import Link from "next/link";
import { Plus, Trash2, Users, UserPlus, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { OptionRow } from "@/components/option-row";
import { useLanguage } from "@/components/language-provider";
import { discover, type DiscoveryMatch } from "@/lib/api";
import {
  CASTES, GENDERS, RESIDENCE, YES_NO, MARITAL, EMPLOYMENT, OCCUPATIONS,
  answersToPayload, answersToQuery,
} from "@/lib/facets";
import {
  type Household, type Member, type Shared,
  addMember, memberAnswers, removeMember, save, saveShared,
  seedFromProfile, updateMember, useHousehold,
} from "@/lib/household";
import { facetList } from "@/lib/i18n/vocabulary";
import { cn } from "@/lib/utils";

/**
 * What the whole house can claim, not just the person holding the phone.
 *
 * One discovery request per member, run together, and the results turned
 * inside out: the engine answers "which schemes for this person?" and what
 * somebody actually wants to see is "who in my house can claim this one?".
 * Grouping by scheme is also what stops the page repeating the same national
 * scholarship four times because four children qualify for it.
 *
 * Everything here is a client component because the household lives in
 * localStorage and nowhere else. The server renders the frame and knows none
 * of the contents, exactly as it does for the profile sheet.
 */

/** A scheme, with the people under this roof who match it. */
interface Claim {
  match: DiscoveryMatch;
  members: Member[];
  /** True when at least one member matched on something that names a group
   *  they belong to — caste, occupation, BPL. The number worth acting on. */
  targeted: boolean;
}

export function HouseholdView() {
  const { t, lang } = useLanguage();
  const house = useHousehold();
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [claims, setClaims] = useState<Claim[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  const named = house.members.filter((m) => m.name.trim());

  async function run() {
    setBusy(true);
    setFailed(false);
    try {
      // Together, not one after another: five members served sequentially is
      // five round trips a person waits through in series.
      const results = await Promise.all(
        house.members.map((member) =>
          discover({
            ...answersToPayload(memberAnswers(house, member)),
            limit: 40,
            lang,
          }).then((r) => ({ member, matches: r.matches })),
        ),
      );

      const bySlug = new Map<string, Claim>();
      for (const { member, matches } of results) {
        for (const match of matches) {
          const existing = bySlug.get(match.slug);
          if (existing) {
            existing.members.push(member);
            existing.targeted ||= isTargeted(match);
          } else {
            bySlug.set(match.slug, {
              match,
              members: [member],
              targeted: isTargeted(match),
            });
          }
        }
      }

      // Schemes meant for someone here first, then the ones the most people
      // can claim, then the engine's own ranking.
      setClaims([...bySlug.values()].sort((a, b) =>
        Number(b.targeted) - Number(a.targeted)
        || b.members.length - a.members.length
        || b.match.relevance - a.match.relevance,
      ));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  /* ----------------------------------------------------------- empty house */

  if (house.members.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-input p-12 text-center">
        <Users className="mx-auto size-6 text-muted-foreground" />
        <h2 className="mt-3 font-display text-[1.25rem] font-normal">
          {t("household.empty.title")}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
          {t("household.empty.body")}
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Button
            className="h-11 rounded-full px-5"
            onClick={() => save(seedFromProfile())}
          >
            <UserPlus className="size-4" />
            {t("household.empty.seed")}
          </Button>
          <Button
            variant="outline"
            className="h-11 rounded-full bg-card px-5"
            onClick={() => { save({ shared: {}, members: [] }); setAdding(true); }}
          >
            <Plus className="size-4" />
            {t("household.add")}
          </Button>
        </div>
        {adding ? (
          <MemberForm
            onSave={(name, fields) => { addMember(name, fields); setAdding(false); }}
            onCancel={() => setAdding(false)}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <SharedPanel shared={house.shared} onSave={saveShared} />

      <section>
        <h2 className="font-display text-[1.25rem] font-normal">
          {t("household.members")}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("household.members.hint")}
        </p>

        <ul className="mt-4 grid gap-3 sm:grid-cols-2">
          {house.members.map((member) => (
            <li key={member.id}>
              {editing === member.id ? (
                <MemberForm
                  member={member}
                  onSave={(name, fields) => {
                    updateMember(member.id, { name, ...fields });
                    setEditing(null);
                  }}
                  onCancel={() => setEditing(null)}
                />
              ) : (
                <MemberCard
                  member={member}
                  onEdit={() => setEditing(member.id)}
                  onRemove={() => removeMember(member.id)}
                />
              )}
            </li>
          ))}
        </ul>

        {adding ? (
          <MemberForm
            onSave={(name, fields) => { addMember(name, fields); setAdding(false); }}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button
            variant="outline"
            className="mt-4 h-11 rounded-full bg-card px-5"
            onClick={() => setAdding(true)}
          >
            <Plus className="size-4" />
            {t("household.add")}
          </Button>
        )}
      </section>

      <section>
        <Button
          className="h-12 rounded-full px-6 text-base"
          disabled={busy || named.length === 0}
          onClick={run}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          {busy ? t("household.running") : t("household.run")}
        </Button>
        {named.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            {t("household.needName")}
          </p>
        ) : null}
        {failed ? (
          <p className="mt-3 text-sm font-medium text-clay">
            {t("household.failed")}
          </p>
        ) : null}
      </section>

      {claims ? <Claims claims={claims} house={house} /> : null}
    </div>
  );
}

/** Whether this match names a group the person belongs to, rather than being
 *  open to everyone. Mirrors the engine's own `_TARGETING` set. */
const TARGETING = new Set([
  "caste", "BPL", "disability", "minority", "occupation",
  "economic distress", "land",
]);

function isTargeted(match: DiscoveryMatch): boolean {
  return match.matched_on.some((reason) => TARGETING.has(reason));
}

/* --------------------------------------------------------------- the house */

function SharedPanel({
  shared,
  onSave,
}: {
  shared: Shared;
  onSave: (next: Shared) => void;
}) {
  const { t } = useLanguage();
  const set = (key: keyof Shared, value: string) =>
    onSave({ ...shared, [key]: shared[key] === value ? undefined : value });

  return (
    <section className="card-quiet p-5 sm:p-6">
      <h2 className="font-display text-[1.25rem] font-normal">
        {t("household.shared")}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {t("household.shared.hint")}
      </p>

      <div className="mt-5 space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="hh-state" className="text-sm font-medium">
              {t("household.state")}
            </Label>
            <Input
              id="hh-state"
              value={shared.state ?? ""}
              onChange={(e) => onSave({ ...shared, state: e.target.value })}
              className="mt-2 h-12 rounded-xl bg-paper text-base"
            />
          </div>
          <div>
            <Label htmlFor="hh-income" className="text-sm font-medium">
              {t("household.income")}
            </Label>
            <Input
              id="hh-income"
              type="number"
              inputMode="numeric"
              value={shared.family_income ?? ""}
              onChange={(e) => onSave({ ...shared, family_income: e.target.value })}
              className="mt-2 h-12 rounded-xl bg-paper text-base"
            />
            <p className="mt-1.5 text-xs text-muted-foreground">
              {t("household.income.hint")}
            </p>
          </div>
        </div>

        <OptionRow
          label={t("household.residence")}
          options={RESIDENCE}
          value={shared.residence}
          onSelect={(v) => set("residence", v)}
        />
        <OptionRow
          label={t("household.caste")}
          options={CASTES}
          value={shared.caste}
          onSelect={(v) => set("caste", v)}
        />
        <OptionRow
          label={t("household.bpl")}
          options={YES_NO}
          value={shared.is_bpl}
          onSelect={(v) => set("is_bpl", v)}
        />
      </div>
    </section>
  );
}

/* -------------------------------------------------------------- one person */

function MemberCard({
  member,
  onEdit,
  onRemove,
}: {
  member: Member;
  onEdit: () => void;
  onRemove: () => void;
}) {
  const { t } = useLanguage();
  const facts = [
    member.age ? t("household.card.age", { age: member.age }) : null,
    member.gender
      ? t(GENDERS.find((g) => g.value === member.gender)?.key as never)
      : null,
    member.is_student === "yes" ? t("household.card.student") : null,
    member.disability === "yes" ? t("household.card.disability") : null,
    member.occupation,
  ].filter(Boolean);

  return (
    <div className="card-quiet flex h-full flex-col p-5">
      <div className="flex items-start justify-between gap-3">
        <h3 className="font-semibold">
          {member.name.trim() || t("household.card.unnamed")}
        </h3>
        <Button
          variant="ghost"
          size="icon"
          onClick={onRemove}
          aria-label={t("household.card.remove")}
        >
          <Trash2 className="size-4" />
        </Button>
      </div>
      <p className="mt-1 flex-1 text-sm text-muted-foreground">
        {facts.length ? facts.join(" · ") : t("household.card.nothingYet")}
      </p>
      <Button
        variant="outline"
        className="mt-3 h-9 self-start rounded-full bg-card px-4 text-sm"
        onClick={onEdit}
      >
        {t("household.card.edit")}
      </Button>
    </div>
  );
}

function MemberForm({
  member,
  onSave,
  onCancel,
}: {
  member?: Member;
  onSave: (name: string, fields: Partial<Member>) => void;
  onCancel: () => void;
}) {
  const { t } = useLanguage();
  const [draft, setDraft] = useState<Partial<Member>>(member ?? {});
  const [name, setName] = useState(member?.name ?? "");

  const set = (key: keyof Member, value: string) =>
    setDraft((prev) => ({
      ...prev,
      [key]: prev[key] === value ? undefined : value,
    }));

  return (
    <form
      className="card-quiet mt-4 space-y-5 p-5 sm:p-6"
      onSubmit={(event) => {
        event.preventDefault();
        onSave(name, draft);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <Label htmlFor="m-name" className="text-sm font-medium">
            {t("household.form.name")}
          </Label>
          <Input
            id="m-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("household.form.name.placeholder")}
            className="mt-2 h-12 rounded-xl bg-paper text-base"
          />
          <p className="mt-1.5 text-xs text-muted-foreground">
            {t("household.form.name.hint")}
          </p>
        </div>
        <div>
          <Label htmlFor="m-age" className="text-sm font-medium">
            {t("household.form.age")}
          </Label>
          <Input
            id="m-age"
            type="number"
            inputMode="numeric"
            value={draft.age ?? ""}
            onChange={(e) => setDraft((p) => ({ ...p, age: e.target.value }))}
            className="mt-2 h-12 rounded-xl bg-paper text-base"
          />
        </div>
      </div>

      <OptionRow
        label={t("household.form.gender")}
        options={GENDERS}
        value={draft.gender}
        onSelect={(v) => set("gender", v)}
      />
      <OptionRow
        label={t("household.form.student")}
        options={YES_NO}
        value={draft.is_student}
        onSelect={(v) => set("is_student", v)}
      />
      <OptionRow
        label={t("household.form.disability")}
        options={YES_NO}
        value={draft.disability}
        onSelect={(v) => set("disability", v)}
      />
      <OptionRow
        label={t("household.form.marital")}
        options={MARITAL}
        value={draft.marital_status}
        onSelect={(v) => set("marital_status", v)}
      />
      <OptionRow
        label={t("household.form.employment")}
        options={EMPLOYMENT}
        value={draft.employment_status}
        onSelect={(v) => set("employment_status", v)}
      />

      <div>
        <Label htmlFor="m-occupation" className="text-sm font-medium">
          {t("household.form.occupation")}
        </Label>
        <select
          id="m-occupation"
          value={draft.occupation ?? ""}
          onChange={(e) => setDraft((p) => ({ ...p, occupation: e.target.value }))}
          className="mt-2 h-12 w-full rounded-xl border border-input bg-paper px-3 text-base"
        >
          <option value="">{t("household.form.occupation.none")}</option>
          {OCCUPATIONS.map((occupation) => (
            <option key={occupation} value={occupation}>
              {occupation}
            </option>
          ))}
        </select>
      </div>

      <div className="flex gap-3">
        <Button type="submit" className="h-11 rounded-full px-5">
          {t("household.form.save")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="h-11 rounded-full px-5"
          onClick={onCancel}
        >
          {t("household.form.cancel")}
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------- the answers */

function Claims({ claims, house }: { claims: Claim[]; house: Household }) {
  const { t, lang } = useLanguage();
  const targeted = claims.filter((c) => c.targeted).length;

  if (claims.length === 0) {
    return (
      <section className="rounded-2xl border border-dashed border-input p-10 text-center">
        <h2 className="font-display text-[1.25rem] font-normal">
          {t("household.none.title")}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
          {t("household.none.body")}
        </p>
      </section>
    );
  }

  return (
    <section>
      <h2 className="font-display text-[1.5rem] font-light sm:text-[1.75rem]">
        {targeted > 0
          ? t("household.result.targeted", { count: targeted })
          : t("household.result.plain", { count: claims.length })}
      </h2>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
        {t("household.result.lede")}
      </p>

      <ul className="mt-6 space-y-3">
        {claims.map(({ match, members }) => (
          <li key={match.slug} className="card-quiet p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <h3 className="font-semibold leading-snug">
                <Link
                  href={`/schemes/${match.slug}`}
                  className="hover:text-primary"
                >
                  {match.name.trim()}
                </Link>
              </h3>
              {match.state && match.state !== "All" ? (
                <span className="text-xs text-muted-foreground">
                  {match.state}
                </span>
              ) : null}
            </div>

            {match.brief ? (
              <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-muted-foreground">
                {match.brief}
              </p>
            ) : null}

            {/* Who it is for, which is the entire point of this page. */}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                {t("household.claim.who")}
              </span>
              {members.map((member) => (
                <Link
                  key={member.id}
                  // Straight into the single-person check, already answered,
                  // so "why does it say that?" is one tap rather than a form.
                  href={`/check/results?${answersToQuery(
                    memberAnswers(house, member),
                  )}&scheme=${match.slug}`}
                  className={cn(
                    "rounded-full bg-secondary px-2.5 py-1 text-xs font-medium",
                    "text-primary hover:bg-primary hover:text-primary-foreground",
                  )}
                >
                  {member.name.trim() || t("household.card.unnamed")}
                </Link>
              ))}
            </div>

            {match.matched_on.length ? (
              <p className="mt-2 text-xs text-muted-foreground">
                {t("results.matchedOn", {
                  facets: facetList(lang, match.matched_on),
                })}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
