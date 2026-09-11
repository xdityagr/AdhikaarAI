import Link from "next/link";
import { Compass } from "lucide-react";

import { ButtonLink } from "@/components/ui/button-link";
import { getT } from "@/lib/i18n/server";

export const metadata = { title: "Page not found" };

/**
 * Without this file Next serves its own 404, which paints itself black on a
 * machine set to dark mode — jarring against a deliberately light product, and
 * it drops the header, so a lost visitor has nothing to click.
 */
export default async function NotFound() {
  const t = await getT();

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-24 text-center sm:py-32">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-secondary text-primary">
        <Compass className="size-7" />
      </span>

      <h1 className="mt-6 font-display text-3xl font-bold sm:text-4xl">
        {t("notfound.h1")}
      </h1>
      <p className="mt-3 text-muted-foreground">
        {t("notfound.body")}
      </p>

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <ButtonLink href="/check" size="lg" className="h-11 px-6">
          {t("nav.cta")}
        </ButtonLink>
        <ButtonLink
          href="/schemes"
          size="lg"
          variant="outline"
          className="h-11 bg-card px-6"
        >
          {t("nav.schemes")}
        </ButtonLink>
      </div>

      <p className="mt-8 text-sm text-muted-foreground">
        Or go back to the{" "}
        <Link href="/" className="font-medium text-primary underline underline-offset-4">
          {t("notfound.home")}
        </Link>
        .
      </p>
    </div>
  );
}
