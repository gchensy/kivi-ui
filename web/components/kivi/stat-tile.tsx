"use client";

import {
  RiArrowDownCircleFill,
  RiArrowUpCircleFill,
  RiIndeterminateCircleFill,
} from "@remixicon/react";
import type { ComponentType, ReactNode } from "react";

import { cx } from "@/utils/cx";

type IconComponent = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;

export type Tone = "blue" | "orange" | "purple" | "pink" | "sky" | "emerald";
export type DeltaTone = "good" | "bad" | "neutral";

const TILE: Record<Tone, string> = {
  blue: "from-blue-500 to-blue-600",
  orange: "from-orange-400 to-orange-500",
  purple: "from-purple-500 to-purple-600",
  pink: "from-pink-500 to-pink-600",
  sky: "from-sky-400 to-sky-500",
  emerald: "from-emerald-500 to-emerald-600",
};

const DELTA: Record<DeltaTone, { pill: string; text: string }> = {
  good: { pill: "bg-status-lime-background", text: "text-status-lime-text" },
  bad: { pill: "bg-status-rose-background", text: "text-status-rose-text" },
  neutral: { pill: "bg-background-secondary-default", text: "text-text-secondary" },
};

/**
 * KPI tile in BoardUI's footer stat-card recipe: gradient icon tile, label,
 * display value, and a footer band with the comparison and a delta pill. The
 * delta colour reads direction × whether up is good, so it is passed in.
 */
export function StatTile({
  icon: Icon,
  tone,
  label,
  value,
  caption,
  delta,
  deltaTone = "neutral",
  direction,
}: {
  icon: IconComponent;
  tone: Tone;
  label: string;
  value: ReactNode;
  caption: ReactNode;
  delta?: ReactNode;
  deltaTone?: DeltaTone;
  direction?: "up" | "down" | "flat";
}) {
  const DeltaIcon =
    direction === "up" ? RiArrowUpCircleFill : direction === "down" ? RiArrowDownCircleFill : RiIndeterminateCircleFill;
  const style = DELTA[deltaTone];
  return (
    <section className="flex min-w-0 flex-col rounded-2xl bg-background-secondary-default p-2">
      <div className="flex w-full items-start justify-between gap-2.5 p-2">
        <span className={cx("flex size-10 shrink-0 items-center justify-center rounded-2lg bg-linear-to-b", TILE[tone])}>
          <Icon className="size-5 shrink-0 text-white" aria-hidden />
        </span>
      </div>
      <div className="flex flex-col gap-0.5 px-2 pt-2.5 pb-3.5">
        <p className="truncate text-body-medium text-text-secondary">{label}</p>
        <p className="text-display-4-medium whitespace-nowrap text-text-primary">{value}</p>
      </div>
      <div className="mt-auto flex w-full items-center justify-between gap-2 rounded-2lg bg-background-inner-default py-1.5 pe-1.5 ps-2.5 shadow-card">
        <p className="truncate text-body-2-regular text-text-secondary">{caption}</p>
        {delta !== undefined && (
          <span className={cx("flex shrink-0 items-center gap-1 rounded-full py-0.5 pe-2 ps-1", style.pill)}>
            <DeltaIcon className={cx("size-4 shrink-0", style.text)} aria-hidden />
            <span className={cx("text-body-2-medium whitespace-nowrap tabular-nums", style.text)}>{delta}</span>
          </span>
        )}
      </div>
    </section>
  );
}
