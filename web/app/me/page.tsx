import { PageHeader } from "@/components/page-header";
import { ProfileSheet } from "@/components/profile-sheet";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata() {
  const t = await getT();
  return { title: t("profile.title"), description: t("profile.lede") };
}

/**
 * "About you", on its own page.
 *
 * Answered once and then never asked again: it feeds the assistant, the
 * eligibility check and every application form. Scanning the QR on an Aadhaar
 * card fills most of it in three taps; a photograph catches the worn cards a
 * live camera cannot hold focus on; and typing works for someone with no card
 * in reach.
 *
 * The sheet itself is a client component because everything it touches —
 * `localStorage`, the camera — exists only in the browser. The server renders
 * the frame around it and knows none of the contents, which is the point.
 */
export default async function ProfilePage() {
  const t = await getT();

  return (
    <div className="pb-24">
      <PageHeader
        eyebrow={t("nav.check")}
        title={t("profile.title")}
        lede={t("profile.lede")}
      />
      <div className="mx-auto max-w-3xl px-5 sm:px-6">
        <ProfileSheet showHeading={false} />
      </div>
    </div>
  );
}
