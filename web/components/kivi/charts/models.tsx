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
import type { Band, Gain, Roc, Split } from "@/lib/types";

import {
  ANIMATION,
  AXIS_LINE,
  AXIS_TICK,
  BAR_RADIUS,
  CURSOR_BAND,
  CURSOR_LINE,
  GRID,
  RingDot,
  tipDatum,
  TooltipCard,
  type TipProps,
} from "./kit";

export const SPLIT_COLOR: Record<Split, string> = { train: "var(--viz-1)", test: "var(--viz-3)", oot: "var(--viz-2)" };
export const SPLIT_ORDER: Split[] = ["train", "test", "oot"];

type Evaluation = Partial<Record<Split, { roc?: Roc; bands: Band[] }>>;

/** ROC of every split present; all curves share the same resampled FPR grid. */
export function RocChart({ evaluation }: { evaluation: Evaluation }) {
  const i18n = useI18n();
  const splits = SPLIT_ORDER.filter((s) => evaluation[s]?.roc);
  const grid = evaluation[splits[0]]?.roc?.curve ?? [];
  const data = grid.map((p, i) => ({
    fpr: p.fpr,
    chance: p.fpr,
    ...Object.fromEntries(splits.map((s) => [s, evaluation[s]?.roc?.curve[i]?.tpr ?? null])),
  })) as ({ fpr: number; chance: number } & Partial<Record<Split, number | null>>)[];
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
        <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v) => i18n.pct(v, 0)} width={44} tick={AXIS_TICK} axisLine={false} tickLine={false} />
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={`${i18n.t("models.fpr")} ${i18n.pct(d.fpr, 0)}`}
                rows={splits.map((s) => ({ label: i18n.t(`mdl.splits.${s}`), value: i18n.pct(d[s] ?? null), color: SPLIT_COLOR[s] }))}
              />
            );
          }}
        />
        <Line dataKey="chance" stroke="var(--viz-neutral)" strokeWidth={1.5} strokeDasharray="4 4" dot={false} activeDot={false} isAnimationActive={false} />
        {splits.map((s) => (
          <Line key={s} type="monotone" dataKey={s} stroke={SPLIT_COLOR[s]} strokeWidth={2} dot={false} activeDot={<RingDot color={SPLIT_COLOR[s]} />} {...ANIMATION} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Share or bad rate of each split in common score bands (grouped bars, one per split). */
export function BandsChart({ evaluation, metric }: { evaluation: Evaluation; metric: "share" | "bad_rate" }) {
  const i18n = useI18n();
  const splits = SPLIT_ORDER.filter((s) => evaluation[s]);
  const reference = evaluation[splits[0]]?.bands ?? [];
  const data = reference.map((b, i) => ({
    name: bandLabel(b.lower, b.upper),
    ...Object.fromEntries(splits.map((s) => [s, evaluation[s]?.bands[i]?.[metric] ?? null])),
  })) as ({ name: string } & Partial<Record<Split, number | null>>)[];
  const format = (v: number | null | undefined) => i18n.pct(v ?? null, metric === "share" ? 1 : 2);
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="20%" barGap={2}>
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
                rows={splits.map((s) => ({ label: i18n.t(`mdl.splits.${s}`), value: format(d[s]), color: SPLIT_COLOR[s], shape: "rect" }))}
              />
            );
          }}
        />
        {splits.map((s) => (
          <Bar key={s} dataKey={s} fill={SPLIT_COLOR[s]} maxBarSize={14} radius={BAR_RADIUS} {...ANIMATION} />
        ))}
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
