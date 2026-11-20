"use client";

import { RiTranslate2 } from "@remixicon/react";

import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { useI18n } from "@/lib/i18n/provider";
import type { Locale } from "@/lib/i18n/messages";
import { cx } from "@/utils/cx";

const LABELS: Record<Locale, { short: string; name: string }> = {
  "zh-CN": { short: "中文", name: "简体中文" },
  "en-US": { short: "EN", name: "English" },
};

/** Language switch: a two-way segmented control, or a single toggle button on a collapsed rail. */
export function LocaleToggle({ collapsed = false, className }: { collapsed?: boolean; className?: string }) {
  const { locale, setLocale, t } = useI18n();
  if (collapsed) {
    const next: Locale = locale === "zh-CN" ? "en-US" : "zh-CN";
    return (
      <button
        type="button"
        onClick={() => setLocale(next)}
        aria-label={`${t("common.language")}: ${LABELS[next].name}`}
        title={LABELS[next].name}
        className="flex size-9 cursor-pointer items-center justify-center rounded-full bg-background-tertiary-default text-foreground-icon-secondary outline-none hover:bg-background-tertiary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
      >
        <RiTranslate2 className="size-5" aria-hidden />
      </button>
    );
  }
  return (
    <SegmentedControl
      aria-label={t("common.language")}
      selectedKeys={new Set([locale])}
      onSelectionChange={(keys) => {
        const value = [...keys][0] as Locale | undefined;
        if (value) setLocale(value);
      }}
      className={cx("w-full [&>button]:flex-1", className)}
    >
      {(Object.keys(LABELS) as Locale[]).map((key) => (
        <SegmentedControlItem key={key} id={key} aria-label={LABELS[key].name} lang={key}>
          <span className="flex items-center gap-1.5">
            {key === "zh-CN" && <RiTranslate2 className="size-4" aria-hidden />}
            {LABELS[key].short}
          </span>
        </SegmentedControlItem>
      ))}
    </SegmentedControl>
  );
}
