"use client";

import { useMemo, useState } from "react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  qrMatrix,
  whatsappDisplayNumber,
  whatsappLink,
  WHATSAPP_CONFIGURED,
} from "@/lib/whatsapp";
import { cn } from "@/lib/utils";

/** WhatsApp's own glyph. Recognised instantly; a generic speech bubble is not. */
export function WhatsAppGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className ?? "size-4"} aria-hidden="true" fill="currentColor">
      <path d="M17.47 14.38c-.3-.15-1.75-.86-2.02-.96-.27-.1-.47-.15-.67.15-.2.3-.77.96-.94 1.16-.17.2-.35.22-.64.08-.3-.15-1.25-.46-2.38-1.47-.88-.78-1.47-1.75-1.65-2.05-.17-.3-.02-.46.13-.6.13-.14.3-.35.45-.53.15-.18.2-.3.3-.5.1-.2.05-.38-.02-.53-.08-.15-.67-1.61-.92-2.2-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.01-1.04 2.47s1.06 2.86 1.21 3.06c.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.69.63.71.22 1.36.19 1.87.12.57-.09 1.75-.72 2-1.41.25-.7.25-1.29.17-1.42-.07-.13-.27-.2-.57-.35z"/>
      <path d="M12.04 2C6.6 2 2.18 6.42 2.18 11.86c0 1.74.46 3.44 1.32 4.94L2 22l5.34-1.4a9.83 9.83 0 0 0 4.7 1.2h.01c5.43 0 9.85-4.42 9.85-9.86 0-2.63-1.02-5.11-2.88-6.97A9.79 9.79 0 0 0 12.04 2zm0 1.83c2.15 0 4.17.84 5.69 2.36a7.99 7.99 0 0 1 2.36 5.68c0 4.43-3.61 8.03-8.05 8.03a8.2 8.2 0 0 1-4.16-1.14l-.3-.18-3.1.81.83-3.02-.2-.31a7.96 7.96 0 0 1-1.23-4.26c0-4.43 3.61-8.03 8.05-8.03z"/>
    </svg>
  );
}

/**
 * The QR, drawn as SVG.
 *
 * Rounded modules and a hole in the middle for the mark: a QR reads fine with
 * up to 30% of its area obscured at this error-correction level, and a code
 * that looks designed gets scanned where a raw black square looks like spam.
 */
function Qr({ text, className }: { text: string; className?: string }) {
  const { size, cells } = useMemo(() => qrMatrix(text), [text]);
  // A four-module quiet zone is part of the spec, not a margin — scanners
  // genuinely fail without it.
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

/**
 * The code, mounted in the page rather than behind a button.
 *
 * The whole tile is the link, so the panel works for both readers at once: a
 * laptop reader points their phone at it, and a phone reader taps it. A QR
 * that only a second device can use is dead weight on the device most of this
 * audience is actually holding.
 */
export function WhatsAppQrPanel({ className }: { className?: string }) {
  const { t } = useLanguage();
  const href = whatsappLink(t("wa.prefill"));
  if (!WHATSAPP_CONFIGURED) return null;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={cn(
        "lift group block w-fit rounded-[1.25rem] bg-white p-4 text-center shadow-[0_18px_44px_-20px_rgba(0,0,0,0.5)]",
        className,
      )}
    >
      <Qr text={href} className="size-[8.25rem]" />
      <span className="tnum mt-3 block text-[0.8125rem] font-semibold text-forest-deep">
        {whatsappDisplayNumber()}
      </span>
      <span className="mt-0.5 block text-[0.6875rem] text-faint">
        {t("wa.scanTap")}
      </span>
    </a>
  );
}

/**
 * "Continue on WhatsApp" — a button that opens a sheet with a code you can
 * point a second phone at.
 *
 * Two doors, because two different people arrive here: someone reading on a
 * laptop who wants the conversation on the phone in their pocket (the QR), and
 * someone already on that phone (the link). Showing a QR to a phone user is a
 * dead end, so the link is a real button, not a footnote.
 */
export function WhatsAppDoor({
  prefill,
  label,
  variant = "whatsapp",
  size = "pill",
  className,
}: {
  prefill?: string;
  label?: string;
  variant?: "whatsapp" | "soft" | "outline" | "ghost";
  size?: "pill" | "pill-lg" | "pill-sm";
  className?: string;
}) {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  // The opening message is translated, so the QR a Tamil reader scans encodes
  // a Tamil greeting and the assistant answers in Tamil from the first reply.
  const href = whatsappLink(prefill ?? t("wa.prefill"));

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button variant={variant} size={size} className={cn("font-medium", className)}>
            <WhatsAppGlyph className="size-[18px]" />
            {label ?? t("wa.open")}
          </Button>
        }
      />
      <DialogContent className="max-w-[calc(100%-2rem)] gap-0 rounded-3xl p-0 sm:max-w-[26rem]">
        <div className="px-7 pt-7 text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-verified-soft text-verified">
            <WhatsAppGlyph className="size-6" />
          </span>
          <DialogTitle className="mt-4 font-display text-[1.5rem] font-light tracking-[-0.02em]">
            {t("wa.title")}
          </DialogTitle>
          <DialogDescription className="mt-2 text-[0.9375rem] leading-relaxed text-muted-foreground">
            {t("wa.body")}
          </DialogDescription>
        </div>

        <div className="px-7 pt-6">
          {WHATSAPP_CONFIGURED ? (
            <div className="mx-auto w-fit rounded-2xl border border-border bg-white p-3 shadow-[0_1px_2px_rgb(28_26_23/0.05)]">
              <Qr text={href} className="size-44" />
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-input bg-muted/60 px-5 py-8 text-center">
              <p className="text-sm font-medium">{t("wa.unset.title")}</p>
              <p className="mt-1.5 text-[0.8125rem] leading-relaxed text-muted-foreground">
                {t("wa.unset.body")}
              </p>
            </div>
          )}

          <p className="mt-4 text-center">
            <span className="meta">{t("wa.helpline")}</span>
            <span className="mt-1 block tnum text-[1.0625rem] font-medium">
              {whatsappDisplayNumber()}
            </span>
            <span className="mt-1 block text-[0.8125rem] text-faint">
              {t("wa.scanHint")}
            </span>
          </p>
        </div>

        <div className="mt-6 border-t border-border px-7 py-5">
          <Button
            nativeButton={false}
            size="pill"
            className="w-full"
            disabled={!WHATSAPP_CONFIGURED}
            render={
              <a href={href} target="_blank" rel="noopener noreferrer" />
            }
          >
            <WhatsAppGlyph className="size-[18px]" />
            {t("wa.launch")}
          </Button>
          <DialogClose
            render={
              <Button variant="ghost" size="pill" className="mt-1.5 w-full text-muted-foreground" />
            }
          >
            {t("wa.dismiss")}
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}
