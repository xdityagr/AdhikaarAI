import { PageHeader } from "@/components/page-header";
import { OperatorPanel } from "@/components/operator-panel";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata() {
  const t = await getT();
  return {
    title: t("operator.h1"),
    description: t("operator.lede"),
    // Not a page for search engines. It is a staff tool over other people's
    // applications, and the only way in is an account an admin created.
    robots: { index: false, follow: false },
  };
}

/**
 * The counter, from the operator's side.
 *
 * Deliberately absent from the navigation. The header and footer are the
 * citizen's product, and an entry there saying "operator panel" would be an
 * invitation to a door that only staff have a key to — clutter for everybody
 * else, and a hint of a second system for somebody who is already unsure
 * whether this site is official.
 *
 * The people who need it are told the address.
 */
export default async function OperatorPage() {
  const t = await getT();

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("operator.eyebrow")}
        title={t("operator.h1")}
        lede={t("operator.lede")}
      />
      <div className="mx-auto max-w-4xl px-5 sm:px-6">
        <OperatorPanel />
      </div>
    </div>
  );
}
