"use client";

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

import { useI18n } from "@/lib/i18n/provider";
import type { MonitorKind, MonitorRun, RunFacts, SeriesPoint } from "@/lib/types";

import { displayValue, formatThreshold, formatValue, levelFor } from "../monitoring";
import { STATUS_COLOR } from "../status";
import {
  ANIMATION,
  AXIS_LINE,
  AXIS_TICK,
  BAR_RADIUS_H,
  CURSOR_BAND,
  CURSOR_LINE,
  GRID,
  RingDot,
  tipDatum,
  TooltipCard,
  type TipProps,
} from "./kit";

type Thresholds = { warn: number; alert: number };

/** The smallest of 1, 2, 2.5, 5 × 10^k that is at least `x`, so halves and quarters stay round. */
function niceCeil(x: number): number {
  if (x <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(x));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * power >= x - 1e-12) ?? 10;
  return step * power;
}

/** Daily approval rate; the observation window is shaded and the baseline rate is a dashed line. */
export function ApprovalTrendChart({ series, facts }: { series: SeriesPoint[]; facts: RunFacts }) {
  const i18n = useI18n();
  const day = (d: string) => i18n.date(`${d}T00:00:00`, { month: "numeric", day: "numeric" });
  const inWindow = series.filter((s) => !s.in_reference);
  const baseline = facts.baseline?.rate ?? null;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={series} margin={{ top: 20, right: 44, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} />
        {inWindow.length > 0 && (
          <ReferenceArea
            x1={inWindow[0].period}
            x2={inWindow[inWindow.length - 1].period}
            fill="var(--viz-grid)"
            fillOpacity={0.55}
            label={{ value: i18n.t("mon.current"), position: "insideTop", fill: "var(--viz-tick)", fontSize: 12 }}
          />
        )}
        <XAxis dataKey="period" tickFormatter={day} tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} minTickGap={18} />
        <YAxis width={44} domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.pct(v, 0)} />
        {baseline !== null && (
          <ReferenceLine
            y={baseline}
            stroke="var(--viz-neutral)"
            strokeDasharray="4 3"
            label={{ value: i18n.t("mon.baselineLabel"), position: "right", fill: "var(--color-text-secondary)", fontSize: 11 }}
          />
        )}
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<SeriesPoint>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={i18n.date(`${d.period}T00:00:00`, { dateStyle: "medium" })}
                rows={[
                  { label: i18n.t("overview.approval"), value: i18n.pct(d.value, 1), color: "var(--viz-1)" },
                  { label: i18n.t("data.rows"), value: i18n.num(d.rows ?? 0) },
                ]}
                footer={d.in_reference ? i18n.t("mon.baselineLabel") : i18n.t("mon.current")}
              />
            );
          }}
        />
        <Line type="monotone" dataKey="value" connectNulls stroke="var(--viz-1)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-1)" />} {...ANIMATION} />
      </LineChart>
    </ResponsiveContainer>
  );
}

type ShiftRow = NonNullable<RunFacts["rules"]>[number] & { label: string };

/** Change of each rule's hit rate against its baseline, in points; colour follows the thresholds. */
export function RuleShiftChart({ rules, thresholds }: { rules: NonNullable<RunFacts["rules"]>; thresholds: Thresholds }) {
  const i18n = useI18n();
  const data: ShiftRow[] = rules.map((r) => ({ ...r, label: `${r.code} ${i18n.locale === "en-US" && r.name_en ? r.name_en : r.name}` }));
  const reach = niceCeil(Math.max(thresholds.alert * 1.2, ...data.map((r) => Math.abs(r.shift))));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 44, bottom: 0, left: 0 }} barCategoryGap="28%">
        <CartesianGrid {...GRID} vertical horizontal={false} />
        <XAxis
          type="number"
          domain={[-reach, reach]}
          ticks={[-reach, -reach / 2, 0, reach / 2, reach]}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v) => `${i18n.num(v * 100, { maximumFractionDigits: 0, signDisplay: "exceptZero" })}`}
        />
        <YAxis type="category" dataKey="label" width={i18n.locale === "zh-CN" ? 190 : 260} tick={{ ...AXIS_TICK, fill: "var(--color-text-secondary)" }} axisLine={false} tickLine={false} />
        <ReferenceLine x={0} stroke="var(--viz-axis)" />
        {(["warn", "alert"] as const).flatMap((k) =>
          [-1, 1].map((sign) => (
            <ReferenceLine key={`${k}${sign}`} x={sign * thresholds[k]} stroke={STATUS_COLOR[k]} strokeDasharray="4 3" />
          )),
        )}
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<ShiftRow>) => {
            const d = tipDatum(props);
            if (!d) return null;
            const level = levelFor("rule_hit_rate", d.shift, thresholds);
            return (
              <TooltipCard
                title={d.label}
                rows={[
                  { label: i18n.t("mon.shift"), value: formatValue("rule_hit_rate", d.shift, i18n), color: STATUS_COLOR[level], shape: "rect" },
                  { label: i18n.t("mon.current"), value: i18n.pct(d.current, 2) },
                  { label: i18n.t("mon.baselineLabel"), value: i18n.pct(d.baseline, 2) },
                ]}
                footer={i18n.t(`alerts.${level}`)}
              />
            );
          }}
        />
        <Bar dataKey="shift" maxBarSize={16} radius={BAR_RADIUS_H} {...ANIMATION}>
          {data.map((r) => (
            <Cell key={r.code} fill={STATUS_COLOR[levelFor("rule_hit_rate", r.shift, thresholds)]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/** Headline value of each successful run over time, with the threshold lines. */
export function RunHistoryChart({ runs, kind, thresholds }: { runs: MonitorRun[]; kind: MonitorKind; thresholds: Thresholds }) {
  const i18n = useI18n();
  const data = runs
    .filter((r) => r.status === "done")
    .slice()
    .reverse()
    .map((r) => ({ ...r, at: new Date(r.created_at).getTime(), shown: r.value === null ? null : displayValue(kind, r.value) }));
  const shift = kind === "approval_rate" || kind === "rule_hit_rate";
  const ks = kind === "model_ks";
  const values = data.map((d) => d.shown ?? 0);
  const top = niceCeil(Math.max(thresholds.alert * 1.2, ...values.map(Math.abs)));
  const symmetric = shift || ks;
  const ticks = symmetric ? [-top, -top / 2, 0, top / 2, top] : [0, top / 4, top / 2, (3 * top) / 4, top];
  const lines = (["warn", "alert"] as const).flatMap((k) =>
    (shift ? [-1, 1] : [ks ? -1 : 1]).map((sign) => ({ key: `${k}${sign}`, k, y: sign * thresholds[k] })),
  );
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 12, right: 52, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis
          dataKey="at"
          type="number"
          scale="time"
          domain={["dataMin", "dataMax"]}
          tickFormatter={(v) => i18n.date(new Date(v).toISOString(), { month: "numeric", day: "numeric" })}
          tick={AXIS_TICK}
          axisLine={AXIS_LINE}
          tickLine={false}
          tickMargin={8}
          minTickGap={24}
        />
        <YAxis
          width={64}
          domain={symmetric ? [-top, top] : [0, top]}
          ticks={ticks}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v) => (ks ? formatValue(kind, -v, i18n) : formatThreshold(kind, v, i18n))}
        />
        {lines.map((l) => (
          <ReferenceLine
            key={l.key}
            y={l.y}
            stroke={STATUS_COLOR[l.k]}
            strokeDasharray="4 3"
            label={
              l.y > 0 || ks
                ? { value: ks ? formatValue(kind, -l.y, i18n) : formatThreshold(kind, l.y, i18n), position: "right", fill: "var(--color-text-secondary)", fontSize: 11 }
                : undefined
            }
          />
        ))}
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={i18n.date(d.created_at, { dateStyle: "medium", timeStyle: "short" })}
                rows={[{ label: i18n.t(`mon.valueLabel.${kind}`), value: formatValue(kind, d.value, i18n), color: STATUS_COLOR[d.level === "error" ? "error" : d.level], shape: "line" }]}
                footer={i18n.t(`mon.triggers.${d.trigger}`)}
              />
            );
          }}
        />
        <Line
          type="monotone"
          dataKey="shown"
          stroke="var(--viz-1)"
          strokeWidth={2}
          dot={data.length < 3 ? { r: 3, fill: "var(--viz-1)" } : false}
          activeDot={<RingDot color="var(--viz-1)" />}
          {...ANIMATION}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
