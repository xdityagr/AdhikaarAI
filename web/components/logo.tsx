/**
 * The mark and the wordmark.
 *
 * सेतु is a bridge. The name says what this thing does rather than what it is
 * about — a scheme sits on one bank and the person entitled to it stands on
 * the other, and the product is the span between them. So the mark is an arch
 * bridge: two strokes, the green arch and the gold roadway it carries.
 *
 * The roadway overhangs the arch at both ends, and that overhang is doing the
 * work. Without it the same two strokes read as an archway, or a table. Drawn
 * at several sizes before this was settled; the versions with a separate sun
 * disc above read as a sunset over furniture, and a faint waterline under the
 * arch turned the whole thing into a boat.
 *
 * Gold is the roadway rather than a disc because the palette note is serious
 * that marigold is "emphasis that has earned it" — a hairline of it across the
 * top is emphasis, a filled circle competing with the arch is not.
 *
 * Drawn rather than imported so it stays crisp on a cheap screen, and kept to
 * two strokes so it survives being 20px on a dark header.
 *
 * What it is deliberately not: a chariot wheel, which at this size is
 * indistinguishable from the Ashoka Chakra — this product must never look like
 * it is claiming to be the government itself; and a seal or a tick, which
 * would imply it approves things. It approves nothing, and says so in the
 * footer in thirteen languages.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className ?? "size-7"}
      aria-hidden="true"
      fill="none"
    >
      {/* the arch that carries it */}
      <path
        d="M5 21.5a11 11 0 0 1 22 0"
        stroke="var(--primary)"
        strokeWidth="2.8"
        strokeLinecap="round"
      />
      {/* the deck, drawn after so it closes the crown */}
      <path
        d="M2 10.5h28"
        stroke="var(--gold)"
        strokeWidth="2.9"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * The header lockup: the name, then the Sanskrit it is.
 *
 * Set light and tight, like every other heading on the site. The Devanagari is
 * not decoration — योजना सेतु is two words this audience already owns, not a
 * coinage they have to be taught, and for most of them it is the half of the
 * lockup they can actually read.
 */
export function Logo({
  className,
  showGloss = true,
}: {
  className?: string;
  showGloss?: boolean;
}) {
  return (
    <span className={`flex items-baseline gap-2.5 ${className ?? ""}`}>
      <span className="font-display text-[1.3125rem] font-medium tracking-[-0.03em] text-foreground">
        Yojna Setu
      </span>
      {showGloss ? (
        <span className="hidden text-[0.8125rem] text-faint sm:inline">
          योजना सेतु
        </span>
      ) : null}
    </span>
  );
}
