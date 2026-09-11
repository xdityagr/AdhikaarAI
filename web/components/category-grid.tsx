import Link from "next/link";

import { cn } from "@/lib/utils";

/**
 * The fifteen kinds of need, as a ruled table rather than fifteen cards.
 *
 * Cards were the wrong instrument here: at four across, each one had room for
 * an icon and a truncated label, so "Public Safety, Law & Justice" arrived as
 * "Public Safety,Law & Justi…". The count is the useful part anyway — it is
 * what tells someone whether this category is worth opening — so it leads, set
 * large and light, and the name is given as many lines as it needs.
 *
 * The hairlines are a one-pixel gap over a border-coloured backing, which is
 * how you get a continuous rule through a grid whose last row is short.
 */
export function CategoryGrid({
  categories,
  className,
}: {
  categories: { name: string; count: number }[];
  className?: string;
}) {
  if (categories.length === 0) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        The scheme list is being rebuilt. Browse or search directly in the
        meantime.
      </p>
    );
  }

  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-3 lg:grid-cols-4",
        className,
      )}
    >
      {categories.map((category) => (
        <Link
          key={category.name}
          href={`/schemes?category=${encodeURIComponent(category.name)}`}
          className="group bg-card px-5 py-6 transition-colors duration-200 hover:bg-accent"
        >
          <span className="tnum block font-display text-[1.75rem] font-light leading-none tracking-[-0.03em] text-leaf transition-transform duration-200 group-hover:-translate-y-0.5">
            {category.count.toLocaleString("en-IN")}
          </span>
          <span className="mt-2.5 block text-[0.9375rem] leading-snug text-foreground">
            {category.name}
          </span>
        </Link>
      ))}
    </div>
  );
}
