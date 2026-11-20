"use client";

import { PageHeader } from "@/components/kivi/app-shell";
import { AlertsList } from "@/components/kivi/alerts-list";
import { Legend } from "@/components/kivi/charts/kit";
import { DiscriminationChart, HeatmapScale, PsiHeatmap, PsiTrendChart } from "@/components/kivi/charts/stability";
import { ChartPanel, DataTable, Panel } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { levelOf, STATUS_COLOR, StatusBadge } from "@/components/kivi/status";
import { useI18n } from "@/lib/i18n/provider";
import { useAnalytics } from "@/lib/queries";

export default function StabilityPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const query = useAnalytics();
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return <PageSkeleton />;
  const { stability, meta, alerts } = query.data;
  const th = stability.thresholds;
  const f = (v: number | null, d = 3) => i18n.num(v, { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmt2 = (v: number) => i18n.num(v, { minimumFractionDigits: 2 });

  return (
    <>
      <PageHeader
        title={t("stability.title")}
        subtitle={t("stability.subtitle", {
          start: i18n.month(meta.sample.train_months[0], true),
          end: i18n.month(meta.sample.train_months[1], true),
        })}
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <ChartPanel
          className="xl:col-span-2"
          title={t("stability.scorePsi")}
          description={t("stability.scorePsiDesc")}
          legend={
            <Legend
              items={[
                { label: t("stability.stable", { warn: fmt2(th.warn) }), color: STATUS_COLOR.normal },
                { label: t("stability.shifted", { warn: fmt2(th.warn), alert: fmt2(th.alert) }), color: STATUS_COLOR.warn },
                { label: t("stability.drifted", { alert: fmt2(th.alert) }), color: STATUS_COLOR.alert },
              ]}
            />
          }
          chart={<PsiTrendChart monthly={stability.monthly} thresholds={th} />}
          table={
            <DataTable
              columns={[
                { key: "month", label: t("stability.month") },
                { key: "psi", label: "PSI", align: "end" },
                { key: "level", label: t("stability.level") },
                { key: "period", label: "" },
              ]}
              rows={stability.monthly.map((m) => ({
                key: m.month,
                cells: {
                  month: i18n.month(m.month, true),
                  psi: f(m.score_psi),
                  level: <StatusBadge level={levelOf(m.score_psi, th.warn, th.alert)} />,
                  period: m.in_reference ? t("stability.reference") : t("stability.monitoring"),
                },
              }))}
            />
          }
        />
        <Panel title={t("overview.alerts")} description={t("overview.alertsDesc")}>
          <AlertsList alerts={alerts} />
        </Panel>
      </div>

      <ChartPanel
        title={t("stability.discrimination")}
        description={t("stability.discriminationDesc")}
        legend={
          <Legend
            items={[
              { label: "AUC", color: "var(--viz-1)", shape: "line" },
              { label: "KS", color: "var(--viz-2)", shape: "line" },
            ]}
          />
        }
        chartClassName="h-[240px]"
        chart={<DiscriminationChart monthly={stability.monthly} />}
        table={
          <DataTable
            columns={[
              { key: "month", label: t("stability.month") },
              { key: "auc", label: "AUC", align: "end" },
              { key: "ks", label: "KS", align: "end" },
              { key: "score", label: t("stability.meanScore"), align: "end" },
            ]}
            rows={stability.monthly.map((m) => ({
              key: m.month,
              cells: { month: i18n.month(m.month, true), auc: f(m.auc), ks: f(m.ks), score: i18n.num(m.mean_score) },
            }))}
          />
        }
      />

      <ChartPanel
        title={t("stability.featurePsi")}
        description={t("stability.featurePsiDesc")}
        legend={<HeatmapScale thresholds={th} />}
        chartClassName="h-auto"
        chart={<PsiHeatmap features={stability.feature_psi} months={meta.sample.months} monthly={stability.monthly} thresholds={th} />}
        table={
          <DataTable
            columns={[
              { key: "feature", label: t("stability.feature") },
              ...meta.sample.months.map((m) => ({ key: m, label: i18n.month(m), align: "end" as const })),
            ]}
            rows={stability.feature_psi.map((row) => ({
              key: row.name,
              cells: Object.fromEntries([
                ["feature", i18n.pick(row.label)],
                ...meta.sample.months.map((m, i) => [m, f(row.values[i])]),
              ]),
            }))}
          />
        }
      />
    </>
  );
}
