import type { ReactNode } from "react";

import { Ornament } from "@/components/ornament";
import { cn } from "@/lib/utils";

/**
 * How every page that isn't the front page opens.
 *
 * Centred, generous, and always the same three parts: an eyebrow saying where
 * you are, a light heading, and one sentence of what this page will do for
 * you. Consistency here is not tidiness — someone moving between eligibility,
 * schemes and offices should never have to work out where the title went.
 *
 * The ornament is off by default. It belongs to the front door; repeating it
 * on every screen would turn a signature into wallpaper.
 */
export function PageHeader({
  eyebrow,
  title,
  lede,
  children,
  ornament = false,
  align = "center",
  className,
}: {
  eyebrow?: string;
  title: string;
  lede?: string;
  children?: ReactNode;
  ornament?: boolean;
  align?: "center" | "start";
  className?: string;
}) {
  const centred = align === "center";

  return (
    <header
      className={cn(
        "mx-auto max-w-6xl px-5 pt-14 pb-10 sm:px-6 sm:pt-20 sm:pb-12",
        centred && "text-center",
        "motion-stagger",
        className,
      )}
    >
      {ornament ? <Ornament className="mx-auto h-6 w-44 opacity-75" /> : null}

      {eyebrow ? (
        <p className={cn("text-sm font-medium text-leaf", ornament && "mt-6")}>
          {eyebrow}
        </p>
      ) : null}

      <h1
        className={cn(
          "mt-4 text-[2rem] sm:text-[2.75rem]",
          centred ? "mx-auto max-w-[22ch] text-balance" : "max-w-[22ch]",
        )}
      >
        {title}
      </h1>

      {lede ? (
        <p
          className={cn(
            "mt-5 text-[1.0625rem] leading-relaxed text-muted-foreground",
            centred ? "mx-auto max-w-[58ch]" : "max-w-[58ch]",
          )}
        >
          {lede}
        </p>
      ) : null}

      {children ? <div className="mt-8">{children}</div> : null}
    </header>
  );
}
