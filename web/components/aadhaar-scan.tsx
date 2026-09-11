"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, Check, ImageUp, Loader2, ShieldCheck, X } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";
import type { Profile } from "@/lib/profile";
import { cn } from "@/lib/utils";

/**
 * Filling the form by pointing the camera at an Aadhaar card.
 *
 * Eleven fields on a phone keyboard — often in a script the on-screen keyboard
 * makes hard — is the biggest drop-off in this product. UIDAI's offline e-KYC
 * file avoids the typing but costs about seven steps and an OTP on their
 * website, which is worse. The QR already printed on the card costs three:
 * tap, allow the camera, point it at the card.
 *
 * THE PHOTOGRAPH NEVER LEAVES THE PHONE
 *
 * Frames are decoded in the browser and thrown away. What goes to our server
 * is the decoded string, and what comes back is a name and an address. We
 * never receive, and could not store, a picture of somebody's ID.
 *
 * TWO DECODERS
 *
 * `BarcodeDetector` is native in Chrome on Android — the browser this audience
 * actually uses — and is both faster and better in poor light than anything
 * shipped as JavaScript. It is absent on Windows desktop Chrome and in Safari,
 * so jsQR covers those. The native one is tried first and the fallback is only
 * loaded when it is needed, which keeps the cost off the phones that do not
 * pay it.
 *
 * A LIVE CAMERA IS NOT ALWAYS ENOUGH
 *
 * The Secure QR is dense, and a worn card in a dim room will defeat autofocus
 * on a cheap phone. So a still photograph is a first-class route, not a
 * consolation: a picture can be retried, held steady and zoomed, where a live
 * preview just keeps failing. Typing remains underneath both.
 */

type Phase = "idle" | "starting" | "scanning" | "reading" | "done";

interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<{ rawValue: string }[]>;
}

function nativeDetector(): BarcodeDetectorLike | null {
  const w = window as unknown as {
    BarcodeDetector?: new (o: { formats: string[] }) => BarcodeDetectorLike;
  };
  if (!w.BarcodeDetector) return null;
  try {
    return new w.BarcodeDetector({ formats: ["qr_code"] });
  } catch {
    return null;
  }
}

/** jsQR, loaded only where the browser has no decoder of its own. */
async function decodeWithFallback(
  data: ImageData,
): Promise<string | null> {
  const { default: jsQR } = await import("jsqr");
  // `dontInvert` is wrong for a printed card photographed under a lamp, where
  // the QR often comes through inverted.
  const found = jsQR(data.data, data.width, data.height, {
    inversionAttempts: "attemptBoth",
  });
  return found?.data ?? null;
}

export function AadhaarScan({
  onFilled,
  onClose,
}: {
  onFilled: (
    profile: Profile,
    verified: boolean,
    last4: string,
    card: Record<string, string>,
  ) => void;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);
  const detectorRef = useRef<BarcodeDetectorLike | null>(null);
  const busyRef = useRef(false);

  const stop = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  useEffect(() => () => stop(), [stop]);

  /** Send a decoded string up, and let the sheet fill itself in. */
  const submit = useCallback(
    async (qr: string) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setPhase("reading");
      try {
        const response = await fetch("/api/aadhaar/qr", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ qr }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          setError(body.detail || t("aadhaar.unreadable"));
          setPhase("scanning");
          busyRef.current = false;
          return;
        }
        const data = await response.json();
        stop();
        setPhase("done");
        onFilled(data.profile ?? {}, Boolean(data.verified),
                 data.aadhaar_last4 ?? "", data.card ?? {});
      } catch {
        setError(t("aadhaar.failed"));
        setPhase("scanning");
        busyRef.current = false;
      }
    },
    [onFilled, stop, t],
  );

  /** One frame, through whichever decoder this browser has. */
  const readFrame = useCallback(async (): Promise<string | null> => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;

    if (detectorRef.current) {
      const found = await detectorRef.current.detect(video).catch(() => []);
      if (found.length) return found[0].rawValue;
      return null;
    }

    // The fallback needs pixels, so the frame goes through a canvas. Capped so
    // a 4K front camera does not cost a full-resolution copy every frame.
    const scale = Math.min(1, 1000 / (video.videoWidth || 1));
    canvas.width = Math.round((video.videoWidth || 0) * scale);
    canvas.height = Math.round((video.videoHeight || 0) * scale);
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context || !canvas.width) return null;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    return decodeWithFallback(
      context.getImageData(0, 0, canvas.width, canvas.height),
    );
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setPhase("starting");
    detectorRef.current = nativeDetector();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        // The back camera, and enough resolution for a dense QR — the default
        // 640×480 will not resolve one from a card held at arm's length.
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setPhase("scanning");

      const tick = async () => {
        if (!streamRef.current) return;
        const found = await readFrame().catch(() => null);
        if (found) {
          void submit(found);
          return;
        }
        rafRef.current = requestAnimationFrame(() => void tick());
      };
      void tick();
    } catch {
      setPhase("idle");
      setError(t("aadhaar.noCamera"));
    }
  }, [readFrame, submit, t]);

  /** A still photograph — retriable, steady, and zoomable in a way a live
   *  preview is not. This is the rung that catches a worn card. */
  const fromFile = useCallback(
    async (file: File) => {
      setError(null);
      setPhase("reading");
      try {
        const bitmap = await createImageBitmap(file);
        const canvas = canvasRef.current ?? document.createElement("canvas");
        const scale = Math.min(1, 1600 / bitmap.width);
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("no canvas");
        context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);

        const detector = detectorRef.current ?? nativeDetector();
        let text: string | null = null;
        if (detector) {
          const found = await detector.detect(canvas).catch(() => []);
          text = found.length ? found[0].rawValue : null;
        }
        if (!text) {
          text = await decodeWithFallback(
            context.getImageData(0, 0, canvas.width, canvas.height),
          );
        }
        if (!text) {
          setError(t("aadhaar.notFoundInPhoto"));
          setPhase("idle");
          return;
        }
        await submit(text);
      } catch {
        setError(t("aadhaar.unreadable"));
        setPhase("idle");
      }
    },
    [submit, t],
  );

  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-semibold">
            {t("aadhaar.title")}
          </h3>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            {t("aadhaar.lede")}
          </p>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => {
            stop();
            onClose();
          }}
          aria-label={t("aadhaar.close")}
          className="size-9 shrink-0 rounded-full"
        >
          <X className="size-4" />
        </Button>
      </div>

      {/* Capped and centred: 4:3 across a full desktop column is a
          viewfinder taller than the page, and a card is held close
          anyway — the frame does not need to be large to aim with. */}
      <div className="relative mx-auto mt-4 w-full max-w-sm overflow-hidden rounded-xl bg-muted">
        <video
          ref={videoRef}
          playsInline
          muted
          className={cn(
            "aspect-[4/3] w-full object-cover",
            phase === "scanning" || phase === "reading" ? "block" : "hidden",
          )}
        />
        {phase === "scanning" ? (
          // A frame to aim with. People hold the card too far away otherwise,
          // and a dense QR simply will not resolve at arm's length.
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 flex items-center justify-center"
          >
            <div className="size-2/3 rounded-xl border-2 border-white/80 shadow-[0_0_0_100vmax_rgb(0_0_0/0.35)]" />
          </div>
        ) : null}

        {phase === "idle" || phase === "starting" ? (
          <div className="flex aspect-[4/3] w-full flex-col items-center justify-center gap-3 px-6 text-center">
            <Camera className="size-7 text-faint" />
            <p className="text-sm text-muted-foreground">{t("aadhaar.aim")}</p>
          </div>
        ) : null}
      </div>

      <canvas ref={canvasRef} className="hidden" />

      {error ? (
        <p role="status" className="mt-3 text-sm leading-relaxed text-clay">
          {error}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {phase === "idle" ? (
          <Button type="button" onClick={() => void start()} className="h-10">
            <Camera className="size-4" />
            {t("aadhaar.start")}
          </Button>
        ) : null}
        {phase === "starting" || phase === "reading" ? (
          <Button type="button" disabled className="h-10">
            <Loader2 className="size-4 animate-spin" />
            {t(phase === "reading" ? "aadhaar.reading" : "aadhaar.starting")}
          </Button>
        ) : null}
        {phase === "scanning" ? (
          <Button
            type="button"
            variant="outline"
            className="h-10"
            onClick={() => {
              stop();
              setPhase("idle");
            }}
          >
            {t("aadhaar.stop")}
          </Button>
        ) : null}

        <label className="inline-flex">
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="sr-only"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void fromFile(file);
              event.target.value = "";
            }}
          />
          <span
            className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-full border
                       border-border bg-card px-4 text-sm font-medium transition-colors
                       hover:border-primary/40 hover:bg-accent"
          >
            <ImageUp className="size-4" />
            {t("aadhaar.photo")}
          </span>
        </label>
      </div>

      <p className="mt-4 flex items-start gap-2 border-t border-border pt-3 text-xs leading-relaxed text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-leaf" />
        {t("aadhaar.privacy")}
      </p>
    </div>
  );
}

/** Shown after a scan, so someone can see what was read and from which card. */
export function ScanResult({
  verified,
  last4,
}: {
  verified: boolean;
  last4: string;
}) {
  const { t } = useLanguage();
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      {verified ? (
        <ShieldCheck className="size-4 shrink-0 text-verified" />
      ) : (
        <Check className="size-4 shrink-0 text-leaf" />
      )}
      {verified ? t("aadhaar.verified") : t("aadhaar.readOnly")}
      {last4 ? ` · …${last4}` : ""}
    </p>
  );
}
