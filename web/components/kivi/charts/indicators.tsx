"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { binLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import type { Indicator } from "@/lib/types";

import {
  ANIMATION,
  AXIS_LINE,
  AXIS_TICK,
  BAR_MAX,
  BAR_RADIUS,
  BAR_RADIUS_H,
  CURSOR_BAND,
  GRID,
  SignedBar,
  tipDatum,
  TooltipCard,
  type TipProps,
} from "./kit";

export const IV_CUTOFF = 0.02;

export function IvRankingChart({
  indicators,
  active,
  onSelect,
}: {
  indicators: Indicator[];
  active: string;
  onSelect: (name: string) => void;
}) {
  const i18n = useI18n();
  const data = indicators.map((s) => ({ ...s, display: i18n.pick(s.label) }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 0, right: 48, bottom: 0, left: 0 }}
        barCategoryGap="26%"
        onClick={(state) => {
          const index = Number(state?.activeTooltipIndex);
          if (Number.isFinite(index) && data[index]) onSelect(data[index].name);
        }}
        className="cursor-pointer"
      >
        <CartesianGrid {...GRID} vertical horizontal={false} />
        <XAxis type="number" tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.num(v, { maximumFractionDigits: 2 })} />
        <YAxis
          type="category"
          dataKey="display"
          width={i18n.locale === "zh-CN" ? 128 : 150}
          tick={(props: { x?: number | string; y?: number | string; payload?: { value?: unknown; index?: number } }) => {
            const item = data[props.payload?.index ?? -1];
            const current = item?.name === active;
            return (
              <text
                x={Number(props.x) - 6}
                y={Number(props.y)}
                dy={4}
                textAnchor="end"
                fontSize={12}
                fontWeight={current ? 600 : 400}
                fill={current ? "var(--color-text-primary)" : "var(--color-text-secondary)"}
              >
                {String(props.payload?.value ?? "")}
              </text>
            );
          }}
          axisLine={AXIS_LINE}
          tickLine={false}
          interval={0}
        />
        <ReferenceLine
          x={IV_CUTOFF}
          stroke="var(--viz-tick)"
          strokeDasharray="3 3"
          label={{ value: "0.02", position: "insideTopRight", fill: "var(--viz-tick)", fontSize: 11 }}
        />
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={d.display}
                rows={[
                  { label: i18n.t("indicators.iv"), value: i18n.num(d.iv, { maximumFractionDigits: 3 }), color: d.selected ? "var(--viz-1)" : "var(--viz-neutral)", shape: "rect" },
                  { label: i18n.t("indicators.level"), value: i18n.t(`indicators.levels.${d.level}`) },
                  { label: i18n.t("indicators.trend"), value: i18n.t(`indicators.trends.${d.trend}`) },
                ]}
                footer={d.selected ? i18n.t("indicators.selected") : i18n.t("indicators.notSelected")}
              />
            );
          }}
        />
        <Bar dataKey="iv" maxBarSize={16} radius={BAR_RADIUS_H} {...ANIMATION}>
          {data.map((d) => (
            <Cell
              key={d.name}
              fill={d.selected ? "var(--viz-1)" : "var(--viz-neutral)"}
              fillOpacity={d.name === active ? 1 : 0.78}
            />
          ))}
          <LabelList
            dataKey="iv"
            position="right"
            fill="var(--color-text-secondary)" fontSize={12}
            formatter={(v) => i18n.num(Number(v), { minimumFractionDigits: 3, maximumFractionDigits: 3 })}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export type BinMetric = "woe" | "bad_rate" | "share";

export function BinChart({
  indicator,
  metric,
  overallBadRate,
}: {
  indicator: Indicator;
  metric: BinMetric;
  overallBadRate: number;
}) {
  const i18n = useI18n();
  const data = indicator.bins.map((b) => ({ ...b, name: binLabel(b, indicator.unit, i18n) }));
  const format = (v: number) =>
    metric === "woe" ? i18n.num(v, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : i18n.pct(v, metric === "share" ? 0 : 1);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 22, right: 4, bottom: 0, left: 0 }} barCategoryGap="24%">
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" tick={{ ...AXIS_TICK, fill: "var(--color-text-secondary)" }} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} interval={0} />
        <YAxis width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => format(Number(v))} />
        {metric === "woe" && <ReferenceLine y={0} stroke="var(--viz-axis)" />}
        {metric === "bad_rate" && (
          <ReferenceLine
            y={overallBadRate}
            stroke="var(--viz-tick)"
            strokeDasharray="3 3"
            label={{ value: i18n.t("indicators.overall", { value: i18n.pct(overallBadRate) }), position: "insideTopRight", fill: "var(--viz-tick)", fontSize: 11 }}
          />
        )}
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={d.name}
                rows={[
                  { label: i18n.t("indicators.woe"), value: i18n.num(d.woe, { minimumFractionDigits: 3, maximumFractionDigits: 3 }) },
                  { label: i18n.t("indicators.badRate"), value: i18n.pct(d.bad_rate, 2) },
                  { label: i18n.t("indicators.share"), value: i18n.pct(d.share) },
                  { label: i18n.t("indicators.count"), value: i18n.num(d.count) },
                ]}
                footer={`IV ${i18n.num(d.iv, { maximumFractionDigits: 4 })}`}
              />
            );
          }}
        />
        <Bar dataKey={metric} maxBarSize={56} radius={BAR_RADIUS} shape={metric === "woe" ? <SignedBar /> : undefined} {...ANIMATION}>
          {data.map((d) => (
            <Cell
              key={String(d.code)}
              fill={metric === "woe" ? (d.woe >= 0 ? "var(--viz-pos)" : "var(--viz-neg)") : "var(--viz-1)"}
            />
          ))}
          <LabelList
            dataKey={metric}
            position="top"
            fill="var(--color-text-secondary)" fontSize={12}
            formatter={(v) => format(Number(v))}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export { BAR_MAX };
