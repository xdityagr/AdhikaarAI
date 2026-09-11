import Link from "next/link";
import type { ComponentProps } from "react";

import { Button } from "@/components/ui/button";

/**
 * A link that looks like a button.
 *
 * Base UI's Button assumes it renders a native `<button>`. Point its `render`
 * prop at an anchor without saying so and it warns, and the element loses the
 * button semantics assistive technology relies on. `nativeButton={false}` is
 * the correction, and it is set here once rather than at every call site,
 * because the one time it gets forgotten is the time nobody notices.
 *
 * Pass `external` for links off our own site: they open in a new tab and carry
 * the rel that stops the opened page from reaching back into ours.
 */
export function ButtonLink({
  href,
  external = false,
  children,
  ...props
}: Omit<ComponentProps<typeof Button>, "render" | "nativeButton"> & {
  href: string;
  external?: boolean;
}) {
  return (
    <Button
      {...props}
      nativeButton={false}
      render={
        external ? (
          <a href={href} target="_blank" rel="noopener noreferrer" />
        ) : (
          <Link href={href} />
        )
      }
    >
      {children}
    </Button>
  );
}
