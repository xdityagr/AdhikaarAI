import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";

import { ChatLauncher } from "@/components/chat-launcher";
import { HideOnAppSurfaces } from "@/components/chrome-slot";
import { LanguageProvider } from "@/components/language-provider";
import { LanguageSuggestion } from "@/components/language-suggestion";
import { LocationGate } from "@/components/location-gate";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { Splash } from "@/components/splash";
import { Toaster } from "@/components/ui/sonner";
import { dirFor } from "@/lib/i18n/config";
import { getLang, getT } from "@/lib/i18n/server";
import { getCatalogMeta } from "@/lib/api";
import "./globals.css";

/*
 * Fonts are served from our own origin rather than fetched from Google.
 * Two reasons, and the second is the real one: the build machine cannot always
 * reach fonts.gstatic.com, and neither can a user on a weak rural connection —
 * a page whose text is invisible until a third party responds is a page that
 * fails exactly the people this is built for.
 *
 * Only the two Latin faces are declared here. The nine Indic and Arabic faces
 * are @font-face rules in globals.css with a unicode-range apiece, so a reader
 * downloads the alphabet they are actually reading and none of the others.
 */
const inter = localFont({
  src: "./fonts/inter.woff2",
  variable: "--font-inter",
  display: "swap",
  weight: "400 700",
  fallback: ["system-ui", "Segoe UI", "sans-serif"],
});

/*
 * Hanken Grotesk sets every heading, and it sets them at 300. The lightness is
 * the point: at 60px a light grotesk reads as composed, where the same words at
 * 700 read as a pitch. It is only ever asked to carry Latin — see globals.css
 * for what the other scripts do instead.
 */
const hanken = localFont({
  src: "./fonts/hanken-grotesk.woff2",
  variable: "--font-hanken",
  display: "swap",
  weight: "300 700",
  fallback: ["system-ui", "Segoe UI", "sans-serif"],
});

/**
 * A function rather than a constant, because these two strings are the ones a
 * person sees before they see the site at all — the browser tab, and the
 * preview card when someone forwards the link on WhatsApp. They were English
 * for every reader of every language, which is the one place where a fully
 * translated interface still announced itself in English.
 *
 * Every other route already does this; the root layout was the one that did
 * not, and its description is the fallback all of them inherit.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getT();
  return {
    title: {
      default: t("site.title"),
      template: "%s · Yojna Setu",
    },
    description: t("site.description"),
  };
}

export const viewport: Viewport = {
  themeColor: "#fdfcfa",
  // The sky at the top of every page runs under the status bar on a phone.
  viewportFit: "cover",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const [lang, meta] = await Promise.all([getLang(), getCatalogMeta()]);
  const states = meta.states
    .map((s) => s.name)
    .filter((name) => name !== "All");
  // Urdu is right-to-left. Setting it here flips the whole layout —
  // padding, flex order, text alignment — because Tailwind's logical
  // properties follow the document direction.
  const dir = dirFor(lang);

  return (
    <html
      lang={lang}
      dir={dir}
      className={`${inter.variable} ${hanken.variable} h-full antialiased`}
    >
      <body className="sky-top flex min-h-full flex-col text-foreground">
        <LanguageProvider lang={lang}>
          <Splash />
          <SiteHeader />
          <main className="flex-1">{children}</main>
          <HideOnAppSurfaces>
            <SiteFooter />
          </HideOnAppSurfaces>
          <ChatLauncher />
          <LanguageSuggestion />
          <LocationGate states={states} />
          <Toaster position="top-center" />
        </LanguageProvider>
      </body>
    </html>
  );
}
