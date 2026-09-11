"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, LocateFixed, MapPin, X } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { announcePlace } from "@/components/language-suggestion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PLACE_COOKIE, PLACE_ASKED_COOKIE } from "@/lib/i18n/config";
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
    const cookies = document.cookie;
    if (cookies.includes(`${PLACE_ASKED_COOKIE}=1`) || cookies.includes(`${PLACE_COOKIE}=`)) {
      return;
    }
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
      document.cookie = `${PLACE_ASKED_COOKIE}=1; path=/; max-age=31536000; samesite=lax`;
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
    if (!window.isSecureContext || !("geolocation" in navigator)) {
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
      () => {
        setBusy(false);
        setNote(t("check.location.denied"));
      },
      { timeout: 10000, maximumAge: 300000 },
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

          <Input
            inputMode="numeric"
            maxLength={6}
            value={pin}
            placeholder={t("location.pin.placeholder")}
            aria-label={t("check.location.pin")}
            className="h-11 bg-paper text-base"
            onChange={(event) => {
              const value = event.target.value.replace(/\D/g, "").slice(0, 6);
              setPin(value);
              if (value.length === 6) void lookupPin(value);
            }}
          />

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
