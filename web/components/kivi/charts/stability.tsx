"use client";

import { Fragment } from "react";
import { Focusable } from "react-aria-components";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Tooltip as HoverTip, TooltipTrigger } from "@/components/base/tooltip/tooltip";
import { useI18n } from "@/lib/i18n/provider";


import { levelOf, STATUS_COLOR } from "../status";
import {
  ANIMATION,
  AXIS_LINE,
  AXIS_TICK,
  BAR_MAX,
  BAR_RADIUS,
  CURSOR_BAND,
  CURSOR_LINE,
  GRID,
  RingDot,
  tipDatum,
  TooltipCard,
  type TipProps,
} from "./kit";

type Thresholds = { warn: number; alert: number };
type MonthPoint = { month: string; in_reference: boolean };
type DiscriminationPoint = MonthPoint & { auc: number | null; ks: number | null };
type FeatureRow = { name: string; label: { zh: string; en: string }; values: (number | null)[] };

function referenceShade(monthly: { month: string; in_reference: boolean }[], label: string) {
  const reference = monthly.filter((m) => m.in_reference);
  if (!reference.length) return null;
  return (
    <ReferenceArea
      x1={reference[0].month}
      x2={reference[reference.length - 1].month}
      fill="var(--viz-grid)"
      fillOpacity={0.55}
      label={{ value: label, position: "insideTop", fill: "var(--viz-tick)", fontSize: 12 }}
    />
  );
}

export function PsiTrendChart({ monthly, thresholds }: { monthly: (MonthPoint & { score_psi: number | null; rows?: number | null })[]; thresholds: Thresholds }) {
  return (
    <PsiBars
      data={monthly.map((m) => ({ month: m.month, psi: m.score_psi, in_reference: m.in_reference, rows: m.rows ?? undefined }))}
      thresholds={thresholds}
    />
  );
}

type PsiPoint = { month: string; psi: number | null; in_reference: boolean; rows?: number };

/** Monthly PSI bars coloured by status, with threshold lines and the reference period shaded. */
export function PsiBars({ data, thresholds, referenceLabel }: { data: PsiPoint[]; thresholds: Thresholds; referenceLabel?: string }) {
  const i18n = useI18n();
  const monthly = data;
  const reference = referenceLabel ?? i18n.t("stability.reference");
  const step = 0.05;
  const top = Math.ceil(Math.max(thresholds.alert * 1.2, ...monthly.map((m) => m.psi ?? 0)) / step) * step;
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => Math.round(i * step * 100) / 100);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={monthly} margin={{ top: 20, right: 40, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} />
        {referenceShade(monthly, reference)}
        <XAxis dataKey="month" tickFormatter={(m) => i18n.month(m)} tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} />
        <YAxis width={44} domain={[0, top]} ticks={ticks} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.num(v, { maximumFractionDigits: 2 })} />
        {(["warn", "alert"] as const).map((k) => (
          <ReferenceLine
            key={k}
            y={thresholds[k]}
            stroke={STATUS_COLOR[k]}
            strokeDasharray="4 3"
            label={{ value: i18n.num(thresholds[k], { minimumFractionDigits: 2 }), position: "right", fill: "var(--color-text-secondary)", fontSize: 11 }}
          />
        ))}
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<PsiPoint>) => {
            const d = tipDatum(props);
            if (!d) return null;
            const level = levelOf(d.psi ?? 0, thresholds.warn, thresholds.alert);
            return (
              <TooltipCard
                title={i18n.month(d.month, true)}
                rows={[
                  { label: "PSI", value: i18n.num(d.psi, { minimumFractionDigits: 3, maximumFractionDigits: 3 }), color: STATUS_COLOR[level], shape: "rect" },
                  { label: i18n.t("stability.level"), value: i18n.t(`alerts.${level}`) },
                  ...(d.rows !== undefined ? [{ label: i18n.t("data.rows"), value: i18n.num(d.rows) }] : []),
                ]}
                footer={d.in_reference ? reference : i18n.t("stability.monitoring")}
              />
            );
          }}
        />
        <Bar dataKey="psi" maxBarSize={BAR_MAX} radius={BAR_RADIUS} {...ANIMATION}>
          {monthly.map((m) => (
            <Cell key={m.month} fill={STATUS_COLOR[levelOf(m.psi ?? 0, thresholds.warn, thresholds.alert)]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DiscriminationChart({ monthly }: { monthly: DiscriminationPoint[] }) {
  const i18n = useI18n();
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={monthly} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} />
        {referenceShade(monthly, i18n.t("stability.reference"))}
        <XAxis dataKey="month" tickFormatter={(m) => i18n.month(m)} tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} />
        <YAxis width={44} domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.num(v, { maximumFractionDigits: 2 })} />
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<DiscriminationPoint>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={i18n.month(d.month, true)}
                rows={[
                  { label: "AUC", value: i18n.num(d.auc, { minimumFractionDigits: 3, maximumFractionDigits: 3 }), color: "var(--viz-1)" },
                  { label: "KS", value: i18n.num(d.ks, { minimumFractionDigits: 3, maximumFractionDigits: 3 }), color: "var(--viz-2)" },
                ]}
              />
            );
          }}
        />
        <Line type="monotone" dataKey="auc" connectNulls stroke="var(--viz-1)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-1)" />} {...ANIMATION} />
        <Line type="monotone" dataKey="ks" connectNulls stroke="var(--viz-2)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-2)" />} {...ANIMATION} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Sequential classes: < 0.02, < warn, < alert, ≥ alert (and a step for ≥ 2 × alert). */
export function psiClass(value: number | null, t: Thresholds): number {
  if (value === null) return 0;
  if (value < 0.02) return 0;
  if (value < t.warn) return 1;
  if (value < t.alert) return 2;
  return value < t.alert * 2 ? 3 : 4;
}

export function PsiHeatmap({
  features,
  months,
  monthly,
  thresholds,
}: {
  features: FeatureRow[];
  months: string[];
  monthly: { in_reference: boolean }[];
  thresholds: Thresholds;
}) {
  const i18n = useI18n();
  return (
    <div className="overflow-x-auto">
      <div
        className="grid min-w-[720px] gap-0.5"
        style={{ gridTemplateColumns: `minmax(128px, 1.4fr) repeat(${months.length}, minmax(44px, 1fr))` }}
        role="grid"
        aria-label={i18n.t("stability.featurePsi")}
      >
        <div />
        {months.map((m, i) => (
          <div
            key={m}
            className="pb-1.5 text-center text-caption-1-medium text-text-tertiary"
            title={monthly[i]?.in_reference ? i18n.t("stability.reference") : i18n.t("stability.monitoring")}
          >
            {i18n.month(m)}
            <span
              className="mx-auto mt-1 block h-0.5 w-6 rounded-full"
              style={{ background: monthly[i]?.in_reference ? "var(--viz-neutral)" : "var(--viz-1)" }}
              aria-hidden
            />
          </div>
        ))}
        {features.map((feature) => (
          <Fragment key={feature.name}>
            <div className="flex items-center truncate pe-2 text-body-2-medium text-text-secondary" role="rowheader">
              {i18n.pick(feature.label)}
            </div>
            {feature.values.map((value, i) => {
              const cls = psiClass(value, thresholds);
              const text = i18n.num(value, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
              return (
                <TooltipTrigger key={months[i]} delay={80}>
                  <Focusable>
                    <span
                      role="gridcell"
                      tabIndex={0}
                      aria-label={`${i18n.pick(feature.label)} ${i18n.month(months[i], true)} PSI ${text}`}
                      className="flex h-8 items-center justify-center rounded-md text-caption-1-medium tabular-nums outline-none transition-[filter] hover:brightness-95 focus-visible:ring-2 focus-visible:ring-border-focus-ring"
                      style={{ background: `var(--viz-seq-${cls})`, color: `var(--viz-seq-ink-${cls})` }}
                    >
                      {cls >= 2 ? text : ""}
                    </span>
                  </Focusable>
                  <HoverTip size="md">
                    <span className="flex flex-col gap-0.5">
                      <span className="text-body-2-semibold tabular-nums">PSI {text}</span>
                      <span className="text-caption-1-regular text-text-secondary">
                        {i18n.pick(feature.label)} · {i18n.month(months[i], true)}
                      </span>
                    </span>
                  </HoverTip>
                </TooltipTrigger>
              );
            })}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

export function HeatmapScale({ thresholds }: { thresholds: Thresholds }) {
  const i18n = useI18n();
  const f = (v: number) => i18n.num(v, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const steps = [
    { cls: 0, label: "< 0.02" },
    { cls: 1, label: `0.02–${f(thresholds.warn)}` },
    { cls: 2, label: `${f(thresholds.warn)}–${f(thresholds.alert)}` },
    { cls: 3, label: `${f(thresholds.alert)}–${f(thresholds.alert * 2)}` },
    { cls: 4, label: `≥ ${f(thresholds.alert * 2)}` },
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-caption-1-medium text-text-secondary">
      <span>PSI</span>
      <div className="flex items-center gap-1">
        {steps.map((s) => (
          <span key={s.cls} className="flex flex-col items-center gap-1">
            <span className="h-2.5 w-[72px] rounded-sm" style={{ background: `var(--viz-seq-${s.cls})` }} aria-hidden />
            <span className="tabular-nums">{s.label}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
