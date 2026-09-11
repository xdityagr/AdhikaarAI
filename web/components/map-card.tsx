import Image from "next/image";

import { cn } from "@/lib/utils";

/**
 * The rendered map of the offices that can pay you.
 *
 * The engine draws these at 640×480 from OpenStreetMap tiles, so that is the
 * ratio declared here. It was previously declared as 640×400 in the chat and
 * 720×450 in the loan results — neither matches, and the browser was reserving
 * a box of the wrong shape and stretching the tiles into it. Roads came out
 * squashed, which on a map is not a cosmetic problem: it is the one image on
 * the site a person might try to navigate by.
 *
 * The caption is not decoration either. The pins are numbered to match the
 * list of offices beside them, and a numbered pin with nothing explaining the
 * numbering is a puzzle rather than a direction.
 */
export function MapCard({
  url,
  alt,
  caption,
  className,
}: {
  url: string;
  alt: string;
  caption?: string;
  className?: string;
}) {
  if (!url) return null;

  return (
    <figure
      className={cn(
        "overflow-hidden rounded-2xl border border-border bg-card",
        className,
      )}
    >
      <Image
        src={url}
        alt={alt}
        width={640}
        height={480}
        // Rendered on demand by the engine and already sized for this slot;
        // putting it through the image optimiser would only re-encode it.
        unoptimized
        className="h-auto w-full"
      />
      <figcaption className="border-t border-border px-4 py-3 text-[0.8125rem] leading-relaxed text-muted-foreground">
        {caption}
        {/*
          Not optional and not decoration. These tiles are OpenStreetMap's,
          and the ODbL they are published under requires the credit to travel
          with them. It is deliberately not a translated string: it is a
          licence notice, and it says the same thing in every language.
        */}
        <span className="mt-1.5 block text-[0.75rem] text-faint">
          Map data ©{" "}
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2 hover:text-muted-foreground"
          >
            OpenStreetMap
          </a>{" "}
          contributors
        </span>
      </figcaption>
    </figure>
  );
}
