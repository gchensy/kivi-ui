"use client";

import {
  RiBarChartGroupedLine,
  RiCheckDoubleLine,
  RiGitBranchLine,
  RiLineChartLine,
  RiPulseLine,
  type RemixiconComponentType,
} from "@remixicon/react";

import { useI18n } from "@/lib/i18n/provider";
import type { AlertItem, MonitorItem, MonitorKind, Schedule } from "@/lib/types";
import { cx } from "@/utils/cx";

import { STATUS_COLOR, type StatusLevel } from "./status";

type I18n = ReturnType<typeof useI18n>;
type Thresholds = { warn: number; alert: number };

export const KINDS: MonitorKind[] = ["score_psi", "indicator_psi", "model_ks", "approval_rate", "rule_hit_rate"];
export const SHIFT_KINDS = new Set<MonitorKind>(["approval_rate", "rule_hit_rate"]);
export const MODEL_KINDS = new Set<MonitorKind>(["score_psi", "model_ks", "indicator_psi"]);

export const KIND_ICON: Record<MonitorKind, RemixiconComponentType> = {
  indicator_psi: RiBarChartGroupedLine,
  score_psi: RiPulseLine,
  model_ks: RiLineChartLine,
  approval_rate: RiCheckDoubleLine,
  rule_hit_rate: RiGitBranchLine,
};

/** Same rule as the API: shifts compare their absolute size; thresholds are inclusive. */
export function levelFor(kind: MonitorKind, value: number | null | undefined, t: Thresholds): "normal" | "warn" | "alert" {
  if (value === null || value === undefined) return "normal";
  const v = SHIFT_KINDS.has(kind) ? Math.abs(value) : value;
  return v >= t.alert ? "alert" : v >= t.warn ? "warn" : "normal";
}

/**
 * The value as people read it. The API stores the KS check as a relative drop (positive is worse);
 * it is shown as the change against the reference, so a 10% drop reads "−10%".
 */
export function displayValue(kind: MonitorKind, value: number): number {
  return kind === "model_ks" ? -value : value;
}

/** A monitor value in its own unit: PSI as a decimal, KS change as a percentage, shifts in points. */
export function formatValue(kind: MonitorKind, value: number | null | undefined, i18n: I18n, signed = true): string {
  if (value === null || value === undefined) return "—";
  if (kind === "score_psi" || kind === "indicator_psi") return i18n.num(value, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const sign = signed ? "exceptZero" : "auto";
  if (kind === "model_ks") return i18n.num(displayValue(kind, value) * 100, { maximumFractionDigits: 1, signDisplay: sign }) + "%";
  return `${i18n.num(value * 100, { maximumFractionDigits: 1, signDisplay: sign })} pp`;
}

/** Thresholds keep their sign for the KS check ("−10%"), and read as sizes for shifts ("5 pp"). */
export function formatThreshold(kind: MonitorKind, value: number, i18n: I18n): string {
  return formatValue(kind, value, i18n, kind === "model_ks");
}

const pad = (n: number) => String(n).padStart(2, "0");

export function scheduleText(schedule: Schedule, i18n: I18n): string {
  const time = `${pad(schedule.hour)}:${pad(schedule.minute)}`;
  return i18n.t(`mon.every.${schedule.freq}`, {
    minute: pad(schedule.minute),
    time,
    weekday: i18n.t(`mon.weekdays.${schedule.weekday}`),
  });
}

export function targetText(monitor: Pick<MonitorItem, "model" | "strategy">): string {
  return monitor.model?.code ?? monitor.strategy?.code ?? "—";
}

const localName = (item: { name: string; name_en?: string | null } | undefined, i18n: I18n) =>
  item ? (i18n.locale === "en-US" && item.name_en ? item.name_en : item.name) : "—";

/** One sentence that says what an alert is about, in the reader's language. */
export function alertText(alert: AlertItem, i18n: I18n): string {
  const kind = alert.monitor.kind;
  const d = alert.detail;
  const period = d.period ? (d.period.includes("/") ? d.period.replace("/", " – ") : i18n.month(d.period, true)) : "—";
  return i18n.t(`alr.text.${kind}`, {
    name: localName(d.worst, i18n),
    model: d.model?.code ?? alert.monitor.model?.code ?? "",
    strategy: d.strategy?.code ?? alert.monitor.strategy?.code ?? "",
    value: formatValue(kind, alert.value, i18n),
    threshold: alert.threshold !== null ? formatThreshold(kind, alert.threshold, i18n) : "—",
    period,
    ks: i18n.num(d.ks ?? null, { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
    days: d.window_days ?? 7,
    current: i18n.pct(d.current?.rate ?? null, 1),
    baseline: i18n.pct(d.baseline?.rate ?? null, 1),
  });
}

/** A small trend line; the last point carries the status colour (with the badge beside it for meaning). */
export function Sparkline({ values, level, className }: { values: (number | null)[]; level?: StatusLevel | null; className?: string }) {
  const points = values.map((v, i) => ({ i, v })).filter((p): p is { i: number; v: number } => p.v !== null);
  const w = 96;
  const h = 28;
  if (points.length < 2) return <span className={cx("inline-block h-7 w-24", className)} aria-hidden />;
  const lo = Math.min(...points.map((p) => p.v));
  const hi = Math.max(...points.map((p) => p.v));
  const span = hi - lo || 1;
  const x = (i: number) => 3 + (i / Math.max(values.length - 1, 1)) * (w - 6);
  const y = (v: number) => h - 4 - ((v - lo) / span) * (h - 8);
  const last = points[points.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className={cx("shrink-0 overflow-visible", className)} aria-hidden>
      <polyline
        points={points.map((p) => `${x(p.i)},${y(p.v)}`).join(" ")}
        fill="none"
        stroke="var(--viz-1)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={x(last.i)} cy={y(last.v)} r={3} fill={STATUS_COLOR[level ?? "normal"]} stroke="var(--color-background-primary-default)" strokeWidth={1.5} />
    </svg>
  );
}
