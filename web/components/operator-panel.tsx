"use client";

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, LogOut, Loader2, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useLanguage } from "@/components/language-provider";

/**
 * The counter, from the operator's side.
 *
 * A CSC operator, an NGO worker or an SCA field agent, helping somebody who is
 * standing in front of them. `PRD-v3.md` §6.3 calls assisted mode "load-bearing,
 * not a nice-to-have" — it is the only part of the design that attacks the
 * awareness problem directly, because it reaches the people who will never open
 * a website.
 *
 * WHAT THIS SCREEN CANNOT DO, BY CONSTRUCTION
 *
 * There is no "new case" button, and no route behind one. An operator cannot
 * put somebody's household into this panel; the citizen mints a code and reads
 * it out, and that is the only way anything gets here. The citizen can revoke
 * it with the same code, from their own phone, without an account.
 *
 * So the first thing this screen does is ask for a code. That is not a step
 * before the real work — it IS the consent, and the panel has nothing to show
 * until it is given.
 */

interface Operator {
  operator_id: string;
  name: string;
  role: string;
  email: string;
}

interface Case {
  case_id: string;
  code: string;
  scheme_slug: string | null;
  language: string;
  created_at: string;
  claimed_at: string | null;
  context?: Record<string, string> | null;
}

async function api(path: string, init?: RequestInit) {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    // The session is a cookie, and a cross-origin fetch drops it by default.
    credentials: "include",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export function OperatorPanel() {
  const { t } = useLanguage();
  const [operator, setOperator] = useState<Operator | null>(null);
  const [checking, setChecking] = useState(true);
  const [cases, setCases] = useState<Case[]>([]);
  const [open, setOpen] = useState<Case | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const loadCases = useCallback(async () => {
    try {
      setCases(await api("/api/operator/cases"));
    } catch {
      setCases([]);
    }
  }, []);

  useEffect(() => {
    // Asked on load rather than assumed from a flag in storage: the session
    // may have expired, or been revoked, and the only authority on that is the
    // server.
    api("/api/operator/me")
      .then((me) => { setOperator(me); return loadCases(); })
      .catch(() => setOperator(null))
      .finally(() => setChecking(false));
  }, [loadCases]);

  if (checking) {
    return (
      <div className="flex justify-center py-24">
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!operator) {
    return <SignIn onSignedIn={(me) => { setOperator(me); void loadCases(); }} />;
  }

  if (open) {
    return (
      <CaseDetail
        theCase={open}
        onBack={() => { setOpen(null); void loadCases(); }}
      />
    );
  }

  async function claim(code: string) {
    setBusy(true);
    setError("");
    try {
      const claimed: Case = await api("/api/operator/cases/claim", {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      setOpen(claimed);
    } catch (problem) {
      // The engine's refusals are written to be read out at a counter —
      // "Another operator is already helping with this case" is a different
      // next action from "Check the letters and try again".
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {t("operator.signedInAs", { name: operator.name })}
        </p>
        <Button
          variant="ghost"
          className="h-9 rounded-full px-4 text-sm"
          onClick={async () => {
            await api("/api/operator/logout", { method: "POST" }).catch(() => {});
            setOperator(null);
            setCases([]);
          }}
        >
          <LogOut className="size-4" />
          {t("operator.signout")}
        </Button>
      </div>

      <ClaimBox onClaim={claim} busy={busy} error={error} />

      <section>
        <h2 className="font-display text-[1.25rem] font-normal">
          {t("operator.cases")}
        </h2>
        {cases.length === 0 ? (
          <p className="mt-3 max-w-[58ch] text-sm leading-relaxed text-muted-foreground">
            {t("operator.cases.empty")}
          </p>
        ) : (
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {cases.map((one) => (
              <li key={one.case_id}>
                <button
                  type="button"
                  onClick={() => setOpen(one)}
                  className="card-quiet w-full p-5 text-start transition-colors hover:border-primary/40"
                >
                  <p className="font-mono text-sm font-medium">{one.code}</p>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    {one.scheme_slug || t("operator.case.noScheme")}
                  </p>
                  <p className="mt-2 text-xs text-faint">
                    {t("operator.case.language", { language: one.language })}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SignIn({ onSignedIn }: { onSignedIn: (me: Operator) => void }) {
  const { t } = useLanguage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <form
      className="card-quiet mx-auto max-w-md space-y-5 p-6 sm:p-8"
      onSubmit={async (event) => {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
          onSignedIn(await api("/api/operator/login", {
            method: "POST",
            body: JSON.stringify({ email, password }),
          }));
        } catch (problem) {
          setError((problem as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <div className="flex items-center gap-2.5">
        <span className="flex size-9 items-center justify-center rounded-xl bg-secondary text-primary">
          <ShieldCheck className="size-4.5" />
        </span>
        <h2 className="font-display text-[1.25rem] font-normal">
          {t("operator.signin")}
        </h2>
      </div>

      <div>
        <Label htmlFor="op-email" className="text-sm font-medium">
          {t("operator.email")}
        </Label>
        <Input
          id="op-email" type="email" required autoComplete="username"
          value={email} onChange={(e) => setEmail(e.target.value)}
          className="mt-2 h-12 rounded-xl bg-paper text-base"
        />
      </div>
      <div>
        <Label htmlFor="op-password" className="text-sm font-medium">
          {t("operator.password")}
        </Label>
        <Input
          id="op-password" type="password" required
          autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)}
          className="mt-2 h-12 rounded-xl bg-paper text-base"
        />
      </div>

      {error ? <p className="text-sm font-medium text-clay">{error}</p> : null}

      <Button type="submit" disabled={busy} className="h-11 w-full rounded-full">
        {busy ? <Loader2 className="size-4 animate-spin" /> : null}
        {t("operator.signin.cta")}
      </Button>

      <p className="text-xs leading-relaxed text-faint">
        {t("operator.signin.note")}
      </p>
    </form>
  );
}

function ClaimBox({
  onClaim, busy, error,
}: {
  onClaim: (code: string) => void;
  busy: boolean;
  error: string;
}) {
  const { t } = useLanguage();
  const [code, setCode] = useState("");

  return (
    <form
      className="card-quiet p-5 sm:p-6"
      onSubmit={(event) => { event.preventDefault(); onClaim(code); }}
    >
      <h2 className="font-display text-[1.25rem] font-normal">
        {t("operator.claim.title")}
      </h2>
      <p className="mt-1.5 max-w-[62ch] text-sm leading-relaxed text-muted-foreground">
        {t("operator.claim.hint")}
      </p>
      <div className="mt-4 flex flex-col gap-3 sm:flex-row">
        <Input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="YC-ABC234"
          // Uppercase and monospace because it is read aloud across a desk and
          // typed back a character at a time.
          className="h-12 rounded-xl bg-paper font-mono text-base uppercase sm:max-w-[16rem]"
        />
        <Button type="submit" disabled={busy || !code.trim()}
                className="h-12 rounded-full px-6">
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          {t("operator.claim.cta")}
        </Button>
      </div>
      {error ? (
        <p className="mt-3 text-sm font-medium text-clay">{error}</p>
      ) : null}
    </form>
  );
}

function CaseDetail({
  theCase, onBack,
}: {
  theCase: Case;
  onBack: () => void;
}) {
  const { t } = useLanguage();
  const [busy, setBusy] = useState(false);
  const answers = Object.entries(theCase.context || {});

  return (
    <div>
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary"
      >
        <ArrowLeft className="size-4" />
        {t("operator.case.back")}
      </button>

      <h2 className="mt-5 font-mono text-[1.25rem]">{theCase.code}</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        {t("operator.case.language", { language: theCase.language })}
      </p>

      <section className="mt-7">
        <h3 className="text-sm font-semibold">{t("operator.case.answers")}</h3>
        {answers.length === 0 ? (
          <p className="mt-2 text-sm text-muted-foreground">
            {t("operator.case.noAnswers")}
          </p>
        ) : (
          <dl className="mt-3 grid gap-x-8 gap-y-2 sm:grid-cols-2">
            {answers.map(([key, value]) => (
              <div key={key} className="flex justify-between gap-4 border-b border-border py-2 text-sm">
                <dt className="text-muted-foreground">{key}</dt>
                <dd className="font-medium">{String(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <p className="mt-7 max-w-[62ch] rounded-xl bg-gold-soft p-4 text-sm leading-relaxed text-gold-ink">
        {t("operator.case.consent")}
      </p>

      <Button
        className="mt-6 h-11 rounded-full px-5"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          await api(`/api/operator/cases/${theCase.case_id}/close`,
                    { method: "POST" }).catch(() => {});
          setBusy(false);
          onBack();
        }}
      >
        {busy ? <Loader2 className="size-4 animate-spin" /> : null}
        {t("operator.case.close")}
      </Button>
    </div>
  );
}
