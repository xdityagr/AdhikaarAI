import { type Lang } from "@/lib/i18n/config";

/**
 * The phone door.
 *
 * WhatsApp reaches anyone with a smartphone. This reaches the people who do not
 * have one, which in this audience is not a rounding error — it is the whole
 * reason the channel exists (`docs/PRD-v3.md` §6.4). So the affordance has to
 * work for someone holding a feature phone, which means: a number, readable,
 * dialable, and honest about what happens when they ring it.
 *
 * Two things here are refusals rather than features, and both exist because the
 * alternative costs a person something real.
 */

/** Published, printed on posters, not a secret — hence NEXT_PUBLIC_. */
const RAW = process.env.NEXT_PUBLIC_HELPLINE_NUMBER || "";

/** Digits only: country code, no plus, no spaces. */
export const CALL_E164 = RAW.replace(/[^\d]/g, "");

export const CALL_CONFIGURED = CALL_E164.length >= 8;

/**
 * Whether the published number is Indian.
 *
 * REFUSAL ONE. The number provisioned today is `+1 571 364 0257`, because Vapi's
 * free numbers are US-national only. A caller in Bihar ringing it pays
 * international rates, and on many Indian prepaid plans ISD is barred by
 * default — so for a large share of the people this channel is for, the call
 * does not fail expensively, it simply never connects.
 *
 * A button that quietly bills a poor person for a call that may not complete is
 * worse than no button. So when this is false the door still opens, and it says
 * so before they dial.
 */
export const CALL_IS_INDIAN = CALL_E164.startsWith("91") && CALL_E164.length === 12;

/**
 * The languages the phone line actually answers in.
 *
 * REFUSAL TWO. The site reads in thirteen languages. The line speaks three,
 * because Vapi's only text-to-speech model with language *enforcement*
 * (ElevenLabs Flash v2.5) covers English, Hindi and Tamil and nothing else of
 * ours — see `docs/SPIKE-voice-vapi.md`.
 *
 * Offering "call us" to someone reading in Odia, and answering in English, is
 * the exact failure this product exists to prevent. So the door reads this and
 * tells them the truth, then points at WhatsApp — which does answer in all
 * thirteen.
 *
 * MUST MATCH `VAPI_ELEVENLABS_TTS` in `scripts/provision_voice.py`.
 * `tests/test_voice.py::TestTheCallDoor` reads both and fails when they differ,
 * because a list duplicated across two languages is a list that drifts.
 */
export const CALL_LANGUAGES: readonly Lang[] = ["en", "hi", "ta"];

export function callSpeaks(lang: Lang): boolean {
  return CALL_LANGUAGES.includes(lang);
}

/** Grouped the way the number is read aloud, per country code. */
export function callDisplayNumber(): string {
  if (!CALL_CONFIGURED) return "";
  const d = CALL_E164;
  if (d.startsWith("91") && d.length === 12) {
    return `+91 ${d.slice(2, 7)} ${d.slice(7)}`;
  }
  if (d.startsWith("1") && d.length === 11) {
    return `+1 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`;
  }
  return `+${d}`;
}

/**
 * `tel:` — which is the entire point.
 *
 * On the phone this is one tap to the dialler. On a laptop it usually does
 * nothing at all, which is why the sheet leads with a QR and the readable
 * number: scanning a `tel:` code opens the dialler on the phone you scanned
 * with, and the printed digits work on a phone with no camera worth using.
 */
export function callLink(): string {
  return `tel:+${CALL_E164}`;
}
