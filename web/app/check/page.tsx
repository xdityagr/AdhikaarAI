import { CheckForm } from "@/components/check-form";
import { PageHeader } from "@/components/page-header";
import { getCatalogMeta, getScheme } from "@/lib/api";
import { getLang, getPlace, getT } from "@/lib/i18n/server";

export const metadata = {
  title: "Check what you qualify for",
  description:
    "Answer a few optional questions and see every government scheme you are " +
    "likely to be entitled to, with the reason for each match.",
};

export default async function CheckPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const wanted = Array.isArray(params.scheme) ? params.scheme[0] : params.scheme;
  // The language is read first because it decides what the scheme lookup
  // returns, not just how it is labelled — without it the page headline named
  // the scheme in English while the page they arrived from named it in Hindi,
  // which reads as two different schemes.
  const lang = await getLang();
  const [meta, t, place, focus] = await Promise.all([
    getCatalogMeta(), getT(), getPlace(),
    wanted ? getScheme(wanted, lang) : Promise.resolve(null),
  ]);

  return (
    <div className="pb-24">
      {/* Arriving from one scheme's page is a different question from
          "what am I entitled to" — it is "do I qualify for THIS", and the
          page should say so rather than silently widening the ask. */}
      <PageHeader
        eyebrow={focus ? focus.name.trim() : t("nav.check")}
        title={focus ? t("check.h1.scheme") : t("check.h1")}
        lede={focus ? t("check.lede.scheme") : t("check.lede")}
      />

      <CheckForm
        meta={meta}
        initialState={place}
        focusSlug={focus?.slug ?? null}
        focusName={focus?.name.trim() ?? null}
        className="mx-auto max-w-6xl px-5 sm:px-6"
      />
    </div>
  );
}
