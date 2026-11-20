"use client";

import { RiBarChart2Line, RiTableLine } from "@remixicon/react";
import { useState, type ReactNode } from "react";

import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { useI18n } from "@/lib/i18n/provider";
import { cx } from "@/utils/cx";

/** A titled card on the secondary surface, matching BoardUI's chart cards. */
export function Panel({
  title,
  description,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cx("flex min-w-0 flex-col gap-4 rounded-2xl bg-background-secondary-default p-4", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-0.5">
            {title && <h2 className="text-headline-medium text-text-primary">{title}</h2>}
            {description && <p className="text-body-2-regular text-text-tertiary">{description}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx("flex min-w-0 flex-1 flex-col", bodyClassName)}>{children}</div>
    </section>
  );
}

/**
 * A chart card with a chart/table switch. Every chart ships its table twin, so
 * no value is reachable only by hovering.
 */
export function ChartPanel({
  title,
  description,
  legend,
  controls,
  chart,
  table,
  className,
  chartClassName = "h-[280px]",
}: {
  title: ReactNode;
  description?: ReactNode;
  legend?: ReactNode;
  controls?: ReactNode;
  chart: ReactNode;
  table: ReactNode;
  className?: string;
  chartClassName?: string;
}) {
  const { t } = useI18n();
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <Panel
      title={title}
      description={description}
      className={className}
      actions={
        <>
          {controls}
          <SegmentedControl
            aria-label={`${t("common.chart")} / ${t("common.table")}`}
            selectedKeys={new Set([view])}
            onSelectionChange={(keys) => setView(([...keys][0] as "chart" | "table") ?? "chart")}
          >
            <SegmentedControlItem id="chart" aria-label={t("common.chart")}>
              <RiBarChart2Line className="size-4" aria-hidden />
            </SegmentedControlItem>
            <SegmentedControlItem id="table" aria-label={t("common.table")}>
              <RiTableLine className="size-4" aria-hidden />
            </SegmentedControlItem>
          </SegmentedControl>
        </>
      }
    >
      {view === "chart" ? (
        <div className="flex flex-col gap-3">
          {legend}
          <div className={cx("w-full min-w-0", chartClassName)}>{chart}</div>
        </div>
      ) : (
        <div className="max-h-[340px] overflow-auto rounded-xl bg-background-primary-default">{table}</div>
      )}
    </Panel>
  );
}

/** A small segmented switch for picking which measure a chart shows. */
export function MetricSwitch<K extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: K;
  onChange: (value: K) => void;
  options: { id: K; label: string }[];
  label: string;
}) {
  return (
    <SegmentedControl
      aria-label={label}
      selectedKeys={new Set([value])}
      onSelectionChange={(keys) => {
        const next = [...keys][0] as K | undefined;
        if (next) onChange(next);
      }}
    >
      {options.map((option) => (
        <SegmentedControlItem key={option.id} id={option.id}>
          {option.label}
        </SegmentedControlItem>
      ))}
    </SegmentedControl>
  );
}

export function DataTable({
  columns,
  rows,
}: {
  columns: { key: string; label: ReactNode; align?: "start" | "end" }[];
  rows: { key: string | number; cells: Record<string, ReactNode> }[];
}) {
  return (
    <table className="bui-table bui-table-sm">
      <thead className="sticky top-0 z-10">
        <tr>
          {columns.map((column) => (
            <th key={column.key} className={column.align === "end" ? "!text-end" : undefined}>
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.key}>
            {columns.map((column) => (
              <td key={column.key} className={cx("tabular-nums", column.align === "end" && "text-end")}>
                {row.cells[column.key]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
