"use client";

import { usePathname } from "next/navigation";
import { useState } from "react";
import { MessageCircle, X } from "lucide-react";

import { ChatPanel } from "@/components/chat-panel";
import { useLanguage } from "@/components/language-provider";
import { Button } from "@/components/ui/button";

/**
 * The assistant, reachable from every page without being the whole product.
 *
 * It is a launcher rather than a takeover because the chat is one way in, not
 * the only one: the browse and check flows exist for people who would rather
 * read and tap than type, which on a small keyboard in a second language is
 * most people.
 */
export function ChatLauncher() {
  const { t } = useLanguage();
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // The dedicated chat page already is the chat.
  if (pathname === "/chat") return null;

  return (
    <>
      <Button
        type="button"
        onClick={() => setOpen(true)}
        size="pill"
        className="fixed bottom-5 end-5 z-40 shadow-[0_10px_30px_-10px_rgba(20,64,47,0.55)]"
        aria-label={t("chat.title")}
      >
        <MessageCircle className="size-4" />
        <span className="hidden sm:inline">{t("chat.launcher")}</span>
      </Button>

      {open ? (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div
            className="absolute inset-0 bg-foreground/15 backdrop-blur-[2px]"
            aria-hidden
            onClick={() => setOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("chat.title")}
            className="relative flex h-full w-full max-w-md flex-col border-s border-border bg-paper shadow-[0_0_60px_-12px_rgba(28,26,23,0.3)]"
          >
            <header className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 className="font-display text-[1.0625rem] font-normal tracking-[-0.02em]">
                  {t("chat.title")}
                </h2>
                <p className="mt-0.5 text-[0.8125rem] text-muted-foreground">
                  {t("chat.subtitle")}
                </p>
              </div>
              <Button
                variant="ghost"
                size="pill-icon"
                className="size-9"
                onClick={() => setOpen(false)}
                aria-label={t("nav.menu.close")}
              >
                <X className="size-5" />
              </Button>
            </header>
            <ChatPanel className="min-h-0 flex-1" />
          </div>
        </div>
      ) : null}
    </>
  );
}
