"use client";

import { usePathname } from "next/navigation";

/**
 * The chat is an app surface, not a document: it fills the viewport and pins its
 * composer to the bottom edge. A marketing footer underneath that turns the
 * whole thing into an awkward double-scroll, so it is dropped there.
 */
export function HideOnAppSurfaces({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/chat") return null;
  return <>{children}</>;
}
