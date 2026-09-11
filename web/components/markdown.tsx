import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

/**
 * Scheme prose, rendered as the government published it.
 *
 * Raw HTML is deliberately not enabled: this text comes from an external corpus,
 * and the only safe assumption about text you did not write is that it is data.
 * Markdown-only rendering means the worst a malformed record can do is look odd.
 *
 * Styling is written out rather than pulled from a typography plugin because
 * these documents are dense — long nested lists of documents and conditions —
 * and need tighter spacing than prose defaults give.
 */
/**
 * myScheme's text carries hand-written `<br>` tags inside otherwise plain
 * Markdown, and because raw HTML is off — rightly — they were reaching the
 * page as the literal characters "<br>", mid-sentence, in the middle of the
 * eligibility rules someone is trying to read.
 *
 * Turning them into real line breaks fixes that WITHOUT opening the corpus's
 * HTML up to the renderer. Only the break tags are touched; anything else stays
 * visible as text, which is the honest failure for content we did not write.
 */
function normalise(text: string): string {
  return text
    .replace(/<br\s*\/?>/gi, "\n")
    // A trailing break before a blank line just adds an empty paragraph.
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function Markdown({
  children,
  className,
}: {
  children: string | null | undefined;
  className?: string;
}) {
  if (!children?.trim()) return null;
  const text = normalise(children);
  if (!text) return null;

  return (
    <div
      className={cn(
        "text-[0.95rem] leading-relaxed text-foreground/90",
        "[&_p]:my-3",
        "[&_ul]:my-3 [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5",
        "[&_ol]:my-3 [&_ol]:list-decimal [&_ol]:space-y-1.5 [&_ol]:pl-5",
        "[&_li]:pl-1 [&_li>ul]:my-1.5 [&_li>ol]:my-1.5",
        "[&_strong]:font-semibold [&_strong]:text-foreground",
        "[&_h1]:mt-6 [&_h1]:mb-2 [&_h1]:text-lg [&_h1]:font-semibold",
        "[&_h2]:mt-6 [&_h2]:mb-2 [&_h2]:text-base [&_h2]:font-semibold",
        "[&_h3]:mt-5 [&_h3]:mb-2 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:uppercase [&_h3]:tracking-wide [&_h3]:text-muted-foreground",
        "[&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4",
        "[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:text-muted-foreground",
        // Government tables are wide; let them scroll rather than break the page.
        "[&_table]:my-4 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
        "[&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-3 [&_th]:py-2 [&_th]:text-left",
        "[&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_td]:align-top",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children: content }) => (
            <a href={href} target="_blank" rel="noopener noreferrer nofollow">
              {content}
            </a>
          ),
          table: ({ children: content }) => (
            <div className="my-4 overflow-x-auto">
              <table>{content}</table>
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
