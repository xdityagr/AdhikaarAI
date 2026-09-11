import { AssistantRail } from "@/components/assistant-rail";
import { ChatPanel } from "@/components/chat-panel";
import { getScheme } from "@/lib/api";
import { getLang, getPlace, getT } from "@/lib/i18n/server";

export async function generateMetadata() {
  const t = await getT();
  return { title: t("chat.title"), description: t("chat.lede") };
}

function one(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export default async function ChatPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const params = await searchParams;
  const slug = one(params.scheme);
  const [place, lang] = await Promise.all([getPlace(), getLang()]);

  // Arrived from a scheme page. Look the scheme up rather than trusting the
  // slug: it is shown to the person and sent to the assistant, so a stale or
  // hand-edited URL must not put an invented scheme name in front of either.
  // The name is fetched in the reader's language so the chip matches the page
  // they just left.
  const scheme = slug ? await getScheme(slug, lang) : null;

  // Fills the viewport below the header, so the composer sits at the bottom
  // edge of the screen. A chat that scrolls the page instead is unusable on a
  // phone, where the keyboard already takes half the screen.
  //
  // 100dvh rather than vh: on mobile Safari and Chrome the visual viewport
  // shrinks when the address bar is showing, and vh does not know that, so the
  // composer ends up under the browser chrome exactly when it is being used.
  return (
    <div className="flex h-[calc(100dvh-4rem)] overflow-hidden">
      <AssistantRail state={place} />
      {/* The rail carries the title on a wide screen. On a phone there is no
          rail, so the panel shows its own heading instead of opening with an
          unattributed paragraph. */}
      <ChatPanel
        className="min-w-0 flex-1"
        showHeading="mobile"
        scheme={
          scheme ? { slug: scheme.slug, name: scheme.name.trim() } : undefined
        }
      />
    </div>
  );
}
