"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, LocateFixed, MapPin, X } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { announcePlace } from "@/components/language-suggestion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  PLACE_COOKIE,
  PLACE_ASKED_COOKIE,
  LEGACY_PLACE_ASKED_COOKIE,
} from "@/lib/i18n/config";
import { cn } from "@/lib/utils";

/**
 * Asked once, on the first visit: where are you?
 *
 * It earns its interruption. State is the single most consequential thing about
 * a person here — most schemes are run by one state, so knowing it changes the
 * answer more than caste, income or age do — and it is also what lets us offer
 * the interface in the language that state administers in, before they have
 * struggled through a page they cannot read.
 *
 * Three ways in and a way out. Nothing is required, skipping is remembered, and
 * the browser's own permission prompt only fires when the person taps the
 * button that says it will: a page that demands location on load is a page
 * people reflexively deny and then distrust.
 */
/** Ask for the location again, from anywhere. */
export function askForLocation(): void {
  window.dispatchEvent(new Event("yojnasetu:ask-location"));
}

export function LocationGate({ states }: { states: string[] }) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  useEffect(() => {
    // Clear the year-long dismissal the old build wrote. Without this, anyone
    // who ever tapped "skip" would keep being not-asked until 2027, which is
    // the bug rather than the fix.
    document.cookie = `${LEGACY_PLACE_ASKED_COOKIE}=; path=/; max-age=0; samesite=lax`;

    const cookies = document.cookie;
    // Knowing the state is the end of it — never ask again.
    if (cookies.includes(`${PLACE_COOKIE}=`)) return;
    // Not knowing it, but having asked already, is NOT the end of it. The
    // dismissal cookie is session-scoped (see `close`), so a skip quiets this
    // for the rest of the visit and the next visit asks again. Making it
    // permanent meant one mis-tap left the product without the single most
    // consequential thing it can know about somebody — most schemes are run by
    // one state — with no prompt ever offered again.
    if (cookies.includes(`${PLACE_ASKED_COOKIE}=1`)) return;
    // A beat before appearing, so the page paints first and the person can see
    // what they have arrived at before being asked anything.
    //
    // Deliberately no ref guard around this. One here would be defeated by
    // StrictMode, which runs the effect, tears it down — clearing the timer —
    // then runs it again and hits the guard, so the prompt never appears at
    // all. The cleanup is the whole mechanism; let it do its job.
    const timer = setTimeout(() => setOpen(true), 900);
    return () => clearTimeout(timer);
  }, []);

  // Anywhere in the interface can ask for this again — someone who skipped on
  // arrival, or whose answer is now wrong, must not be stuck with it. Dismissal
  // is remembered; it is not a life sentence.
  useEffect(() => {
    const reopen = () => setOpen(true);
    window.addEventListener("yojnasetu:ask-location", reopen);
    return () => window.removeEventListener("yojnasetu:ask-location", reopen);
  }, []);

  const close = useCallback((remember = true) => {
    setOpen(false);
    if (remember) {
      // No max-age: a session cookie. Quiet for this visit, asked again on the
      // next one — for as long as we still do not know where they are.
      document.cookie = `${PLACE_ASKED_COOKIE}=1; path=/; samesite=lax`;
    }
  }, []);

  const accept = useCallback(
    (state: string, label?: string) => {
      document.cookie =
        `${PLACE_COOKIE}=${encodeURIComponent(state)}; path=/; max-age=31536000; samesite=lax`;
      setNote(label ?? state);
      announcePlace(state);
      // Long enough to read what was found, short enough not to be in the way.
      setTimeout(() => close(), 1200);
    },
    [close],
  );

  const useMyLocation = () => {
    if (!("geolocation" in navigator)) {
      setNote(t("check.location.unavailable"));
      return;
    }
    // Browsers only offer location on a secure origin. localhost counts as one;
    // a LAN address like 192.168.1.5:3100 does not — which is exactly how this
    // gets opened from a phone during testing, and the button then does nothing
    // with no explanation at all.
    if (!window.isSecureContext) {
      setNote(t("check.location.insecure"));
      return;
    }
    setBusy(true);
    setNote(null);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { latitude, longitude } = position.coords;
          const response = await fetch(`/api/geo/reverse?lat=${latitude}&lon=${longitude}`);
          const place = await response.json();
          if (place.state) {
            accept(place.state, [place.district, place.state].filter(Boolean).join(", "));
          } else {
            setNote(t("check.location.failed"));
          }
        } catch {
          setNote(t("check.location.failed"));
        } finally {
          setBusy(false);
        }
      },
      (error) => {
        setBusy(false);
        // Three very different failures used to share one message. "Location
        // was not shared" told someone whose browser had simply timed out that
        // they had refused, and told someone who HAD refused nothing about
        // where to change it — so neither could act, and both concluded the
        // button was broken.
        if (error.code === error.PERMISSION_DENIED) {
          setNote(t("check.location.blocked"));
        } else if (error.code === error.TIMEOUT) {
          setNote(t("check.location.timeout"));
        } else {
          setNote(t("check.location.unavailable"));
        }
      },
      // 20s, and a fix up to five minutes old is fine. The old 10s reported a
      // timeout as a refusal on exactly the slow devices this is built for.
      { timeout: 20000, maximumAge: 300000, enableHighAccuracy: false },
    );
  };

  const lookupPin = async (value: string) => {
    setBusy(true);
    setNote(null);
    try {
      const response = await fetch(`/api/geo/pin/${value}`);
      const place = await response.json();
      if (place.state) {
        accept(place.state, [place.district, place.state].filter(Boolean).join(", "));
      } else {
        setNote(t("check.location.badpin"));
      }
    } catch {
      setNote(t("check.location.failed"));
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center">
      <div
        className="absolute inset-0 bg-foreground/25 backdrop-blur-[2px]"
        aria-hidden
        onClick={() => close()}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="location-gate-title"
        className={cn(
          "relative w-full max-w-md border border-border bg-card p-6 shadow-xl",
          "rounded-t-2xl sm:rounded-2xl",
        )}
      >
        <Button
          variant="ghost"
          size="icon"
          className="absolute end-3 top-3 size-8"
          onClick={() => close()}
          aria-label={t("location.skip")}
        >
          <X className="size-4" />
        </Button>

        <span className="flex size-11 items-center justify-center rounded-xl bg-secondary text-primary">
          <MapPin className="size-5" />
        </span>

        <h2 id="location-gate-title" className="mt-4 font-display text-xl font-bold">
          {t("location.title")}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          {t("location.why")}
        </p>

        <div className="mt-5 space-y-3">
          <Button
            className="h-11 w-full"
            onClick={useMyLocation}
            disabled={busy}
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : <LocateFixed className="size-4" />}
            {t("check.location.use")}
          </Button>

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            {t("location.or")}
            <span className="h-px flex-1 bg-border" />
          </div>

          {/* A form, so Enter submits — on a phone keyboard the "go" key is
              what a person reaches for, and the six-digit auto-fire alone left
              anyone who paused mid-number with no way to ask. The auto-fire is
              kept because it usually saves the tap. */}
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (pin.length === 6) void lookupPin(pin);
            }}
          >
            <Input
              inputMode="numeric"
              maxLength={6}
              value={pin}
              disabled={busy}
              placeholder={t("location.pin.placeholder")}
              aria-label={t("check.location.pin")}
              className="h-11 flex-1 bg-paper text-base"
              onChange={(event) => {
                const value = event.target.value.replace(/\D/g, "").slice(0, 6);
                setPin(value);
                if (value.length === 6) void lookupPin(value);
              }}
            />
            <Button
              type="submit"
              variant="outline"
              className="h-11 px-4"
              disabled={busy || pin.length !== 6}
            >
              {busy ? <Loader2 className="size-4 animate-spin" /> : t("check.location.find")}
            </Button>
          </form>

          <select
            aria-label={t("check.location.state")}
            className="h-11 w-full rounded-lg border border-input bg-paper px-3 text-base"
            defaultValue=""
            onChange={(event) => {
              if (event.target.value) accept(event.target.value);
            }}
          >
            <option value="">{t("location.pickState")}</option>
            {states.map((state) => (
              <option key={state} value={state}>
                {state}
              </option>
            ))}
          </select>
        </div>

        {note ? (
          <p className="mt-4 flex items-start gap-1.5 rounded-lg bg-muted/60 p-3 text-sm text-muted-foreground">
            <MapPin className="mt-0.5 size-3.5 shrink-0" />
            {note}
          </p>
        ) : null}

        <button
          type="button"
          onClick={() => close()}
          className="mt-4 w-full text-sm font-medium text-muted-foreground underline-offset-4 hover:underline"
        >
          {t("location.skip")}
        </button>
      </div>
    </div>
  );
}
