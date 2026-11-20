"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useI18n } from "@/lib/i18n/provider";
import type { BacktestSummary, Decision } from "@/lib/types";
import { cx } from "@/utils/cx";

import { DECISION_COLOR } from "./overview";
import { ANIMATION, AXIS_LINE, AXIS_TICK, CURSOR_LINE, GRID, RingDot, tipDatum, TooltipCard, type TipProps } from "./kit";

const ORDER: Decision[] = ["pass", "review", "reject"];
const INK: Record<Decision, string> = { pass: "#ffffff", review: "#0b0b0b", reject: "#ffffff" };

/** One whole split into approve / review / decline: a tall segmented bar with shares printed inside. */
export function DecisionMixBar({ summary, label }: { summary: BacktestSummary; label: string }) {
  const i18n = useI18n();
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-caption-1-medium text-text-secondary">{label}</span>
      <div
        className="flex h-7 w-full gap-0.5 overflow-hidden rounded-md"
        role="img"
        aria-label={ORDER.map((d) => `${i18n.t(`stg.decisions.${d}`)} ${i18n.pct(summary[`${d}_rate`])}`).join(", ")}
      >
        {ORDER.map((d) => {
          const share = summary[`${d}_rate`] ?? 0;
          if (!share) return null;
          return (
            <div
              key={d}
              className="flex items-center rounded-[4px] ps-2 text-caption-1-semibold tabular-nums"
              style={{ width: `${share * 100}%`, background: DECISION_COLOR[d], color: INK[d] }}
              title={`${i18n.t(`stg.decisions.${d}`)} ${i18n.num(summary[d])} · ${i18n.pct(share)}`}
            >
              {share >= 0.08 ? i18n.pct(share, 1) : ""}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function PassRateChart({ current, compare, currentLabel, compareLabel }: { current: BacktestSummary; compare?: BacktestSummary; currentLabel: string; compareLabel?: string }) {
  const i18n = useI18n();
  const months = current.monthly ?? [];
  const other = new Map((compare?.monthly ?? []).map((m) => [m.month, m.pass_rate]));
  const data = months.map((m) => ({ month: m.month, current: m.pass_rate, compare: other.get(m.month) ?? null }));
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="month" tickFormatter={(m) => i18n.month(m)} tick={AXIS_TICK} axisLine={AXIS_LINE} tickLine={false} tickMargin={8} />
        <YAxis width={44} domain={["auto", "auto"]} tick={AXIS_TICK} axisLine={false} tickLine={false} tickFormatter={(v) => i18n.pct(v, 0)} />
        <Tooltip
          cursor={CURSOR_LINE}
          content={(props: TipProps<(typeof data)[number]>) => {
            const d = tipDatum(props);
            if (!d) return null;
            return (
              <TooltipCard
                title={i18n.month(d.month, true)}
                rows={[
                  { label: currentLabel, value: i18n.pct(d.current), color: "var(--viz-1)" },
                  ...(compare ? [{ label: compareLabel ?? "", value: i18n.pct(d.compare), color: "var(--viz-2)" }] : []),
                ]}
              />
            );
          }}
        />
        {compare && (
          <Line type="monotone" dataKey="compare" stroke="var(--viz-2)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-2)" />} {...ANIMATION} />
        )}
        <Line type="monotone" dataKey="current" stroke="var(--viz-1)" strokeWidth={2} dot={false} activeDot={<RingDot color="var(--viz-1)" />} {...ANIMATION} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/** Decisions under the comparison version (rows) against this version (columns). */
export function SwapMatrix({ cells }: { cells: { from: Decision; to: Decision; rows: number; bad_rate: number | null }[] }) {
  const i18n = useI18n();
  const max = Math.max(1, ...cells.filter((c) => c.from !== c.to).map((c) => c.rows));
  return (
    <div className="grid grid-cols-[auto_repeat(3,minmax(0,1fr))] gap-1 text-body-2-regular">
      <span />
      {ORDER.map((d) => (
        <span key={d} className="px-2 pb-1 text-center text-caption-1-medium text-text-tertiary">{i18n.t(`stg.decisions.${d}`)}</span>
      ))}
      {ORDER.map((from) => (
        <div key={from} className="contents">
          <span className="flex items-center pe-2 text-caption-1-medium text-text-tertiary">{i18n.t(`stg.decisions.${from}`)}</span>
          {ORDER.map((to) => {
            const cell = cells.find((c) => c.from === from && c.to === to);
            const same = from === to;
            const weight = same ? 0 : (cell?.rows ?? 0) / max;
            return (
              <div
                key={to}
                className={cx("flex flex-col items-center justify-center rounded-lg px-2 py-2 tabular-nums", same ? "bg-background-tertiary-default" : "")}
                style={same ? undefined : { background: `color-mix(in srgb, var(--viz-seq-3) ${Math.round(weight * 55)}%, var(--color-background-primary-default))` }}
              >
                <span className="text-body-2-semibold text-text-primary">{i18n.num(cell?.rows ?? 0)}</span>
                {/* Shaded cells keep primary ink: secondary grey loses contrast on the blue fill. */}
                <span className={cx("text-caption-1-regular", same || !cell?.rows ? "text-text-secondary" : "text-text-primary")}>
                  {cell?.rows ? `(${i18n.pct(cell.bad_rate, 1)})` : "—"}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
