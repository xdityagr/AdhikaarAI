"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, ImageUp, Loader2, X } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";

/**
 * Photographing a document, and saying honestly where the photograph goes.
 *
 * The camera handling here is lifted from `aadhaar-scan.tsx`, which had it
 * first and had it right — the environment-facing constraint, the canvas
 * downscale that stops a 4K sensor costing a full-resolution copy per frame,
 * the file input with `capture="environment"` as the rung that catches a worn
 * card in bad light. What is deliberately NOT lifted is the QR decode loop,
 * because a ration card has nothing to decode.
 *
 * AND THAT IS THE WHOLE DIFFERENCE, SO IT IS SAID OUT LOUD.
 *
 * The Aadhaar scanner can promise the photograph never leaves the phone: it
 * decodes a QR code locally and uploads a short string. There is no version of
 * this component that can make the same promise, because naming a document
 * means looking at it. So the image is uploaded — held in memory, classified,
 * dropped, never written to disk — and `privacyNote` renders that sentence
 * above the shutter, before anyone taps it, rather than in a policy nobody
 * opens. Inheriting the old promise here would have been a lie of omission.
 *
 * The component captures and hands back bytes. It does not know what a scheme
 * is, and it does not decide anything.
 */

type Phase = "idle" | "starting" | "live" | "working";

export function DocumentCapture({
  onCaptured,
  onClose,
  privacyNote,
  busy = false,
  label,
}: {
  onCaptured: (file: Blob) => void | Promise<void>;
  onClose: () => void;
  /** Shown before the shutter. Say where the image goes; do not be vague. */
  privacyNote: string;
  busy?: boolean;
  /** Required, and translated by the caller. It used to default to an English
   *  sentence, which is how a component nobody had touched in weeks would have
   *  started showing English again the first time a new caller forgot it. */
  label: string;
}) {
  const { t } = useLanguage();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  }, []);

  // Releasing the camera on unmount is not tidiness. A live stream left running
  // keeps the phone's camera light on after the panel is closed, which reads to
  // the person holding it as being watched.
  useEffect(() => stop, [stop]);

  const start = useCallback(async () => {
    setError(null);
    setPhase("starting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
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
      setPhase("live");
    } catch {
      setPhase("idle");
      setError(t("documents.capture.noCamera"));
    }
  }, []);

  /** Freeze the current frame and hand it over as a JPEG. */
  const shoot = useCallback(async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    // Downscaled for the same reason the scanner downscales: a full-resolution
    // frame from a modern sensor is several megabytes, and on the connection
    // this is built for that is the difference between two seconds and twenty.
    const scale = Math.min(1, 1600 / (video.videoWidth || 1));
    canvas.width = Math.round((video.videoWidth || 0) * scale);
    canvas.height = Math.round((video.videoHeight || 0) * scale);
    const context = canvas.getContext("2d");
    if (!context || !canvas.width) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

    setPhase("working");
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.85),
    );
    stop();
    if (blob) await onCaptured(blob);
    setPhase("idle");
  }, [onCaptured, stop]);

  /** A still from the gallery — steadier than a live frame, and the rung that
   *  works when the camera permission has been refused outright. */
  const fromFile = useCallback(
    async (file: File) => {
      setError(null);
      setPhase("working");
      try {
        const bitmap = await createImageBitmap(file);
        // A canvas of its own rather than the ref's: writing width/height
        // through a ref captured by a hook is a mutation of hook-owned state,
        // and this path does not need the shared one anyway.
        const canvas = document.createElement("canvas");
        const scale = Math.min(1, 1600 / bitmap.width);
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        const context = canvas.getContext("2d");
        if (!context) throw new Error("no canvas");
        context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise<Blob | null>((resolve) =>
          canvas.toBlob(resolve, "image/jpeg", 0.85),
        );
        if (blob) await onCaptured(blob);
      } catch {
        setError(t("documents.capture.unreadable"));
      }
      setPhase("idle");
    },
    [onCaptured],
  );

  const working = phase === "working" || busy;

  return (
    <div className="rounded-2xl border border-hairline bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-foreground">{label}</p>
        <button
          type="button"
          onClick={() => {
            stop();
            onClose();
          }}
          aria-label={t("documents.capture.close")}
          className="rounded-lg p-1 text-faint hover:text-foreground"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Before the shutter, not after, and not in a policy page. */}
      <p className="mt-2 text-[0.8125rem] leading-relaxed text-muted-foreground">
        {privacyNote}
      </p>

      <div className="relative mt-3 overflow-hidden rounded-xl bg-black/90">
        <video
          ref={videoRef}
          playsInline
          muted
          className={phase === "live" ? "block max-h-[46vh] w-full object-contain" : "hidden"}
        />
        {phase !== "live" ? (
          <div className="flex h-36 items-center justify-center text-white/50">
            {working ? <Loader2 className="size-5 animate-spin" /> : <Camera className="size-6" />}
          </div>
        ) : null}
      </div>
      <canvas ref={canvasRef} className="hidden" />

      {error ? (
        <p className="mt-2 text-[0.8125rem] text-clay">{error}</p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        {phase === "live" ? (
          <Button type="button" onClick={() => void shoot()} disabled={working}>
            {t("documents.capture.take")}
          </Button>
        ) : (
          <Button type="button" onClick={() => void start()} disabled={working}>
            <Camera className="size-4" /> {t("documents.capture.open")}
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={working}
          onClick={() => fileRef.current?.click()}
        >
          <ImageUp className="size-4" /> {t("documents.capture.choose")}
        </Button>
      </div>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Reset so picking the same file twice still fires a change.
          event.target.value = "";
          if (file) void fromFile(file);
        }}
      />
    </div>
  );
}
