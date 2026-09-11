/**
 * The flourish that sits above a page's eyebrow.
 *
 * It is the only ornament on the site, and it is doing a specific job: saying
 * "Indian" without reaching for a flag, a chakra or a lotus — none of which
 * this product is entitled to use, because none of them are ours to imply.
 * A drawn line ending in two opposed curls is a shape that appears on printed
 * Indian forms, invitations and municipal notices, and it belongs to nobody.
 */
export function Ornament({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 132 20"
      className={className ?? "mx-auto h-5 w-40"}
      fill="none"
      stroke="var(--gold)"
      strokeWidth="1"
      aria-hidden="true"
    >
      <path d="M2 14h34" strokeLinecap="round" />
      <path d="M96 14h34" strokeLinecap="round" />
      <path d="M44 14c0-5 4-8 7-6s2 7-3 8-9-3-9-7 5-7 9-5" />
      <path d="M88 14c0-5-4-8-7-6s-2 7 3 8 9-3 9-7-5-7-9-5" />
      <circle cx="66" cy="11" r="2.4" />
    </svg>
  );
}
