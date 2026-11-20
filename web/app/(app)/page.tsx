"use client";

import {
  RiAlarmWarningFill,
  RiArrowRightSLine,
  RiCheckDoubleLine,
  RiFileList2Fill,
  RiLineChartFill,
  RiPulseFill,
  RiScales3Fill,
} from "@remixicon/react";
import { useState } from "react";

import { ButtonLink } from "@/components/base/buttons/button";
import { AlertsList } from "@/components/kivi/alerts-list";
import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { DECISION_COLOR, DECISIONS, DecisionTrendChart, EffectChart, MonthlyIntakeChart, RuleHitsChart } from "@/components/kivi/charts/overview";
import { ChartPanel, DataTable, MetricSwitch, Panel } from "@/components/kivi/panel";
import { StatTile, type DeltaTone } from "@/components/kivi/stat-tile";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { levelOf } from "@/components/kivi/status";
import { signed } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { useAnalytics } from "@/lib/queries";

function deltaTone(change: number, upIsGood: boolean): DeltaTone {
  if (Math.abs(change) < 1e-9) return "neutral";
  return change > 0 === upIsGood ? "good" : "bad";
}
const direction = (change: number) => (change > 0 ? "up" : change < 0 ? "down" : "flat");

export default function OverviewPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const query = useAnalytics();
  const [intake, setIntake] = useState<"applications" | "bad_rate">("applications");

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return <PageSkeleton />;
  const data = query.data;
  const { kpis, decisions, stability, meta, model } = data;
  const f3 = (v: number) => i18n.num(v, { minimumFractionDigits: 3, maximumFractionDigits: 3 });

  const appChange = (kpis.applications_30d - kpis.applications_prev_30d) / kpis.applications_prev_30d;
  const approvalChange = kpis.approval_rate_30d - kpis.approval_rate_prev_30d;
  const ksChange = kpis.ks_oot - kpis.ks_train;
  const aucChange = kpis.auc_oot - kpis.auc_train;
  const psiLevel = levelOf(kpis.score_psi_latest, stability.thresholds.warn, stability.thresholds.alert);
  const openAlerts = kpis.alerts.alert + kpis.alerts.warn;
  const pp = (v: number) => `${i18n.num(v * 100, { maximumFractionDigits: 1, signDisplay: "exceptZero" })} pp`;

  return (
    <>
      <PageHeader
        title={t("overview.title")}
        subtitle={t("overview.subtitle", { model: i18n.pick(model.name), date: i18n.date(`${meta.as_of}T00:00:00`, { dateStyle: "long" }) })}
      />
      <p className="mx-1 rounded-xl bg-status-blue-background px-3 py-2 text-body-2-regular text-status-blue-text">
        {t("overview.demoNote", {
          rows: i18n.num(meta.sample.rows),
          start: i18n.month(meta.sample.months[0], true),
          end: i18n.month(meta.sample.months[meta.sample.months.length - 1], true),
        })}
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <StatTile
          icon={RiFileList2Fill}
          tone="blue"
          label={t("overview.applications")}
          value={i18n.num(kpis.applications_30d)}
          caption={t("overview.vsPrev")}
          delta={signed(i18n.pct(appChange), appChange)}
          deltaTone={deltaTone(appChange, true)}
          direction={direction(appChange)}
        />
        <StatTile
          icon={RiCheckDoubleLine}
          tone="emerald"
          label={t("overview.approvalRate")}
          value={i18n.pct(kpis.approval_rate_30d)}
          caption={t("overview.vsPrev")}
          delta={pp(approvalChange)}
          deltaTone={deltaTone(approvalChange, true)}
          direction={direction(approvalChange)}
        />
        <StatTile
          icon={RiLineChartFill}
          tone="purple"
          label={t("overview.aucOot")}
          value={f3(kpis.auc_oot)}
          caption={t("overview.vsTrain", { value: f3(kpis.auc_train) })}
          delta={signed(f3(aucChange), aucChange)}
          deltaTone={deltaTone(aucChange, true)}
          direction={direction(aucChange)}
        />
        <StatTile
          icon={RiScales3Fill}
          tone="sky"
          label={t("overview.ksOot")}
          value={f3(kpis.ks_oot)}
          caption={t("overview.vsTrain", { value: f3(kpis.ks_train) })}
          delta={signed(f3(ksChange), ksChange)}
          deltaTone={deltaTone(ksChange, true)}
          direction={direction(ksChange)}
        />
        <StatTile
          icon={RiPulseFill}
          tone="orange"
          label={t("overview.scorePsi")}
          value={f3(kpis.score_psi_latest)}
          caption={t("overview.psiCaption", { warn: stability.thresholds.warn, alert: stability.thresholds.alert })}
          delta={t(`alerts.${psiLevel}`)}
          deltaTone={psiLevel === "normal" ? "good" : "bad"}
          direction={psiLevel === "normal" ? "flat" : "up"}
        />
        <StatTile
          icon={RiAlarmWarningFill}
          tone="pink"
          label={t("overview.openAlerts")}
          value={i18n.num(openAlerts)}
          caption={t("overview.alertCaption", { alert: kpis.alerts.alert, warn: kpis.alerts.warn })}
          delta={String(kpis.alerts.alert)}
          deltaTone={kpis.alerts.alert ? "bad" : "good"}
          direction={kpis.alerts.alert ? "up" : "flat"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartPanel
          className="xl:col-span-2"
          title={t("overview.decisionTrend")}
          description={`${t("overview.decisionTrendDesc")} · ${t("overview.perDay", { n: i18n.num(Math.round(decisions.current.total / 30)) })} · ${t("overview.approval")} ${i18n.pct(decisions.current.approval_rate)}`}
          legend={<Legend items={DECISIONS.map((k) => ({ label: t(`overview.${k}`), color: DECISION_COLOR[k] }))} />}
          chart={<DecisionTrendChart daily={decisions.daily} />}
          table={
            <DataTable
              columns={[
                { key: "date", label: t("stability.month") },
                ...DECISIONS.map((k) => ({ key: k, label: t(`overview.${k}`), align: "end" as const })),
                { key: "rate", label: t("overview.approval"), align: "end" },
              ]}
              rows={decisions.daily.map((d) => ({
                key: d.date,
                cells: {
                  date: i18n.date(`${d.date}T00:00:00`, { dateStyle: "medium" }),
                  pass: i18n.num(d.pass),
                  review: i18n.num(d.review),
                  reject: i18n.num(d.reject),
                  rate: i18n.pct(d.approval_rate),
                },
              }))}
            />
          }
        />
        <Panel
          title={t("overview.alerts")}
          description={t("overview.alertsDesc")}
          actions={
            <ButtonLink href="/stability" variant="ghost" size="small" trailingIcon={RiArrowRightSLine}>
              {t("overview.viewStability")}
            </ButtonLink>
          }
        >
          <AlertsList alerts={data.alerts} limit={4} />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <ChartPanel
          className="xl:col-span-3"
          title={t("overview.ruleHits")}
          description={t("overview.ruleHitsDesc")}
          legend={<Legend items={[{ label: t("overview.reject"), color: DECISION_COLOR.reject }, { label: t("overview.review"), color: DECISION_COLOR.review }]} />}
          chart={<RuleHitsChart rules={decisions.rules} />}
          table={
            <DataTable
              columns={[
                { key: "rule", label: t("overview.rule") },
                { key: "decision", label: t("overview.decision") },
                { key: "hits", label: t("overview.hits"), align: "end" },
                { key: "exclusive", label: t("overview.exclusive"), align: "end" },
                { key: "rate", label: t("overview.hitRate"), align: "end" },
              ]}
              rows={decisions.rules.map((r) => ({
                key: r.code,
                cells: {
                  rule: `${r.code} ${i18n.pick(r.label)}`,
                  decision: t(`overview.${r.decision}`),
                  hits: i18n.num(r.hits),
                  exclusive: i18n.num(r.exclusive),
                  rate: i18n.pct(r.hit_rate),
                },
              }))}
            />
          }
        />
        <ChartPanel
          className="xl:col-span-2"
          title={t("overview.effect")}
          description={t("overview.effectDesc")}
          chart={<EffectChart effect={decisions.effect} />}
          table={
            <DataTable
              columns={[
                { key: "decision", label: t("overview.decision") },
                { key: "rate", label: t("overview.badRate"), align: "end" },
              ]}
              rows={DECISIONS.map((k) => ({ key: k, cells: { decision: t(`overview.${k}`), rate: i18n.pct(decisions.effect[k], 2) } }))}
            />
          }
        />
      </div>

      <ChartPanel
        title={t("overview.monthly")}
        description={t("overview.monthlyDesc")}
        controls={
          <MetricSwitch
            label={t("overview.monthly")}
            value={intake}
            onChange={setIntake}
            options={[
              { id: "applications", label: t("overview.applicationsMetric") },
              { id: "bad_rate", label: t("overview.badRateMetric") },
            ]}
          />
        }
        chartClassName="h-[260px]"
        chart={<MonthlyIntakeChart monthly={stability.monthly} metric={intake} />}
        table={
          <DataTable
            columns={[
              { key: "month", label: t("overview.month") },
              { key: "apps", label: t("overview.applicationsMetric"), align: "end" },
              { key: "bad", label: t("overview.badRateMetric"), align: "end" },
              { key: "approval", label: t("overview.approval"), align: "end" },
            ]}
            rows={stability.monthly.map((m) => ({
              key: m.month,
              cells: {
                month: i18n.month(m.month, true),
                apps: i18n.num(m.applications),
                bad: i18n.pct(m.bad_rate, 2),
                approval: i18n.pct(m.approval_rate),
              },
            }))}
          />
        }
      />
    </>
  );
}
