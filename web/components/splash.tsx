import { LogoMark } from "@/components/logo";

/**
 * The first second.
 *
 * No JavaScript, deliberately. The overlay is in the server-rendered HTML so
 * it is part of the first paint — a splash that arrives after the page it is
 * meant to cover is worse than no splash — and a CSS animation takes it away
 * again. Nothing to hydrate, nothing to mismatch.
 *
 * It does not need to remember anything either: this lives in the root layout,
 * and a layout is not re-rendered on client-side navigation. So it plays once
 * when the site is opened and never again while someone moves around it.
 *
 * `pointer-events: none` is set for the whole life of the element rather than
 * at the end of the animation. If anything ever goes wrong with the animation,
 * the failure is an invisible div — not an invisible div that has swallowed
 * every click on the site.
 */
export function Splash() {
  return (
    <div className="adh-splash" aria-hidden="true">
      <div className="adh-splash-inner">
        <LogoMark className="size-11" />
        <span className="adh-splash-word">Adhikaar AI</span>
        <span className="adh-splash-gloss">आपका अधिकार</span>
      </div>
    </div>
  );
}
