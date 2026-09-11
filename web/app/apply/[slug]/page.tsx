import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ApplicationPack } from "@/components/application-pack";
import { getScheme } from "@/lib/api";
import { getLang, getT } from "@/lib/i18n/server";
import { translator } from "@/lib/i18n";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const lang = await getLang();
  const scheme = await getScheme(slug, lang);
  const t = translator(lang);
  if (!scheme) return { title: t("scheme.notFound") };
  return { title: `${t("apply.title")} — ${scheme.name.trim()}` };
}

/**
 * The filled application, on its own page.
 *
 * The assistant could fill a form and say so, and there was nowhere to look —
 * the filled fields came back as a card the chat had no renderer for. This is
 * where "I have filled in your details" becomes something a person can read,
 * print and carry to a counter.
 *
 * The scheme is fetched on the server so the page has a real title and works
 * from a shared link; the filled values come from the browser, because the
 * profile lives on the device and never touches our database.
 */
export default async function ApplyPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [lang, t] = await Promise.all([getLang(), getT()]);
  const scheme = await getScheme(slug, lang);
  if (!scheme) notFound();

  return (
    <article className="mx-auto max-w-3xl px-5 py-8 sm:px-6 sm:py-12">
      <Link
        href={`/schemes/${slug}`}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-primary print:hidden"
      >
        <ArrowLeft className="size-4" />
        {scheme.name.trim().slice(0, 60)}
      </Link>

      <header className="mt-5 border-b border-border pb-6">
        <p className="meta">{t("apply.title")}</p>
        <h1 className="mt-2 font-display text-2xl font-bold leading-tight sm:text-3xl">
          {scheme.name.trim()}
        </h1>
        {scheme.state && scheme.state !== "All" ? (
          <p className="mt-2 text-sm text-muted-foreground">{scheme.state}</p>
        ) : null}
      </header>

      <div className="mt-8">
        <ApplicationPack slug={slug} />
      </div>
    </article>
  );
}
