import Link from "next/link";

import { Logo } from "@/components/logo";
import { getT } from "@/lib/i18n/server";
import { en, type StringKey } from "@/lib/i18n/keys";

/** Official names — myScheme, NSFDC, PFMS — are never translated. */
function isKey(value: string): value is StringKey {
  return value in en;
}

const COLUMNS = [
  {
    title: "footer.find",
    links: [
      { href: "/check", label: "nav.check" },
      { href: "/schemes", label: "nav.schemes" },
      { href: "/credit", label: "nav.credit" },
    ],
  },
  {
    title: "footer.act",
    links: [
      { href: "/partners", label: "nav.partners" },
      { href: "/track", label: "nav.track" },
      { href: "/chat", label: "nav.chat" },
    ],
  },
  {
    title: "footer.sources",
    links: [
      { href: "https://www.myscheme.gov.in", label: "myScheme (Govt. of India)" },
      { href: "https://nsfdc.nic.in", label: "NSFDC" },
      { href: "https://pfms.nic.in", label: "PFMS — payment status" },
    ],
  },
];

/**
 * Quiet by design. A footer on this site is not a second navigation — the
 * disclaimer is the part that matters, and it says plainly that we are not the
 * government and cannot approve anything. Burying that under a wall of links
 * would be the dishonest way to include it.
 */
export async function SiteFooter() {
  const t = await getT();

  return (
    <footer className="border-t border-border">
      <div className="mx-auto max-w-6xl px-5 py-16 sm:px-6">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="max-w-xs">
            <Logo />
            <p className="mt-5 text-[0.875rem] leading-relaxed text-muted-foreground">
              {t("footer.tagline")}
            </p>
          </div>

          {COLUMNS.map((column) => (
            <div key={column.title}>
              <h2 className="meta">
                {isKey(column.title) ? t(column.title) : column.title}
              </h2>
              <ul className="mt-4 space-y-3">
                {column.links.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className="text-[0.9375rem] text-muted-foreground transition-colors hover:text-foreground"
                    >
                      {isKey(link.label) ? t(link.label) : link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <p className="mt-14 max-w-[80ch] border-t border-border pt-7 text-[0.8125rem] leading-relaxed text-faint">
          {t("footer.disclaimer")}
        </p>
      </div>
    </footer>
  );
}
