"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Menu, X } from "lucide-react";

import { useLanguage } from "@/components/language-provider";
import { LanguageSwitcher } from "@/components/language-switcher";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { ButtonLink } from "@/components/ui/button-link";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/check", key: "nav.check" },
  { href: "/schemes", key: "nav.schemes" },
  { href: "/credit", key: "nav.credit" },
  { href: "/partners", key: "nav.partners" },
  { href: "/track", key: "nav.track" },
  // Answered once and reused everywhere — the assistant, the eligibility
  // check and every application form read from it, so it needs to be
  // reachable rather than something you find by accident.
  { href: "/me", key: "nav.me" },
  // The unit people actually search on. It sits next to "About you" because
  // it is the same question asked of everyone else in the house.
  { href: "/household", key: "nav.household" },
  { href: "/chat", key: "nav.chat" },
] as const;

/**
 * Brand on the left, the sections in the middle, one action on the right.
 *
 * The middle group is a flex child rather than an absolutely positioned one.
 * Absolute centring looked right in English and collided with the button in
 * Tamil, where every label is half again as long — and an overlap is a worse
 * failure than a nav that sits a few pixels off centre.
 *
 * The bar is transparent at the top of the page so the sunrise runs under it,
 * and only takes a background once you have scrolled past it.
 */
export function SiteHeader() {
  const { t } = useLanguage();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // A menu left open while the page changes underneath is a small betrayal.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-[background-color,border-color,backdrop-filter] duration-300",
        scrolled || open
          ? "border-b border-border bg-paper/80 backdrop-blur-md"
          : "border-b border-transparent",
      )}
    >
      <div className="mx-auto flex h-16 max-w-[84rem] items-center gap-5 px-4 sm:px-6">
        <Link
          href="/"
          className="shrink-0 rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/40"
          aria-label="Yojna Setu"
        >
          <Logo />
        </Link>

        <nav
          data-site-nav
          className="hidden min-w-0 flex-1 items-center justify-center gap-0.5 whitespace-nowrap xl:flex"
          aria-label={t("nav.primary")}
        >
          {NAV.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative rounded-full px-2.5 py-2 transition-colors duration-200",
                  active
                    ? "text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {t(item.key)}
                {active ? (
                  <span
                    aria-hidden
                    className="absolute inset-x-2.5 -bottom-0.5 h-px origin-center scale-x-100 bg-leaf/60 motion-fade-in"
                  />
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="ms-auto flex shrink-0 items-center gap-1">
          <LanguageSwitcher />
          <ButtonLink
            href="/check"
            size="pill-sm"
            className="hidden font-medium sm:inline-flex"
          >
            {t("nav.cta")}
          </ButtonLink>
          <Button
            data-site-menu
            variant="ghost"
            size="pill-icon"
            className="size-9 xl:hidden"
            aria-label={open ? t("nav.menu.close") : t("nav.menu.open")}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? <X className="size-5" /> : <Menu className="size-5" />}
          </Button>
        </div>
      </div>

      {open ? (
        <nav
          className="mx-auto max-w-[84rem] border-t border-border bg-paper/95 px-3 py-2 backdrop-blur-md xl:hidden"
          aria-label={t("nav.primary")}
        >
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="block rounded-xl px-3 py-3 text-base text-foreground transition-colors hover:bg-accent"
            >
              {t(item.key)}
            </Link>
          ))}
          <ButtonLink href="/check" size="pill" className="mt-2 w-full sm:hidden">
            {t("nav.cta")}
          </ButtonLink>
        </nav>
      ) : null}
    </header>
  );
}
