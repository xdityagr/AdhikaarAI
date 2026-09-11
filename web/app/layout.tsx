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
import { getLang } from "@/lib/i18n/server";
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

export const metadata: Metadata = {
  title: {
    default: "Adhikaar AI — find the schemes you actually qualify for",
    template: "%s · Adhikaar AI",
  },
  description:
    "Adhikaar AI finds the government schemes you qualify for, explains what they " +
    "cost in rupees, and shows you where to go to apply. Built for SC, ST, OBC " +
    "and other marginalised households.",
};

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
