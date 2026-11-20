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
import Link from "next/link";

import { ButtonLink } from "@/components/base/buttons/button";
import { AlertsList } from "@/components/kivi/alerts-list";
import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { DECISION_COLOR, DECISIONS, DecisionTrendChart, EffectChart, RuleHitsChart } from "@/components/kivi/charts/overview";
import { formatValue, KIND_ICON, Sparkline, targetText } from "@/components/kivi/monitoring";
import { ChartPanel, DataTable, Panel } from "@/components/kivi/panel";
import { StatTile, type DeltaTone } from "@/components/kivi/stat-tile";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { StatusBadge } from "@/components/kivi/status";
import { signed } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { useOverview } from "@/lib/queries";
import type { MonitorItem } from "@/lib/types";

function deltaTone(change: number, upIsGood: boolean): DeltaTone {
  if (Math.abs(change) < 1e-9) return "neutral";
  return change > 0 === upIsGood ? "good" : "bad";
}
const direction = (change: number) => (change > 0 ? "up" : change < 0 ? "down" : "flat");

function Empty({ text }: { text: string }) {
  return <p className="flex h-full min-h-[160px] items-center justify-center text-body-regular text-text-tertiary">{text}</p>;
}

function MonitorCard({ monitor }: { monitor: MonitorItem }) {
  const i18n = useI18n();
  const Icon = KIND_ICON[monitor.kind];
  const level = monitor.last_level ?? null;
  return (
    <Link
      href={`/monitors/${monitor.id}`}
      className="flex min-w-0 flex-col gap-2 rounded-xl bg-background-primary-default p-3 shadow-card outline-none transition-colors hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 text-body-2-medium text-text-secondary">
          <Icon className="size-4 shrink-0 text-foreground-icon-tertiary" aria-hidden />
          <span className="truncate">{monitor.name}</span>
        </span>
        {level && <StatusBadge level={level} className="bg-background-secondary-default" />}
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="flex min-w-0 flex-col">
          <span className="text-title-3-semibold text-text-primary tabular-nums">{formatValue(monitor.kind, monitor.last_value, i18n)}</span>
          <span className="truncate text-caption-1-regular text-text-tertiary">
            {i18n.t(`mon.valueLabel.${monitor.kind}`)} · {targetText(monitor)}
          </span>
        </div>
        <Sparkline values={monitor.trend} level={level} />
      </div>
    </Link>
  );
}

export default function OverviewPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const query = useOverview();

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return <PageSkeleton />;
  const { decisions, strategy, model, score_psi: psi, alerts, monitors } = query.data;
  const f3 = (v: number | null) => i18n.num(v, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const pp = (v: number) => `${i18n.num(v * 100, { maximumFractionDigits: 1, signDisplay: "exceptZero" })} pp`;
  const { current, previous } = decisions;
  const appChange = previous.total ? (current.total - previous.total) / previous.total : null;
  const approvalChange = current.approval_rate !== null && previous.approval_rate !== null ? current.approval_rate - previous.approval_rate : null;
  const aucChange = model?.auc_focus != null && model.auc_train != null ? model.auc_focus - model.auc_train : null;
  const ksChange = model?.ks_focus != null && model.ks_train != null ? model.ks_focus - model.ks_train : null;
  const split = !model || model.focus === "oot" ? "OOT" : t(`mdl.splits.${model.focus}`);
  const demo = decisions.sources.demo ?? 0;
  const unresolved = alerts.counts.open + alerts.counts.acknowledged;

  return (
    <>
      <PageHeader title={t("overview.title")} subtitle={t("overview.subtitle", { date: i18n.date(`${query.data.as_of}T00:00:00`, { dateStyle: "long" }) })} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        <StatTile
          icon={RiFileList2Fill}
          tone="blue"
          label={t("overview.applications")}
          value={i18n.num(current.total)}
          caption={appChange === null ? t("overview.noPrevious") : demo ? t("overview.sourceNote", { n: i18n.num(demo) }) : t("overview.vsPrev")}
          delta={appChange === null ? undefined : signed(i18n.pct(appChange), appChange)}
          deltaTone={appChange === null ? "neutral" : deltaTone(appChange, true)}
          direction={appChange === null ? "flat" : direction(appChange)}
        />
        <StatTile
          icon={RiCheckDoubleLine}
          tone="emerald"
          label={t("overview.approvalRate")}
          value={i18n.pct(current.approval_rate)}
          caption={approvalChange === null ? t("overview.noPrevious") : t("overview.vsPrev")}
          delta={approvalChange === null ? undefined : pp(approvalChange)}
          deltaTone={approvalChange === null ? "neutral" : deltaTone(approvalChange, true)}
          direction={approvalChange === null ? "flat" : direction(approvalChange)}
        />
        <StatTile
          icon={RiLineChartFill}
          tone="purple"
          label={t("overview.aucFocus", { split })}
          value={model ? f3(model.auc_focus) : "—"}
          caption={model ? t("overview.vsTrain", { value: f3(model.auc_train) }) : t("overview.noModel")}
          delta={aucChange === null ? undefined : signed(f3(aucChange), aucChange)}
          deltaTone={aucChange === null ? "neutral" : deltaTone(aucChange, true)}
          direction={aucChange === null ? "flat" : direction(aucChange)}
        />
        <StatTile
          icon={RiScales3Fill}
          tone="sky"
          label={t("overview.ksFocus", { split })}
          value={model ? f3(model.ks_focus) : "—"}
          caption={model ? t("overview.vsTrain", { value: f3(model.ks_train) }) : t("overview.noModel")}
          delta={ksChange === null ? undefined : signed(f3(ksChange), ksChange)}
          deltaTone={ksChange === null ? "neutral" : deltaTone(ksChange, true)}
          direction={ksChange === null ? "flat" : direction(ksChange)}
        />
        <StatTile
          icon={RiPulseFill}
          tone="orange"
          label={t("overview.scorePsi")}
          value={psi ? f3(psi.value) : "—"}
          caption={
            psi
              ? t("overview.psiCaption", {
                  period: psi.period ? i18n.month(psi.period, true) : "—",
                  warn: i18n.num(psi.thresholds.warn, { minimumFractionDigits: 2 }),
                  alert: i18n.num(psi.thresholds.alert, { minimumFractionDigits: 2 }),
                })
              : t("overview.noPsi")
          }
          delta={psi ? t(`alerts.${psi.level}`) : undefined}
          deltaTone={psi ? (psi.level === "normal" ? "good" : "bad") : "neutral"}
          direction={psi && psi.level !== "normal" ? "up" : "flat"}
        />
        <StatTile
          icon={RiAlarmWarningFill}
          tone="pink"
          label={t("overview.openAlerts")}
          value={i18n.num(unresolved)}
          caption={t("overview.alertCaption", { open: alerts.counts.open, ack: alerts.counts.acknowledged })}
          delta={`${t("alerts.alert")} ${alerts.counts.alert}`}
          deltaTone={alerts.counts.alert ? "bad" : "good"}
          direction={alerts.counts.alert ? "up" : "flat"}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <ChartPanel
          className="xl:col-span-2"
          title={t("overview.decisionTrend")}
          description={`${t("overview.decisionTrendDesc")} · ${t("overview.perDay", { n: i18n.num(Math.round(current.total / 30)) })} · ${t("overview.approval")} ${i18n.pct(current.approval_rate)}`}
          legend={<Legend items={DECISIONS.map((k) => ({ label: t(`overview.${k}`), color: DECISION_COLOR[k] }))} />}
          chart={current.total ? <DecisionTrendChart daily={decisions.daily} /> : <Empty text={t("overview.noDecisions")} />}
          table={
            <DataTable
              columns={[
                { key: "date", label: t("dec.time") },
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
            <ButtonLink href="/alerts" variant="ghost" size="small" trailingIcon={RiArrowRightSLine}>
              {t("overview.viewAlerts")}
            </ButtonLink>
          }
        >
          <AlertsList alerts={alerts.items} limit={4} />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <ChartPanel
          className="xl:col-span-3"
          title={t("overview.ruleHits")}
          description={strategy ? t("overview.ruleHitsDesc", { strategy: strategy.code, version: strategy.version }) : t("overview.noStrategy")}
          legend={
            <Legend
              items={DECISIONS.filter((d) => strategy?.rules.some((r) => r.decision === d)).map((d) => ({ label: t(`overview.${d}`), color: DECISION_COLOR[d] }))}
            />
          }
          chartClassName="h-[300px]"
          chart={strategy && strategy.rules.length ? <RuleHitsChart rules={strategy.rules} /> : <Empty text={t("overview.noStrategy")} />}
          table={
            <DataTable
              columns={[
                { key: "rule", label: t("overview.rule") },
                { key: "decision", label: t("overview.decision") },
                { key: "hits", label: t("overview.hits"), align: "end" },
                { key: "exclusive", label: t("overview.exclusive"), align: "end" },
                { key: "rate", label: t("overview.hitRate"), align: "end" },
              ]}
              rows={(strategy?.rules ?? []).map((r) => ({
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
          description={strategy?.effect ? t("overview.effectDesc", { dataset: strategy.effect_dataset ?? "—" }) : t("overview.noEffect")}
          chart={strategy?.effect ? <EffectChart effect={strategy.effect} /> : <Empty text={t("overview.noEffect")} />}
          table={
            <DataTable
              columns={[
                { key: "decision", label: t("overview.decision") },
                { key: "rate", label: t("overview.badRate"), align: "end" },
              ]}
              rows={DECISIONS.map((k) => ({ key: k, cells: { decision: t(`overview.${k}`), rate: i18n.pct(strategy?.effect?.[k] ?? null, 2) } }))}
            />
          }
        />
      </div>

      <Panel
        title={t("overview.monitors")}
        description={t("overview.monitorsDesc")}
        actions={
          <ButtonLink href="/monitors" variant="ghost" size="small" trailingIcon={RiArrowRightSLine}>
            {t("overview.viewMonitors")}
          </ButtonLink>
        }
      >
        {monitors.length === 0 ? (
          <Empty text={t("overview.noMonitors")} />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
            {monitors.map((m) => (
              <MonitorCard key={m.id} monitor={m} />
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}
