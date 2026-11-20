"use client";

import { RiCheckLine } from "@remixicon/react";
import { useEffect } from "react";

/** A short-lived confirmation toast at the bottom of the screen. */
export function Notice({ text, onDone }: { text: string | null; onDone: () => void }) {
  useEffect(() => {
    if (!text) return;
    const timer = window.setTimeout(onDone, 3200);
    return () => window.clearTimeout(timer);
  }, [text, onDone]);
  if (!text) return null;
  return (
    <div
      role="status"
      className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-full bg-background-inverse-default px-4 py-2 text-body-2-medium text-text-inverse shadow-xl"
    >
      <RiCheckLine className="size-4" aria-hidden />
      {text}
    </div>
  );
}
