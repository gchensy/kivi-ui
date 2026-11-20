import { useId } from "react";

import { cx } from "@/utils/cx";

/** Kivi mark: an accent tile carrying a rising, ROC-like curve over a baseline. */
export function KiviMark({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={cx("size-8 shrink-0", className)} aria-hidden>
      <defs>
        <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--color-accent-500)" />
          <stop offset="100%" stopColor="var(--color-accent-700)" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${id}-bg)`} />
      <path d="M8 23.5 L24 23.5" stroke="white" strokeOpacity="0.35" strokeWidth="1.6" strokeLinecap="round" />
      <path
        d="M8 23 C 9.5 14.5, 13.5 10, 24 8.5"
        fill="none"
        stroke="white"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="24" cy="8.5" r="2.2" fill="white" />
    </svg>
  );
}

export function KiviWordmark({ name, tagline, className }: { name: string; tagline?: string; className?: string }) {
  return (
    <span className={cx("flex min-w-0 items-center gap-2.5", className)}>
      <KiviMark />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-headline-semibold text-text-primary">{name}</span>
        {tagline && <span className="truncate text-caption-1-regular text-text-tertiary">{tagline}</span>}
      </span>
    </span>
  );
}
