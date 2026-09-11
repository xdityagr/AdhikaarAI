import { PageHeader } from "@/components/page-header";
import { HouseholdView } from "@/components/household-view";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata() {
  const t = await getT();
  return { title: t("household.h1"), description: t("household.lede") };
}

/**
 * The house, not the person.
 *
 * `profile.ts` argues against accounts on the grounds that people share
 * phones. That is the same observation this page is built on: the phone is
 * shared because the household is the unit, and the person holding it is
 * usually looking on behalf of a grandmother, a daughter and a husband whose
 * entitlements have nothing in common.
 *
 * Client component, for the same reason the profile sheet is one — the roster
 * lives in localStorage and the server is never told who lives here.
 */
export default async function HouseholdPage() {
  const t = await getT();

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("nav.household")}
        title={t("household.h1")}
        lede={t("household.lede")}
      />
      <div className="mx-auto max-w-4xl px-5 sm:px-6">
        <HouseholdView />
        <p className="mt-10 border-t border-border pt-6 text-sm text-muted-foreground">
          {t("household.privacy")}
        </p>
      </div>
    </div>
  );
}
