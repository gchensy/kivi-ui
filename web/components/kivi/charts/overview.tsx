"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useI18n } from "@/lib/i18n/provider";
import type { DailyDecision, Decision, Monthly, RuleHit } from "@/lib/types";

import {
  ANIMATION,
  AXIS_LINE,
  AXIS_TICK,
  BAR_MAX,
  BAR_RADIUS,
  BAR_RADIUS_H,
  CURSOR_BAND,
  CURSOR_LINE,
  GRID,
  RingDot,
  SURFACE_GAP,
  tipDatum,
  TooltipCard,
  type TipProps,
} from "./kit";

export const DECISION_COLOR: Record<Decision, string> = {
  pass: "var(--viz-good)",
  review: "var(--viz-warning)",
  reject: "var(--viz-critical)",
};
export const DECISIONS: Decision[] = ["pass", "review", "reject"];

export function DecisionTrendChart({ daily }: { daily: DailyDecision[] }) {
  const i18n = useI18n();
  const day = (d: string) => i18n.date(`${d}T00:00:00`, { month: "numeric", day: "numeric" });
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap="22%">
        <CartesianGrid {...GRID} />
        <XAxis
          dataKey="date"
          tickFormatter={day}
          tick={AXIS_TICK}
          axisLine={AXIS_LINE}
          tickLine={false}
          tickMargin={8}
          minTickGap={18}
        />
        <YAxis width={40} tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<DailyDecision>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={i18n.date(`${d.date}T00:00:00`, { dateStyle: "medium" })}
                rows={DECISIONS.map((k) => ({
                  label: i18n.t(`overview.${k}`),
                  value: i18n.num(d[k]),
                  color: DECISION_COLOR[k],
                  shape: "rect",
                }))}
                footer={`${i18n.t("overview.approval")} ${i18n.pct(d.approval_rate)} · ${i18n.num(d.total)}`}
              />
            );
          }}
        />
        {DECISIONS.map((k, i) => (
          <Bar
            key={k}
            dataKey={k}
            stackId="decision"
            fill={DECISION_COLOR[k]}
            maxBarSize={BAR_MAX}
            radius={i === DECISIONS.length - 1 ? BAR_RADIUS : 0}
            {...SURFACE_GAP}
            {...ANIMATION}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MonthlyIntakeChart({ monthly, metric }: { monthly: Monthly[]; metric: "applications" | "bad_rate" }) {
  const i18n = useI18n();
  const monitoring = monthly.filter((m) => !m.in_reference);
  const area = monitoring.length ? (
    <ReferenceArea
      x1={monitoring[0].month}
      x2={monitoring[monitoring.length - 1].month}
      fill="var(--viz-grid)"
      fillOpacity={0.55}
      label={{ value: i18n.t("stability.monitoring"), position: "insideTop", fill: "var(--viz-tick)", fontSize: 12 }}
    />
  ) : null;
  const tooltip = (
    <Tooltip
      cursor={metric === "applications" ? CURSOR_BAND : CURSOR_LINE}
      content={(props: TipProps<Monthly>) => {
        const d = tipDatum(props);
        if (!d) return null;
        return (
          <TooltipCard
            title={i18n.month(d.month, true)}
            rows={[
              { label: i18n.t("overview.applicationsMetric"), value: i18n.num(d.applications) },
              { label: i18n.t("overview.badRateMetric"), value: i18n.pct(d.bad_rate, 2) },
            ]}
            footer={monitoring.length ? (d.in_reference ? i18n.t("stability.reference") : i18n.t("stability.monitoring")) : undefined}
          />
        );
      }}
    />
  );
  const x = (
    <XAxis
      dataKey="month"
      tickFormatter={(m) => i18n.month(m)}
      tick={AXIS_TICK}
      axisLine={AXIS_LINE}
      tickLine={false}
      tickMargin={8}
    />
  );
  return (
    <ResponsiveContainer width="100%" height="100%">
      {metric === "applications" ? (
        <BarChart data={monthly} margin={{ top: 20, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          {area}
          {x}
          <YAxis width={44} domain={[0, "auto"]} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.num(v, { notation: "compact" })} />
          {tooltip}
          <Bar dataKey="applications" fill="var(--viz-1)" maxBarSize={BAR_MAX} radius={BAR_RADIUS} {...ANIMATION} />
        </BarChart>
      ) : (
        <LineChart data={monthly} margin={{ top: 20, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid {...GRID} />
          {area}
          {x}
          <YAxis width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.pct(v, 0)} domain={[0, "auto"]} />
          {tooltip}
          <Line
            type="monotone"
            dataKey="bad_rate"
            stroke="var(--viz-1)"
            strokeWidth={2}
            dot={false}
            activeDot={<RingDot color="var(--viz-1)" />}
            {...ANIMATION}
          />
        </LineChart>
      )}
    </ResponsiveContainer>
  );
}

export function RuleHitsChart({ rules }: { rules: RuleHit[] }) {
  const i18n = useI18n();
  const data = rules.map((r) => ({ ...r, name: `${r.code} ${i18n.pick(r.label)}` }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }} barCategoryGap="28%">
        <CartesianGrid {...GRID} vertical horizontal={false} />
        <XAxis type="number" tick={AXIS_TICK} axisLine={false} tickLine={false} allowDecimals={false} />
        <YAxis
          type="category"
          dataKey="name"
          width={i18n.locale === "zh-CN" ? 210 : 230}
          tick={{ ...AXIS_TICK, fill: "var(--color-text-secondary)" }}
          axisLine={AXIS_LINE}
          tickLine={false}
        />
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={d.name}
                rows={[
                  { label: i18n.t("overview.hits"), value: i18n.num(d.hits), color: DECISION_COLOR[d.decision], shape: "rect" },
                  { label: i18n.t("overview.exclusive"), value: i18n.num(d.exclusive) },
                  { label: i18n.t("overview.hitRate"), value: i18n.pct(d.hit_rate) },
                ]}
                footer={i18n.t(`overview.${d.decision}`)}
              />
            );
          }}
        />
        <Bar dataKey="hits" maxBarSize={18} radius={BAR_RADIUS_H} {...ANIMATION}>
          {data.map((r) => (
            <Cell key={r.code} fill={DECISION_COLOR[r.decision]} />
          ))}
          <LabelList dataKey="hits" position="right" fill="var(--color-text-secondary)" fontSize={12} formatter={(v) => i18n.num(Number(v))} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function EffectChart({ effect }: { effect: Record<Decision, number | null> }) {
  const i18n = useI18n();
  const data = DECISIONS.map((k) => ({ key: k, name: i18n.t(`overview.${k}`), value: effect[k] }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 22, right: 4, bottom: 0, left: 0 }} barCategoryGap="30%">
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" tick={{ ...AXIS_TICK, fill: "var(--color-text-secondary)" }} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} />
        <YAxis width={40} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.pct(v, 0)} />
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            return d ? <TooltipCard title={d.name} rows={[{ label: i18n.t("overview.badRate"), value: i18n.pct(d.value, 2) }]} /> : null;
          }}
        />
        <Bar dataKey="value" maxBarSize={40} radius={BAR_RADIUS} {...ANIMATION}>
          {data.map((d) => (
            <Cell key={d.key} fill={DECISION_COLOR[d.key]} />
          ))}
          <LabelList dataKey="value" position="top" fill="var(--color-text-primary)" fontSize={12} formatter={(v) => i18n.pct(Number(v))} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
