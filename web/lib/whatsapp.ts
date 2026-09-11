import qrcode from "qrcode-generator";

/**
 * The WhatsApp door.
 *
 * For a large part of this audience WhatsApp is not a fallback — it is the
 * whole internet. So the number is configuration, not a constant: a demo runs
 * against a sandbox, a deployment runs against a business number, and neither
 * should need a code change.
 *
 * NEXT_PUBLIC_ is deliberate. This is a published helpline number printed on
 * posters; it is not a secret, and the QR has to be drawn in the browser.
 */
const FALLBACK_NUMBER = "+1 555 197 0478";
const RAW = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || FALLBACK_NUMBER;

/** Digits only, the form wa.me wants: country code, no plus, no spaces. */
export const WHATSAPP_E164 = RAW.replace(/[^\d]/g, "");

/** True when a real number has been configured, false in a bare checkout. */
export const WHATSAPP_CONFIGURED = WHATSAPP_E164.length >= 8;

/** Grouped the way the number is read aloud, per country code. */
export function whatsappDisplayNumber(): string {
  if (!WHATSAPP_CONFIGURED) return "Not configured yet";
  const d = WHATSAPP_E164;
  // +91 92892 00000
  if (d.startsWith("91") && d.length === 12) {
    return `+91 ${d.slice(2, 7)} ${d.slice(7)}`;
  }
  // +1 (555) 197-0478
  if (d.startsWith("1") && d.length === 11) {
    return `+1 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`;
  }
  return `+${d}`;
}

/**
 * The deep link, carrying the reader's opening message.
 *
 * The prefill matters more than it looks. It opts the sender into the 24-hour
 * service window, it gives the assistant something to act on instead of "hi",
 * and — because it is written in the language the reader is already using —
 * it tells the bot which language to answer in before a word is exchanged.
 *
 * Which is why the caller passes it rather than this file inventing one: only
 * the caller knows what language the page is currently in.
 */
export function whatsappLink(prefill: string): string {
  return `https://wa.me/${WHATSAPP_E164}?text=${encodeURIComponent(prefill)}`;
}

export interface QrMatrix {
  /** Side length in modules, including no quiet zone. */
  size: number;
  /** Row-major dark/light. */
  cells: boolean[][];
}

/**
 * A QR as a matrix, so the caller can draw it as SVG rather than a bitmap.
 *
 * Drawn rather than fetched from an image service: a QR is a URL, and posting
 * every reader's deep link to a third-party endpoint to get a picture back is
 * both a privacy leak and a dependency on a network this product cannot count
 * on. Error correction is M — enough to survive a cracked phone screen or a
 * photocopied poster without inflating the module count.
 */
export function qrMatrix(text: string): QrMatrix {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  const size = qr.getModuleCount();
  const cells: boolean[][] = [];
  for (let row = 0; row < size; row += 1) {
    const line: boolean[] = [];
    for (let col = 0; col < size; col += 1) line.push(qr.isDark(row, col));
    cells.push(line);
  }
  return { size, cells };
}
