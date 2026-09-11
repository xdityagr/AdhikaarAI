"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ElementType,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

/**
 * useLayoutEffect runs before the browser paints; useEffect runs after. We
 * need the former so the hidden state lands in the same frame as the first
 * paint — otherwise the section flashes in at full opacity and then jumps
 * back to hidden before animating. React warns about useLayoutEffect during
 * server rendering, hence the swap.
 */
const useIsomorphicLayoutEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

/** How long to wait for the observer to prove it is alive. */
const OBSERVER_GRACE_MS = 1200;

/**
 * A section that arrives as you reach it.
 *
 * Two failure modes are guarded, because the cost of getting this wrong is a
 * reader looking at a blank page — and this is a page about money someone is
 * owed, so a blank page is not a cosmetic bug.
 *
 * The first is no JavaScript. The server markup carries no hidden state at
 * all; the element is plain and visible. Only after mounting does it *arm*
 * itself, adding the attribute that hides it. Written the other way round —
 * hidden in the HTML, revealed by script — a blocked or failed bundle leaves
 * nothing on screen.
 *
 * The second is JavaScript that runs but an observer that never reports. A
 * backgrounded tab freezes rAF and IntersectionObserver delivery; some
 * WebViews throttle it harder still. An observer normally delivers its first
 * callback within a frame of observe(), so if nothing has arrived after a
 * moment, we assume it never will and show the content. Losing the animation
 * is not a real loss; losing the words is.
 */
export function Reveal({
  children,
  className,
  delay = 0,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  /** Milliseconds, for staggering two or three siblings against each other. */
  delay?: number;
  as?: ElementType;
}) {
  const ref = useRef<HTMLElement>(null);
  const [armed, setArmed] = useState(false);
  const [shown, setShown] = useState(false);

  useIsomorphicLayoutEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    // Nobody is looking at a hidden tab, so there is nothing to animate into
    // view — and arming here is what strands the content when the observer is
    // frozen along with the tab.
    if (document.visibilityState === "hidden") return;
    setArmed(true);
  }, []);

  useEffect(() => {
    if (!armed) return;
    const el = ref.current;
    if (!el) return;

    let heard = false;
    const observer = new IntersectionObserver(
      ([entry]) => {
        heard = true;
        if (!entry.isIntersecting) return;
        setShown(true);
        observer.disconnect();
      },
      // Fire a little before the edge, so the movement finishes as the section
      // settles into view rather than starting once it is already being read.
      { rootMargin: "0px 0px -12% 0px", threshold: 0.01 },
    );
    observer.observe(el);

    // The net. If the observer has not said anything at all by now it is not
    // working, so stop waiting on it.
    const failsafe = window.setTimeout(() => {
      if (!heard) setShown(true);
    }, OBSERVER_GRACE_MS);

    return () => {
      observer.disconnect();
      window.clearTimeout(failsafe);
    };
  }, [armed]);

  return (
    <Tag
      ref={ref}
      className={cn("motion-reveal", className)}
      data-armed={armed ? "1" : undefined}
      data-shown={shown ? "1" : undefined}
      style={delay && armed ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Tag>
  );
}
