import { CreditForm } from "@/components/credit-form";
import { PageHeader } from "@/components/page-header";
import { getT } from "@/lib/i18n/server";

export const metadata = {
  title: "NSFDC loans",
  description:
    "Work out which NSFDC credit scheme fits, what it costs in rupees against " +
    "a moneylender, and which office near you can actually disburse it.",
};

export default async function CreditPage() {
  const t = await getT();

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("nav.credit")}
        title={t("credit.h1")}
        lede={t("credit.lede")}
      />

      <CreditForm className="mx-auto max-w-6xl px-5 sm:px-6" />
    </div>
  );
}
