"use client";

import { RiAddLine, RiPulseLine } from "@remixicon/react";
import { useState } from "react";

import { ButtonLink } from "@/components/base/buttons/button";
import { AlertsList } from "@/components/kivi/alerts-list";
import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { DiscriminationChart, HeatmapScale, PsiHeatmap, PsiTrendChart } from "@/components/kivi/charts/stability";
import { ChartPanel, DataTable, Panel } from "@/components/kivi/panel";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { levelOf, STATUS_COLOR, StatusBadge } from "@/components/kivi/status";
import { useI18n } from "@/lib/i18n/provider";
import { useStability } from "@/lib/queries";
import type { MonitorKind, StabilityView } from "@/lib/types";

function Missing({ text }: { text: string }) {
  return <p className="flex h-full min-h-[160px] items-center justify-center text-body-regular text-text-tertiary">{text}</p>;
}

export default function StabilityPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const [modelId, setModelId] = useState<string | undefined>(undefined);
  const query = useStability(modelId);
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return <PageSkeleton />;
  const data = query.data;

  if (!data.model) {
    return (
      <>
        <PageHeader title={t("stability.title")} />
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
          <RiPulseLine className="size-8 text-foreground-icon-tertiary" aria-hidden />
          <p className="max-w-[520px] text-body-regular text-text-secondary">{t("stability.noMonitors")}</p>
          <ButtonLink href="/monitors" leadingIcon={RiAddLine}>{t("stability.setup")}</ButtonLink>
        </div>
      </>
    );
  }

  const { monthly = [], months = [], feature_psi: features = [], monitors = {}, alerts = [] } = data as Required<StabilityView>;
  const th = data.thresholds ?? { warn: 0.1, alert: 0.25 };
  const f = (v: number | null | undefined, d = 3) => i18n.num(v ?? null, { minimumFractionDigits: d, maximumFractionDigits: d });
  const fmt2 = (v: number) => i18n.num(v, { minimumFractionDigits: 2 });
  const ranAt = (kind: MonitorKind) => {
    const m = monitors[kind];
    if (!m) return t("stability.missing", { what: t(`mon.kinds.${kind}`) });
    return t("stability.ranAt", { name: m.name, time: m.ran_at ? i18n.date(m.ran_at, { dateStyle: "short", timeStyle: "short" }) : t("stability.notRun") });
  };
  const reference = data.reference;

  return (
    <>
      <PageHeader
        title={t("stability.title")}
        subtitle={
          reference
            ? t("stability.subtitle", { model: i18n.pick(data.model.name), start: i18n.month(reference[0], true), end: i18n.month(reference[1], true) })
            : i18n.pick(data.model.name)
        }
        actions={
          data.models.length > 1 ? (
            <SelectField
              className="w-[240px]"
              size="sm"
              label={t("stability.model")}
              value={data.model.id}
              onChange={setModelId}
              options={data.models.map((m) => ({ id: m.id, label: `${m.code} · ${i18n.pick(m.name)}` }))}
            />
          ) : undefined
        }
      />
      <div className="grid gap-4 xl:grid-cols-3">
        <ChartPanel
          className="xl:col-span-2"
          title={t("stability.scorePsi")}
          description={`${t("stability.scorePsiDesc")} · ${ranAt("score_psi")}`}
          legend={
            <Legend
              items={[
                { label: t("stability.stable", { warn: fmt2(th.warn) }), color: STATUS_COLOR.normal },
                { label: t("stability.shifted", { warn: fmt2(th.warn), alert: fmt2(th.alert) }), color: STATUS_COLOR.warn },
                { label: t("stability.drifted", { alert: fmt2(th.alert) }), color: STATUS_COLOR.alert },
              ]}
            />
          }
          chart={monitors.score_psi ? <PsiTrendChart monthly={monthly} thresholds={th} /> : <Missing text={ranAt("score_psi")} />}
          table={
            <DataTable
              columns={[
                { key: "month", label: t("stability.month") },
                { key: "rows", label: t("stability.rows"), align: "end" },
                { key: "psi", label: "PSI", align: "end" },
                { key: "level", label: t("stability.level") },
                { key: "period", label: "" },
              ]}
              rows={monthly.map((m) => ({
                key: m.month,
                cells: {
                  month: i18n.month(m.month, true),
                  rows: i18n.num(m.rows),
                  psi: f(m.score_psi),
                  level: m.score_psi === null ? "—" : <StatusBadge level={levelOf(m.score_psi, th.warn, th.alert)} />,
                  period: m.in_reference ? t("stability.reference") : t("stability.monitoring"),
                },
              }))}
            />
          }
        />
        <Panel title={t("stability.alerts")} description={t("overview.alertsDesc")}>
          <AlertsList alerts={alerts} />
        </Panel>
      </div>

      <ChartPanel
        title={t("stability.discrimination")}
        description={`${t("stability.discriminationDesc", { ks: f(data.reference_metrics?.ks) })} · ${ranAt("model_ks")}`}
        legend={
          <Legend
            items={[
              { label: "AUC", color: "var(--viz-1)", shape: "line" },
              { label: "KS", color: "var(--viz-2)", shape: "line" },
            ]}
          />
        }
        chartClassName="h-[240px]"
        chart={monitors.model_ks ? <DiscriminationChart monthly={monthly} /> : <Missing text={ranAt("model_ks")} />}
        table={
          <DataTable
            columns={[
              { key: "month", label: t("stability.month") },
              { key: "auc", label: "AUC", align: "end" },
              { key: "ks", label: "KS", align: "end" },
              { key: "bad", label: t("overview.badRate"), align: "end" },
            ]}
            rows={monthly.map((m) => ({
              key: m.month,
              cells: { month: i18n.month(m.month, true), auc: f(m.auc), ks: f(m.ks), bad: i18n.pct(m.bad_rate, 2) },
            }))}
          />
        }
      />

      <ChartPanel
        title={t("stability.featurePsi")}
        description={`${t("stability.featurePsiDesc")} · ${ranAt("indicator_psi")}`}
        legend={<HeatmapScale thresholds={th} />}
        chartClassName="h-auto"
        chart={
          features.length ? <PsiHeatmap features={features} months={months} monthly={monthly} thresholds={th} /> : <Missing text={ranAt("indicator_psi")} />
        }
        table={
          <DataTable
            columns={[{ key: "feature", label: t("stability.feature") }, ...months.map((m) => ({ key: m, label: i18n.month(m), align: "end" as const }))]}
            rows={features.map((row) => ({
              key: row.name,
              cells: Object.fromEntries([["feature", i18n.pick(row.label)], ...months.map((m, i) => [m, f(row.values[i])])]),
            }))}
          />
        }
      />
    </>
  );
}
