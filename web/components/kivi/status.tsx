"use client";

import { RiAlarmWarningFill, RiCheckboxCircleFill, RiCloseCircleFill, RiErrorWarningFill } from "@remixicon/react";

import { useI18n } from "@/lib/i18n/provider";
import { cx } from "@/utils/cx";

export type StatusLevel = "alert" | "warn" | "normal" | "error";

const STYLE: Record<StatusLevel, { icon: typeof RiAlarmWarningFill; color: string; key: string }> = {
  alert: { icon: RiAlarmWarningFill, color: "var(--viz-critical)", key: "alerts.alert" },
  warn: { icon: RiErrorWarningFill, color: "var(--viz-warning)", key: "alerts.warn" },
  normal: { icon: RiCheckboxCircleFill, color: "var(--viz-good)", key: "alerts.normal" },
  error: { icon: RiCloseCircleFill, color: "var(--viz-neutral)", key: "alerts.error" },
};

export const STATUS_COLOR: Record<StatusLevel, string> = {
  alert: STYLE.alert.color,
  warn: STYLE.warn.color,
  normal: STYLE.normal.color,
  error: STYLE.error.color,
};

/** Status always carries an icon and a label, never colour alone. */
export function StatusBadge({ level, label, className }: { level: StatusLevel; label?: string; className?: string }) {
  const { t } = useI18n();
  const { icon: Icon, color, key } = STYLE[level];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full bg-background-primary-default py-0.5 pe-2 ps-1 text-caption-1-medium text-text-primary",
        className,
      )}
    >
      <Icon className="size-4 shrink-0" style={{ color }} aria-hidden />
      {label ?? t(key)}
    </span>
  );
}

export function levelOf(value: number, warn: number, alert: number): "alert" | "warn" | "normal" {
  return value >= alert ? "alert" : value >= warn ? "warn" : "normal";
}
