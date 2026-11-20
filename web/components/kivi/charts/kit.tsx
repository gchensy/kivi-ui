"use client";

import type { ReactNode } from "react";

import { cx } from "@/utils/cx";

/** Chart chrome shared by every Recharts chart: recessive solid hairlines, muted ticks. */
export const AXIS_TICK = { fontSize: 12, fill: "var(--viz-tick)" } as const;
export const GRID = { stroke: "var(--viz-grid)", strokeDasharray: undefined, vertical: false } as const;
export const AXIS_LINE = { stroke: "var(--viz-axis)" } as const;
export const CURSOR_LINE = { stroke: "var(--viz-axis)", strokeWidth: 1 } as const;
export const CURSOR_BAND = { fill: "var(--viz-grid)", opacity: 0.6 } as const;
/** 2px gap in the card surface colour between touching fills (stacked segments, adjacent bars). */
export const SURFACE_GAP = { stroke: "var(--color-background-secondary-default)", strokeWidth: 2 } as const;
export const BAR_MAX = 24;
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
export const BAR_RADIUS_H: [number, number, number, number] = [0, 4, 4, 0];
const reducedMotion =
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
export const ANIMATION = { isAnimationActive: !reducedMotion, animationDuration: 450 } as const;

export type LegendItem = { label: string; color: string; shape?: "rect" | "line" | "dash" };

/** Legend mirrors the mark: a square for bars and areas, a stroke for lines. */
export function Legend({ items, className }: { items: LegendItem[]; className?: string }) {
  return (
    <ul className={cx("flex flex-wrap items-center gap-x-4 gap-y-1 text-body-2-medium text-text-secondary", className)}>
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          {item.shape === "line" || item.shape === "dash" ? (
            <svg width="14" height="8" aria-hidden className="shrink-0">
              <line
                x1="1"
                y1="4"
                x2="13"
                y2="4"
                stroke={item.color}
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray={item.shape === "dash" ? "3 3" : undefined}
              />
            </svg>
          ) : (
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: item.color }} aria-hidden />
          )}
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export type TooltipRow = { label: string; value: ReactNode; color?: string; shape?: "line" | "rect" };

/** Tooltip surface: the value leads, the series name follows, keyed with a short stroke. */
export function TooltipCard({ title, rows, footer }: { title?: ReactNode; rows: TooltipRow[]; footer?: ReactNode }) {
  return (
    <div className="min-w-[160px] rounded-xl border border-border-button-default bg-background-primary-default px-3 py-2.5 shadow-lg">
      {title && <p className="mb-1.5 text-caption-1-medium text-text-tertiary">{title}</p>}
      <ul className="flex flex-col gap-1">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center gap-2">
            {row.color && (
              <span
                className={cx("shrink-0", row.shape === "rect" ? "size-2.5 rounded-[3px]" : "h-0.5 w-3 rounded-full")}
                style={{ background: row.color }}
                aria-hidden
              />
            )}
            <span className="text-body-2-semibold text-text-primary tabular-nums">{row.value}</span>
            <span className="text-body-2-regular text-text-secondary">{row.label}</span>
          </li>
        ))}
      </ul>
      {footer && <div className="mt-1.5 border-t border-separator-border pt-1.5 text-caption-1-regular text-text-tertiary">{footer}</div>}
    </div>
  );
}

/** Recharts passes `active` and `payload`; this narrows them for our tooltips. */
// The type parameter only carries the datum type from the chart to tipDatum.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export type TipProps<T = unknown> = { active?: boolean; payload?: ReadonlyArray<{ payload?: unknown }>; label?: unknown };

export function tipDatum<T>(props: TipProps<T>): T | null {
  return props.active && props.payload?.length ? ((props.payload[0].payload as T) ?? null) : null;
}

/** End-dot with a 2px surface ring, so it reads where it crosses other marks. */
export function RingDot({ cx: x, cy: y, color, r = 4 }: { cx?: number; cy?: number; color: string; r?: number }) {
  if (x === undefined || y === undefined) return null;
  return <circle cx={x} cy={y} r={r} fill={color} stroke="var(--color-background-secondary-default)" strokeWidth={2} />;
}

/**
 * Bar shape with a 4px rounded data end and a square baseline, for bars that
 * can run either side of zero (WOE): the rounded end follows the sign.
 */
export function SignedBar(props: {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  fill?: string;
  fillOpacity?: number;
  value?: number | [number, number];
}) {
  const { x = 0, y = 0, width = 0, height = 0, fill, fillOpacity } = props;
  const value = Array.isArray(props.value) ? props.value[1] - props.value[0] : (props.value ?? 0);
  const top = Math.min(y, y + height);
  const h = Math.abs(height);
  const r = Math.min(4, h, width / 2);
  if (h === 0 || width === 0) return null;
  const path =
    value >= 0
      ? `M${x},${top + h} V${top + r} Q${x},${top} ${x + r},${top} H${x + width - r} Q${x + width},${top} ${x + width},${top + r} V${top + h} Z`
      : `M${x},${top} V${top + h - r} Q${x},${top + h} ${x + r},${top + h} H${x + width - r} Q${x + width},${top + h} ${x + width},${top + h - r} V${top} Z`;
  return <path d={path} fill={fill} fillOpacity={fillOpacity} />;
}
