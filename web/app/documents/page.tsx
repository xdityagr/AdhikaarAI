import Link from "next/link";

import { AadhaarPanel, DocumentReadiness } from "@/components/document-readiness";
import { PageHeader } from "@/components/page-header";
import { getScheme } from "@/lib/api";
import { splitRequirements } from "@/lib/documents";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata() {
  const t = await getT();
  return {
    title: t("documents.pageTitle"),
    description: t("documents.pageLede"),
  };
}

/**
 * Papers, in one place.
 *
 * Two things that were previously scattered, put where someone gathering
 * documents is actually looking:
 *
 * - The Aadhaar QR scanner, which used to be reachable only from inside the
 *   profile sheet on `/me`. The fastest way to fill eleven fields was hidden
 *   behind the page you would only visit once they were already filled.
 * - The readiness check for a scheme's published document list — the answer to
 *   "have I got everything?", which is the question that decides whether a trip
 *   to an office is wasted.
 *
 * `?scheme=<slug>` renders that scheme's checklist. Without it the page is
 * still useful on its own, because the Aadhaar panel does not need a scheme.
 */
export default async function DocumentsPage({
  searchParams,
}: {
  searchParams: Promise<{ scheme?: string }>;
}) {
  const t = await getT();
  const { scheme: slug } = await searchParams;
  const scheme = slug ? await getScheme(slug) : null;

  // The corpus writes the document list as markdown prose, so the bullets are
  // split here the same way `src/application.py` splits them — one requirement
  // per line, markers stripped, prose surviving as a single item.
  const requirements = splitRequirements(scheme?.documents_md);

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("nav.documents")}
        title={t("documents.pageTitle")}
        lede={t("documents.pageLede")}
      />

      <div className="mx-auto grid max-w-3xl gap-5 px-5 sm:px-6">
        {scheme && requirements.length ? (
          <DocumentReadiness slug={String(slug)} requirements={requirements} />
        ) : (
          <section className="rounded-2xl border border-hairline bg-card p-5">
            <h2 className="font-display text-lg font-medium">
              {t("documents.title")}
            </h2>
            <p className="mt-1 text-[0.8125rem] leading-relaxed text-muted-foreground">
              {t("documents.pickScheme")}
            </p>
            <Link
              href="/schemes"
              className="mt-3 inline-block text-[0.8125rem] font-medium text-leaf underline underline-offset-4"
            >
              {t("nav.schemes")}
            </Link>
          </section>
        )}

        <AadhaarPanel />
      </div>
    </div>
  );
}

