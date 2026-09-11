import type { ReactNode } from "react";

/**
 * A short fade on every route change.
 *
 * This is a template rather than a layout because a template re-mounts on each
 * navigation and a layout does not — the remount is the whole mechanism.
 *
 * 260ms and opacity only. Sliding pages horizontally would imply a spatial
 * relationship between eligibility, schemes and offices that does not exist,
 * and would cost a repaint of the whole viewport on a slow device.
 */
export default function Template({ children }: { children: ReactNode }) {
  return <div className="motion-fade-in">{children}</div>;
}
