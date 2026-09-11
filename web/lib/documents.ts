/**
 * Splitting a scheme's document list the same way the backend does.
 *
 * The corpus stores `documents_md` as markdown prose — myScheme writes ordered
 * lists whose numbers are all "1.", and some departments write a paragraph
 * instead of a list at all. `src/application.py:parse_list` turns that into one
 * requirement per line, and this has to agree with it character for character:
 * the checklist's ticks are keyed on the exact requirement text, so a split that
 * drifted would silently stop matching everything somebody had already ticked.
 *
 * Kept here rather than copied into each page for that reason. Two copies of a
 * parser that must not disagree is two chances to make them disagree.
 */
const BULLET = /^\s*(?:[-*•]|\d+[.)])\s+/;

export function splitRequirements(markdown?: string | null): string[] {
  if (!markdown) return [];
  const out: string[] = [];
  for (const raw of markdown.split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    const text = line
      .replace(BULLET, "")                              // marker, not trusted
      .replace(/\*\*(.+?)\*\*/g, "$1")                  // bold
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")   // links
      .replace(/^#{1,6}\s*/, "")                        // headings
      .trim();
    // Two characters or fewer is punctuation left behind by a stripped marker,
    // never a document. Prose survives whole, as one requirement.
    if (text.length > 2) out.push(text);
    if (out.length >= 24) break;
  }
  return out;
}
