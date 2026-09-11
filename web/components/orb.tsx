import { cn } from "@/lib/utils";

/**
 * The assistant, as a mark.
 *
 * The same sunrise the pages are washed in, compressed into a disc. It turns
 * slowly while a question is being worked on and is perfectly still the rest
 * of the time — which is what makes the movement read as thinking rather than
 * as decoration. If everything on the site moved, this would mean nothing.
 *
 * Lives here rather than inside the chat panel because it is the assistant's
 * face everywhere it is offered: the rail, the conversation, the launcher, and
 * the invitation at the foot of a scheme page. One mark, one file.
 */
export function Orb({
  busy = false,
  className,
}: {
  busy?: boolean;
  className?: string;
}) {
  return (
    <span
      aria-hidden
      data-busy={busy}
      className={cn("adh-orb block shrink-0", className ?? "size-7")}
    />
  );
}
