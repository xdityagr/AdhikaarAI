import { ApplicationTracker } from "@/components/application-tracker";
import { PageHeader } from "@/components/page-header";
import { getT } from "@/lib/i18n/server";

export const metadata = {
  title: "Track an application",
  description:
    "Follow your application through sanction and disbursement, and escalate " +
    "with a drafted grievance when it stalls.",
};

export default async function TrackPage() {
  const t = await getT();

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("nav.track")}
        title={t("track.h1")}
        lede={t("track.lede")}
      />

      <div className="mx-auto max-w-3xl px-5 sm:px-6">
        {/* Saying this plainly is the honest thing and, as it happens, the
            useful one. Every "live tracker" for these schemes is either
            scraping a portal that blocks bots or quietly making it up. */}
        <aside className="border-s-2 border-gold ps-5 sm:ps-6">
          <h2 className="text-[1.0625rem] font-medium text-gold-ink">
            {t("track.limits.title")}
          </h2>
          <p className="mt-2 text-[0.9375rem] leading-relaxed text-muted-foreground">
            {t("track.limits.body")}
          </p>
        </aside>

        <ApplicationTracker className="mt-14" />
      </div>
    </div>
  );
}
