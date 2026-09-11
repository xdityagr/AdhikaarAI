"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * A voice message, the way WhatsApp does it.
 *
 * This replaces hold-to-talk, which did not work. Two reasons, and both were
 * fatal rather than fixable:
 *
 * - It ran on the browser's Web Speech API, which is Chrome-only. Firefox has
 *   none, most Android WebViews have none, and the failure is silent — the
 *   button simply did nothing, on exactly the cheap phones this is built for.
 * - Holding a button while speaking a whole sentence is genuinely awkward on a
 *   phone, and any slip of the finger ends the recording mid-word.
 *
 * So: tap to start, tap to send. The audio goes to our own endpoint and is
 * transcribed by the same engine that handles WhatsApp voice notes, which
 * means one behaviour to reason about instead of two — and Indian-language
 * accuracy that the browser never had.
 *
 * Typing Devanagari, Tamil or Odia on a phone keyboard is slow enough that
 * people give up and type romanised English, or give up entirely. For a
 * person who does not read comfortably in any script, this is not a
 * convenience, it is the only usable input.
 */

/** Long enough for a real question; past this we stop and send on our own. */
const MAX_SECONDS = 60;

/** Below this nobody said anything — usually a mis-tap. */
const MIN_MS = 400;

type Phase = "idle" | "recording" | "sending";

/** Whichever container this browser will actually produce. */
function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const type of [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4",
  ]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return undefined;
}

export function VoiceButton({
  onTranscript,
  onInterim,
  disabled,
  className,
}: {
  onTranscript: (text: string) => void;
  /** Progress the caller can show while this is happening. */
  onInterim?: (text: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  const { lang, t } = useLanguage();
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedRef = useRef(0);
  const cancelledRef = useRef(false);

  // Whatever happens, the microphone gets released. A page that leaves the
  // recording indicator on is a page nobody grants the permission to twice.
  const releaseMic = useCallback(() => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    recorderRef.current = null;
  }, []);

  useEffect(() => () => releaseMic(), [releaseMic]);

  const send = useCallback(
    async (blob: Blob, mimeType: string) => {
      setPhase("sending");
      onInterim?.(t("chat.voice.sending"));
      try {
        const form = new FormData();
        form.append("audio", blob, "voice.webm");
        // The interface language is a hint only — someone reading in English
        // may well speak Marathi, and the engine detects better than we guess.
        form.append("language", lang);

        const response = await fetch("/api/transcribe", {
          method: "POST",
          body: form,
        });
        if (!response.ok) throw new Error(String(response.status));
        const data = await response.json();

        if (data.ok && data.text?.trim()) {
          onInterim?.("");
          onTranscript(data.text.trim());
        } else {
          onInterim?.("");
          setError(t("chat.voice.unclear"));
        }
      } catch {
        onInterim?.("");
        setError(t("chat.voice.failed"));
      } finally {
        setPhase("idle");
        setSeconds(0);
      }
    },
    [lang, onInterim, onTranscript, t],
  );

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    recorder.stop();
  }, []);

  const start = useCallback(async () => {
    if (disabled || phase !== "idle") return;
    setError(null);
    cancelledRef.current = false;

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      // Denied, or no microphone. Either way it is not a failure to explain at
      // length — the person can type instead, and the box is right there.
      setError(t("chat.voice.noMic"));
      return;
    }

    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;
    chunksRef.current = [];
    startedRef.current = Date.now();

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstop = () => {
      const held = Date.now() - startedRef.current;
      const type = recorder.mimeType || mimeType || "audio/webm";
      const blob = new Blob(chunksRef.current, { type });
      releaseMic();

      if (cancelledRef.current || held < MIN_MS || blob.size === 0) {
        setPhase("idle");
        setSeconds(0);
        return;
      }
      void send(blob, type);
    };

    recorder.start();
    setPhase("recording");
    setSeconds(0);
  }, [disabled, phase, releaseMic, send, t]);

  // The running count, and the backstop that ends a recording someone forgot
  // to stop rather than uploading four minutes of room noise.
  useEffect(() => {
    if (phase !== "recording") return;
    const timer = window.setInterval(() => {
      setSeconds((value) => {
        if (value + 1 >= MAX_SECONDS) stop();
        return value + 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [phase, stop]);

  // Errors clear themselves; a stale "could not hear that" next to a working
  // microphone is worse than no message at all.
  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(null), 4000);
    return () => window.clearTimeout(timer);
  }, [error]);

  const recording = phase === "recording";
  const sending = phase === "sending";

  return (
    <div className="relative flex shrink-0 items-center gap-2">
      {recording ? (
        <span className="flex items-center gap-1.5 text-xs tabular-nums text-muted-foreground">
          <span className="size-2 animate-pulse rounded-full bg-destructive" />
          {String(Math.floor(seconds / 60)).padStart(1, "0")}:
          {String(seconds % 60).padStart(2, "0")}
        </span>
      ) : null}

      {error ? (
        <span
          role="status"
          className="absolute bottom-full end-0 mb-2 w-max max-w-[15rem] rounded-lg
                     border border-border bg-card px-2.5 py-1.5 text-xs text-muted-foreground
                     shadow-sm"
        >
          {error}
        </span>
      ) : null}

      <Button
        type="button"
        variant={recording ? "default" : "ghost"}
        size="icon"
        disabled={disabled || sending}
        aria-label={t(
          recording ? "chat.voice.stop"
          : sending ? "chat.voice.sending"
          : "chat.voice.record",
        )}
        aria-pressed={recording}
        onClick={() => (recording ? stop() : void start())}
        className={cn("size-10 shrink-0 rounded-full", className)}
      >
        {sending ? (
          <Loader2 className="size-4 animate-spin" />
        ) : recording ? (
          <Square className="size-3.5 fill-current" />
        ) : (
          <Mic className="size-4" />
        )}
      </Button>
    </div>
  );
}
