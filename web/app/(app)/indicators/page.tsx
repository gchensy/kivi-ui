"use client";

import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Select, SelectItem } from "@/components/base/select/select";
import { PageHeader } from "@/components/kivi/app-shell";
import { BinChart, IvRankingChart, type BinMetric } from "@/components/kivi/charts/indicators";
import { Legend } from "@/components/kivi/charts/kit";
import { ChartPanel, DataTable, MetricSwitch } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { binLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { useAnalytics } from "@/lib/queries";
import type { Indicator, IvLevel } from "@/lib/types";

const LEVEL_CHIP: Record<IvLevel, "neutral" | "yellow" | "cyan" | "blue" | "purple"> = {
  useless: "neutral",
  weak: "yellow",
  medium: "cyan",
  strong: "blue",
  suspicious: "purple",
};

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-background-primary-default px-3 py-2 shadow-card">
      <span className="truncate text-caption-1-medium text-text-tertiary">{label}</span>
      <span className="truncate text-body-semibold text-text-primary">{value}</span>
    </div>
  );
}

export default function IndicatorsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const query = useAnalytics();
  const [active, setActive] = useState<string | null>(null);
  const [metric, setMetric] = useState<BinMetric>("woe");

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return <PageSkeleton />;
  const { indicators, meta } = query.data;
  const current: Indicator = indicators.find((s) => s.name === active) ?? indicators[0];
  const trainBad = current.bins.reduce((s, b) => s + b.bad, 0) / current.bins.reduce((s, b) => s + b.count, 0);
  const f = (v: number, d = 3) => i18n.num(v, { minimumFractionDigits: d, maximumFractionDigits: d });

  return (
    <>
      <PageHeader
        title={t("indicators.title")}
        subtitle={t("indicators.subtitle", {
          start: i18n.month(meta.sample.train_months[0], true),
          end: i18n.month(meta.sample.train_months[1], true),
          rows: i18n.num(meta.sample.train_rows),
        })}
      />
      <div className="grid gap-4 xl:grid-cols-5">
        <ChartPanel
          className="xl:col-span-2"
          title={t("indicators.ivRanking")}
          description={t("indicators.ivRankingDesc")}
          legend={
            <Legend
              items={[
                { label: t("indicators.selected"), color: "var(--viz-1)" },
                { label: t("indicators.notSelected"), color: "var(--viz-neutral)" },
              ]}
            />
          }
          chartClassName="h-[420px]"
          chart={<IvRankingChart indicators={indicators} active={current.name} onSelect={setActive} />}
          table={
            <DataTable
              columns={[
                { key: "name", label: t("indicators.feature") },
                { key: "iv", label: t("indicators.iv"), align: "end" },
                { key: "level", label: t("indicators.level") },
                { key: "trend", label: t("indicators.trend") },
                { key: "missing", label: t("indicators.missingRate"), align: "end" },
              ]}
              rows={indicators.map((s) => ({
                key: s.name,
                cells: {
                  name: (
                    <button type="button" className="cursor-pointer text-start hover:underline" onClick={() => setActive(s.name)}>
                      {i18n.pick(s.label)}
                      {s.selected ? " ✓" : ""}
                    </button>
                  ),
                  iv: f(s.iv),
                  level: t(`indicators.levels.${s.level}`),
                  trend: t(`indicators.trends.${s.trend}`),
                  missing: i18n.pct(s.missing_rate),
                },
              }))}
            />
          }
        />

        <div className="flex min-w-0 flex-col gap-4 xl:col-span-3">
          <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <h2 className="truncate text-title-3-semibold text-text-primary">{i18n.pick(current.label)}</h2>
                <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{current.name}</code>
                {current.selected && <Chip variant="subtle" color="blue">{t("indicators.selected")}</Chip>}
              </div>
              <Select
                aria-label={t("indicators.feature")}
                size="sm"
                selectedKey={current.name}
                onSelectionChange={(key) => key && setActive(String(key))}
                className="w-[200px]"
              >
                {indicators.map((s) => (
                  <SelectItem key={s.name} id={s.name} textValue={i18n.pick(s.label)}>
                    {i18n.pick(s.label)}
                  </SelectItem>
                ))}
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              <Fact label={t("indicators.iv")} value={f(current.iv)} />
              <Fact
                label={t("indicators.level")}
                value={<Chip variant="subtle" color={LEVEL_CHIP[current.level]}>{t(`indicators.levels.${current.level}`)}</Chip>}
              />
              <Fact label={t("indicators.trend")} value={t(`indicators.trends.${current.trend}`)} />
              <Fact label={t("indicators.missingRate")} value={i18n.pct(current.missing_rate)} />
              <Fact label={t("indicators.type")} value={`${t(`indicators.${current.kind}`)} · ${t("indicators.binCount", { n: current.bins.length })}`} />
            </div>
          </section>

          <ChartPanel
            title={t("indicators.detail")}
            description={t(metric === "woe" ? "indicators.woeDesc" : metric === "bad_rate" ? "indicators.badRateDesc" : "indicators.shareDesc")}
            controls={
              <MetricSwitch
                label={t("indicators.detail")}
                value={metric}
                onChange={setMetric}
                options={[
                  { id: "woe", label: t("indicators.metricWoe") },
                  { id: "bad_rate", label: t("indicators.metricBadRate") },
                  { id: "share", label: t("indicators.metricShare") },
                ]}
              />
            }
            legend={
              metric === "woe" ? (
                <Legend
                  items={[
                    { label: t("indicators.higherRisk"), color: "var(--viz-pos)" },
                    { label: t("indicators.lowerRisk"), color: "var(--viz-neg)" },
                  ]}
                />
              ) : undefined
            }
            chartClassName="h-[300px]"
            chart={<BinChart indicator={current} metric={metric} overallBadRate={trainBad} />}
            table={
              <DataTable
                columns={[
                  { key: "bin", label: t("indicators.bin") },
                  { key: "count", label: t("indicators.count"), align: "end" },
                  { key: "share", label: t("indicators.share"), align: "end" },
                  { key: "bad", label: t("indicators.bad"), align: "end" },
                  { key: "rate", label: t("indicators.badRate"), align: "end" },
                  { key: "woe", label: t("indicators.woe"), align: "end" },
                  { key: "iv", label: t("indicators.iv"), align: "end" },
                ]}
                rows={current.bins.map((b) => ({
                  key: String(b.code),
                  cells: {
                    bin: binLabel(b, current.unit, i18n),
                    count: i18n.num(b.count),
                    share: i18n.pct(b.share),
                    bad: i18n.num(b.bad),
                    rate: i18n.pct(b.bad_rate, 2),
                    woe: f(b.woe),
                    iv: f(b.iv, 4),
                  },
                }))}
              />
            }
          />
        </div>
      </div>
    </>
  );
}
