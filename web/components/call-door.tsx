"use client";

import { useMemo, useState } from "react";
import { Phone } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { WhatsAppDoor } from "@/components/whatsapp-door";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { LANGUAGE_META } from "@/lib/i18n/config";
import {
  CALL_CONFIGURED,
  CALL_IS_INDIAN,
  CALL_LANGUAGES,
  callDisplayNumber,
  callLink,
  callSpeaks,
} from "@/lib/call";
import { qrMatrix } from "@/lib/whatsapp";
import { cn } from "@/lib/utils";

/**
 * "Call and ask" — the door for someone with no smartphone.
 *
 * Shaped like the WhatsApp door on purpose. A person who has used one should
 * not have to learn the other, and the two sit side by side in the hero, so the
 * difference between them has to be the channel and nothing else.
 *
 * It differs in one way, deliberately: this renders NOTHING when no number is
 * configured, where the WhatsApp door shows a "set the env var" panel. That
 * panel is a developer affordance on the product's primary channel. A "Call the
 * helpline" button on a landing page that cannot place a call is not an
 * affordance, it is a promise being broken in public.
 */

/** Drawn the same way the WhatsApp QR is, so the two sheets are one design. */
function Qr({ text, className }: { text: string; className?: string }) {
  const { size, cells } = useMemo(() => qrMatrix(text), [text]);
  const pad = 4;
  const total = size + pad * 2;

  return (
    <svg
      viewBox={`0 0 ${total} ${total}`}
      className={className}
      role="img"
      aria-label={text}
      shapeRendering="crispEdges"
    >
      <rect width={total} height={total} fill="#ffffff" />
      {cells.map((row, y) =>
        row.map((dark, x) =>
          dark ? (
            <rect
              key={`${x}-${y}`}
              x={x + pad}
              y={y + pad}
              width={1}
              height={1}
              fill="var(--forest-deep)"
            />
          ) : null,
        ),
      )}
    </svg>
  );
}

/** The languages the line speaks, written out in the reader's own language. */
function spokenLanguages(): string {
  return CALL_LANGUAGES.map((code) => LANGUAGE_META[code]?.native ?? code).join(" · ");
}

export function CallDoor({
  label,
  variant = "outline",
  size = "pill",
  className,
}: {
  label?: string;
  variant?: "whatsapp" | "soft" | "outline" | "ghost";
  size?: "pill" | "pill-lg" | "pill-sm";
  className?: string;
}) {
  const { t, lang } = useLanguage();
  const [open, setOpen] = useState(false);

  // Nothing to offer, so nothing is offered. See the component docstring.
  if (!CALL_CONFIGURED) return null;

  const speaks = callSpeaks(lang);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant={variant} size={size} className={cn("font-medium", className)}>
            <Phone className="size-[18px]" />
            {label ?? t("call.open")}
          </Button>
        }
      />
      <DialogContent className="max-w-[calc(100%-2rem)] gap-0 rounded-3xl p-0 sm:max-w-[26rem]">
        <div className="px-7 pt-7 text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-verified-soft text-verified">
            <Phone className="size-6" />
          </span>
          <DialogTitle className="mt-4 font-display text-[1.5rem] font-light tracking-[-0.02em]">
            {t("call.title")}
          </DialogTitle>
          <DialogDescription className="mt-2 text-[0.9375rem] leading-relaxed text-muted-foreground">
            {t("call.body")}
          </DialogDescription>
        </div>

        {/*
          The two warnings come BEFORE the number, not under it. A person who has
          already read the digits has already decided to dial; telling them the
          cost afterwards is a disclaimer, not a warning.
        */}
        {!speaks ? (
          <div className="mx-7 mt-5 rounded-2xl border border-input bg-muted/60 px-4 py-3.5">
            <p className="text-[0.8125rem] leading-relaxed">
              {t("call.otherLanguage")}
            </p>
            <div className="mt-3">
              <WhatsAppDoor size="pill-sm" variant="whatsapp" />
            </div>
          </div>
        ) : null}

        {!CALL_IS_INDIAN ? (
          <div className="mx-7 mt-4 rounded-2xl border border-gold/30 bg-gold-soft px-4 py-3.5 text-gold-ink">
            <p className="text-[0.8125rem] leading-relaxed">
              {t("call.international")}
            </p>
          </div>
        ) : null}

        <div className="px-7 pt-6">
          <div className="mx-auto w-fit rounded-2xl border border-border bg-white p-3 shadow-[0_1px_2px_rgb(28_26_23/0.05)]">
            <Qr text={callLink()} className="size-44" />
          </div>

          <p className="mt-4 text-center">
            <span className="meta">{t("call.helpline")}</span>
            {/* Selectable and copyable: a feature phone is dialled by hand. */}
            <a
              href={callLink()}
              className="mt-1 block tnum text-[1.0625rem] font-medium underline-offset-4 hover:underline"
            >
              {callDisplayNumber()}
            </a>
            <span className="mt-1 block text-[0.8125rem] text-faint">
              {t("call.scanHint")}
            </span>
            <span className="mt-2 block text-[0.8125rem] text-faint">
              {t("call.languages")}{" "}
              <span className="font-medium text-foreground">{spokenLanguages()}</span>
            </span>
          </p>
        </div>

        <div className="mt-6 border-t border-border px-7 py-5">
          <Button
            nativeButton={false}
            size="pill"
            className="w-full"
            render={<a href={callLink()}>{t("call.launch")}</a>}
          />
          <DialogClose
            render={
              <Button variant="ghost" size="pill" className="mt-2 w-full text-muted-foreground">
                {t("call.dismiss")}
              </Button>
            }
          />
          {/*
            Said on the page as well as on the call. Someone deciding whether to
            ring a government-looking number wants to know this before they dial,
            and the commonest fraud against this audience is a phone call asking
            for exactly what we promise never to ask for.
          */}
          <p className="mt-3 text-center text-[0.75rem] leading-relaxed text-faint">
            {t("call.safety")}
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
