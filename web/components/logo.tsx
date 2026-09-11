/**
 * The mark and the wordmark.
 *
 * "Adhikaar" is a right — the thing that is already yours before anyone
 * approves it. So the mark is a doorway with the sunrise standing in it: the
 * product's own description of itself is a front door ("the entire
 * social-justice credit channel has no digital front door"), and a door is
 * something you walk through yourself. The gold disc is carried over from the
 * sunrise the pages are washed in, so the site's visual language survives the
 * rename.
 *
 * Drawn rather than imported so it stays crisp on a cheap screen, and built
 * from two shapes so it survives being 20px.
 *
 * Two shapes it is deliberately NOT: a chariot wheel, which at this size is
 * indistinguishable from the Ashoka Chakra — this product must never look like
 * it is claiming to be the government itself; and a seal or a tick, which
 * would imply it approves things. It cannot approve anything, and says so in
 * thirteen languages in the footer.
 *
 * The arch is left open at the floor for the same reason: a threshold line
 * would close the door.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className ?? "size-7"}
      aria-hidden="true"
      fill="none"
    >
      <circle cx="16" cy="15.5" r="4.8" fill="var(--gold)" />
      <path
        d="M5.8 28V14.5a10.2 10.2 0 0 1 20.4 0V28"
        stroke="var(--primary)"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

/**
 * The header lockup: the name, then the Hindi word it is.
 *
 * Set light and tight, like every other heading on the site. The Devanagari
 * gloss is not decoration — अधिकार is the whole product in one word, it is not
 * a coinage but a word this audience already owns, and for most of them it is
 * the half of the lockup they can actually read.
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
        Adhikaar AI
      </span>
      {showGloss ? (
        <span className="hidden text-[0.8125rem] text-faint sm:inline">
          अधिकार
        </span>
      ) : null}
    </span>
  );
}
