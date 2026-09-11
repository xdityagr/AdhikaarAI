import { ArrowRight, ExternalLink } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { getT } from "@/lib/i18n/server";
import { ButtonLink } from "@/components/ui/button-link";

export async function generateMetadata() {
  const t = await getT();
  return { title: t("partners.h1"), description: t("partners.lede") };
}

interface Partner {
  partner_id: string;
  name: string;
  agency_type: string;
  partner_type: string;
  state: string;
  district: string | null;
  latitude: number | null;
  longitude: number | null;
  cumulative_utilization: number | null;
  deployable_headroom_lakh: number | null;
  net_npa_percentage: number | null;
  utilisation_confidence: string | null;
  note: string | null;
}

const API = process.env.YOJNASETU_API_ORIGIN ?? "http://127.0.0.1:8001";

async function getPartners(): Promise<Partner[]> {
  try {
    const response = await fetch(`${API}/api/partners`, {
      next: { revalidate: 900 },
    });
    if (!response.ok) return [];
    const data = await response.json();
    return data.partners ?? [];
  } catch {
    return [];
  }
}

export default async function PartnersPage() {
  const [partners, t] = await Promise.all([getPartners(), getT()]);

  const byState = new Map<string, Partner[]>();
  for (const partner of partners) {
    const list = byState.get(partner.state) ?? [];
    list.push(partner);
    byState.set(partner.state, list);
  }
  const states = [...byState.keys()].sort();

  return (
    <>
      <PageHeader
        eyebrow={t("nav.partners")}
        title={t("partners.h1")}
        lede={t("partners.lede")}
      />

      <div className="mx-auto max-w-5xl px-5 pb-24 sm:px-6">
        {/* The part nobody else shows. An agency sitting on undeployed funds
            can say yes today; one that has spent its allocation cannot, however
            eligible you are. A wasted journey costs a day's wages and a fare. */}
        <aside className="border-s-2 border-gold ps-5 sm:ps-6">
          <h2 className="text-[1.0625rem] font-medium text-gold-ink">
            {t("partners.why.title")}
          </h2>
          <p className="mt-2 max-w-[68ch] text-[0.9375rem] leading-relaxed text-muted-foreground">
            {t("partners.why.body")}
          </p>
        </aside>

        {partners.length === 0 ? (
          <p className="mt-14 border-s-2 border-clay ps-5 text-[0.9375rem] leading-relaxed text-clay sm:ps-6">
            {t("partners.offline")}
          </p>
        ) : (
          <div className="mt-16 space-y-14">
            {states.map((state) => (
              <section key={state}>
                <h2 className="text-[1.25rem] font-normal">{state}</h2>
                <ul className="mt-5 border-t border-border">
                  {byState.get(state)!.map((partner) => (
                    <PartnerRow
                      key={partner.partner_id}
                      partner={partner}
                      deployed={t("partners.deployed")}
                      official={t("partners.official")}
                      mapLabel={t("partners.map")}
                    />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}

        <section className="mt-24 border-t border-border pt-14 text-center">
          <h2 className="mx-auto max-w-[24ch] text-balance text-[1.5rem] sm:text-[1.875rem]">
            {t("partners.cta.title")}
          </h2>
          <p className="mx-auto mt-4 max-w-[56ch] text-[1.0625rem] leading-relaxed text-muted-foreground">
            {t("partners.cta.body")}
          </p>
          <div className="mt-8 flex flex-col items-stretch justify-center gap-3 sm:flex-row">
            <ButtonLink href="/credit" size="pill">
              {t("credit.submit")}
              <ArrowRight className="size-4" />
            </ButtonLink>
            <ButtonLink href="/check" variant="outline" size="pill" className="bg-card">
              {t("nav.cta")}
            </ButtonLink>
          </div>
        </section>
      </div>
    </>
  );
}

/**
 * One agency, as a ruled row.
 *
 * Rows rather than cards because the useful act here is comparing agencies
 * within a state — which of these has money — and figures set in a column are
 * comparable in a way that figures scattered across a grid of boxes are not.
 */
function PartnerRow({
  partner,
  deployed,
  official,
  mapLabel,
}: {
  partner: Partner;
  deployed: string;
  official: string;
  mapLabel: string;
}) {
  const utilisation = partner.cumulative_utilization;
  const percent = utilisation !== null ? Math.round(utilisation * 100) : null;

  // Below 100% means undeployed funds remain. The reading is deliberately this
  // way round: the agency that has deployed everything is the constrained one.
  const tone =
    percent === null
      ? "bg-muted text-muted-foreground"
      : percent < 90
        ? "bg-verified-soft text-verified"
        : percent < 100
          ? "bg-gold-soft text-gold-ink"
          : "bg-clay-soft text-clay";

  return (
    <li className="border-b border-border py-6">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-[1.0625rem] font-medium leading-snug">
            {partner.name}
          </h3>
          <p className="mt-1 text-[0.875rem] text-muted-foreground">
            {partner.district ? `${partner.district} · ` : ""}
            {partner.agency_type}
          </p>
        </div>
        {percent !== null ? (
          <span
            className={`tnum shrink-0 rounded-full px-3 py-1 text-[0.8125rem] font-medium ${tone}`}
          >
            {percent}% {deployed}
          </span>
        ) : null}
      </div>

      {partner.note ? (
        <p className="mt-3 max-w-[70ch] text-[0.9375rem] leading-relaxed text-muted-foreground">
          {partner.note}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-[0.8125rem] text-faint">
        {partner.utilisation_confidence ? (
          <span>
            {partner.utilisation_confidence === "OFFICIAL"
              ? official
              : `${partner.utilisation_confidence.toLowerCase()}`}
          </span>
        ) : null}
        {partner.net_npa_percentage !== null ? (
          <span className="tnum">Net NPA {partner.net_npa_percentage}%</span>
        ) : null}
        {partner.latitude && partner.longitude ? (
          <a
            href={`https://www.openstreetmap.org/?mlat=${partner.latitude}&mlon=${partner.longitude}#map=13/${partner.latitude}/${partner.longitude}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-leaf underline-offset-4 hover:underline"
          >
            {mapLabel}
            <ExternalLink className="size-3" />
          </a>
        ) : null}
      </div>
    </li>
  );
}
