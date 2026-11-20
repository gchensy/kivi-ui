"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { bandLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import type { Analytics, Gain } from "@/lib/types";

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

type Model = Analytics["model"];

export const SPLIT_COLOR = { train: "var(--viz-1)", oot: "var(--viz-2)" } as const;

export function RocChart({ roc }: { roc: Model["roc"] }) {
  const i18n = useI18n();
  const data = roc.train.curve.map((p, i) => ({ fpr: p.fpr, train: p.tpr, oot: roc.oot.curve[i]?.tpr ?? null, chance: p.fpr }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} vertical />
        <XAxis
          type="number"
          dataKey="fpr"
          domain={[0, 1]}
          ticks={[0, 0.25, 0.5, 0.75, 1]}
          tickFormatter={(v) => i18n.pct(v, 0)}
          tick={AXIS_TICK}
          axisLine={AXIS_LINE}
          tickLine={false}
          tickMargin={8}
        />
        <YAxis
          domain={[0, 1]}
          ticks={[0, 0.25, 0.5, 0.75, 1]}
          tickFormatter={(v) => i18n.pct(v, 0)}
          width={44}
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={`${i18n.t("models.fpr")} ${i18n.pct(d.fpr, 0)}`}
                rows={[
                  { label: i18n.t("models.trainShort"), value: i18n.pct(d.train), color: SPLIT_COLOR.train },
                  { label: i18n.t("models.ootShort"), value: i18n.pct(d.oot), color: SPLIT_COLOR.oot },
                ]}
              />
            );
          }}
        />
        <Line dataKey="chance" stroke="var(--viz-neutral)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="train" stroke={SPLIT_COLOR.train} strokeWidth={2} dot={false} activeDot={<RingDot color={SPLIT_COLOR.train} />} {...ANIMATION} />
        <Line type="monotone" dataKey="oot" stroke={SPLIT_COLOR.oot} strokeWidth={2} dot={false} activeDot={<RingDot color={SPLIT_COLOR.oot} />} {...ANIMATION} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function ScoreDistributionChart({ bands, metric }: { bands: Model["bands"]; metric: "share" | "bad_rate" }) {
  const i18n = useI18n();
  const data = bands.train.map((b, i) => ({
    name: bandLabel(b.lower, b.upper),
    train: b[metric],
    oot: bands.oot[i]?.[metric] ?? null,
    trainCount: b.count,
    ootCount: bands.oot[i]?.count ?? 0,
  }));
  const format = (v: number | null) => i18n.pct(v, metric === "share" ? 1 : 2);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="22%" barGap={2}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="name" tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} interval={0} />
        <YAxis width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.pct(v, 0)} />
        <Tooltip
          cursor={CURSOR_BAND}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={`${i18n.t("models.band")} ${d.name}`}
                rows={[
                  { label: i18n.t("models.trainShort"), value: format(d.train), color: SPLIT_COLOR.train, shape: "rect" },
                  { label: i18n.t("models.ootShort"), value: format(d.oot), color: SPLIT_COLOR.oot, shape: "rect" },
                ]}
                footer={`${i18n.t("models.count")} ${i18n.num(d.trainCount)} / ${i18n.num(d.ootCount)}`}
              />
            );
          }}
        />
        <Bar dataKey="train" fill={SPLIT_COLOR.train} maxBarSize={BAR_MAX / 2 + 4} radius={BAR_RADIUS} {...ANIMATION} />
        <Bar dataKey="oot" fill={SPLIT_COLOR.oot} maxBarSize={BAR_MAX / 2 + 4} radius={BAR_RADIUS} {...ANIMATION} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function KsCurveChart({ gains }: { gains: Gain[] }) {
  const i18n = useI18n();
  const total = gains.reduce((sum, g) => sum + g.count, 0);
  let seen = 0;
  const data = [
    { population: 0, cum_bad_pct: 0, cum_good_pct: 0, ks: 0, decile: 0, min_score: null as number | null, max_score: null as number | null },
    ...gains.map((g) => {
      seen += g.count;
      return { population: seen / total, cum_bad_pct: g.cum_bad_pct, cum_good_pct: g.cum_good_pct, ks: g.ks, decile: g.decile, min_score: g.min_score, max_score: g.max_score };
    }),
  ];
  const peak = data.reduce((best, d) => (d.ks > best.ks ? d : best), data[0]);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 18, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} vertical />
        <XAxis
          type="number"
          dataKey="population"
          domain={[0, 1]}
          ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
          tickFormatter={(v) => i18n.pct(v, 0)}
          tick={AXIS_TICK}
          axisLine={AXIS_LINE}
          tickLine={false}
          tickMargin={8}
        />
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => i18n.pct(v, 0)} width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} />
        <ReferenceLine
          x={peak.population}
          stroke="var(--viz-tick)"
          strokeDasharray="3 3"
          label={{
            value: `KS ${i18n.num(peak.ks, { maximumFractionDigits: 3 })}`,
            position: "top",
            fill: "var(--color-text-secondary)",
            fontSize: 12,
          }}
        />
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={`${i18n.t("models.population")} ${i18n.pct(d.population, 0)}`}
                rows={[
                  { label: i18n.t("models.cumBad"), value: i18n.pct(d.cum_bad_pct), color: "var(--viz-1)" },
                  { label: i18n.t("models.cumGood"), value: i18n.pct(d.cum_good_pct), color: "var(--viz-2)" },
                ]}
                footer={`KS ${i18n.num(d.ks, { maximumFractionDigits: 3 })}${d.min_score !== null ? ` · ${d.min_score}–${d.max_score}` : ""}`}
              />
            );
          }}
        />
        <Line type="monotone" dataKey="cum_bad_pct" stroke="var(--viz-1)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-1)" />} {...ANIMATION} />
        <Line type="monotone" dataKey="cum_good_pct" stroke="var(--viz-2)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-2)" />} {...ANIMATION} />
      </LineChart>
    </ResponsiveContainer>
  );
}
