"use client";

import { RiAlarmWarningLine, RiDeleteBinLine, RiEditLine, RiErrorWarningLine, RiPlayLine } from "@remixicon/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { STATUS_CHIP } from "@/components/kivi/alerts-list";
import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { ApprovalTrendChart, RuleShiftChart, RunHistoryChart } from "@/components/kivi/charts/monitoring";
import { DiscriminationChart, HeatmapScale, PsiBars, PsiHeatmap } from "@/components/kivi/charts/stability";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { MonitorFormModal } from "@/components/kivi/monitor-form";
import { formatThreshold, formatValue, KIND_ICON, levelFor, scheduleText } from "@/components/kivi/monitoring";
import { Notice } from "@/components/kivi/notice";
import { ChartPanel, DataTable, Panel } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { STATUS_COLOR, StatusBadge } from "@/components/kivi/status";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useMe, useMonitor } from "@/lib/queries";
import type { MonitorDetail, MonitorRunDetail } from "@/lib/types";

type I18n = ReturnType<typeof useI18n>;

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="text-caption-1-medium text-text-tertiary">{label}</span>
      <span className="truncate text-body-2-medium text-text-primary">{children}</span>
    </div>
  );
}

function Tile({ label, value, caption }: { label: string; value: string; caption?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-xl bg-background-primary-default p-3 shadow-card">
      <span className="text-caption-1-medium text-text-tertiary">{label}</span>
      <span className="text-title-2-semibold text-text-primary tabular-nums">{value}</span>
      {caption && <span className="text-caption-1-regular text-text-tertiary">{caption}</span>}
    </div>
  );
}

const nameOf = (item: { name: string; name_en?: string | null }, i18n: I18n) => (i18n.locale === "en-US" && item.name_en ? item.name_en : item.name);

function LatestResult({ monitor, run }: { monitor: MonitorDetail; run: MonitorRunDetail }) {
  const i18n = useI18n();
  const { t } = i18n;
  const d = run.detail;
  const th = monitor.thresholds;
  const series = d.series ?? [];
  const f3 = (v: number | null | undefined) => i18n.num(v ?? null, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const period = d.period ? (d.period.includes("/") ? d.period.replace("/", " – ") : i18n.month(d.period, true)) : "—";
  const reference = d.reference ? `${i18n.month(d.reference[0], true)} – ${i18n.month(d.reference[1], true)}` : "—";
  const description = d.reference ? t("mon.latestDesc", { period, reference }) : period;

  if (monitor.kind === "score_psi") {
    return (
      <ChartPanel
        title={t("mon.latest")}
        description={description}
        legend={
          <Legend
            items={(["normal", "warn", "alert"] as const).map((k) => ({ label: t(`alerts.${k}`), color: STATUS_COLOR[k] }))}
          />
        }
        chart={<PsiBars data={series.map((s) => ({ month: s.period, psi: s.value, in_reference: !!s.in_reference, rows: s.rows }))} thresholds={th} />}
        table={
          <DataTable
            columns={[
              { key: "month", label: t("stability.month") },
              { key: "rows", label: t("stability.rows"), align: "end" },
              { key: "psi", label: "PSI", align: "end" },
              { key: "score", label: t("stability.meanScore"), align: "end" },
              { key: "period", label: "" },
            ]}
            rows={series.map((s) => ({
              key: s.period,
              cells: {
                month: i18n.month(s.period, true),
                rows: i18n.num(s.rows ?? 0),
                psi: f3(s.value),
                score: i18n.num(s.mean_score ?? null),
                period: s.in_reference ? t("stability.reference") : t("stability.monitoring"),
              },
            }))}
          />
        }
      />
    );
  }
  if (monitor.kind === "indicator_psi") {
    const months = series.map((s) => s.period);
    const features = (d.indicators ?? []).map((row) => ({ name: row.code, label: { zh: row.name, en: row.name_en ?? row.name }, values: row.values }));
    return (
      <ChartPanel
        title={t("mon.latest")}
        description={`${description}${d.worst ? ` · ${t("mon.worst", { name: nameOf(d.worst, i18n) })}` : ""}${
          d.skipped?.length ? ` · ${t("mon.skipped", { items: d.skipped.map((s) => `${s.code}（${t(`mon.skipReasons.${s.reason}`)}）`).join("、") })}` : ""
        }`}
        legend={<HeatmapScale thresholds={th} />}
        chartClassName="h-auto"
        chart={<PsiHeatmap features={features} months={months} monthly={series.map((s) => ({ in_reference: !!s.in_reference }))} thresholds={th} />}
        table={
          <DataTable
            columns={[{ key: "feature", label: t("stability.feature") }, ...months.map((m) => ({ key: m, label: i18n.month(m), align: "end" as const }))]}
            rows={features.map((row) => ({
              key: row.name,
              cells: Object.fromEntries([["feature", i18n.pick(row.label)], ...months.map((m, i) => [m, f3(row.values[i])])]),
            }))}
          />
        }
      />
    );
  }
  if (monitor.kind === "model_ks") {
    return (
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile label={`KS · ${t("stability.reference")}`} value={f3(d.reference_metrics?.ks)} caption={`AUC ${f3(d.reference_metrics?.auc)} · ${reference}`} />
          <Tile label={`KS · ${period}`} value={f3(d.ks)} caption={`AUC ${f3(d.auc)}`} />
          <Tile label={t("mon.valueLabel.model_ks")} value={formatValue("model_ks", run.value, i18n)} caption={`${t("mon.warn")} ${formatThreshold("model_ks", th.warn, i18n)}`} />
        </div>
        <ChartPanel
          title={t("mon.latest")}
          description={description}
          legend={
            <Legend
              items={[
                { label: "AUC", color: "var(--viz-1)", shape: "line" },
                { label: "KS", color: "var(--viz-2)", shape: "line" },
              ]}
            />
          }
          chartClassName="h-[240px]"
          chart={<DiscriminationChart monthly={series.map((s) => ({ month: s.period, auc: s.auc ?? null, ks: s.ks ?? null, in_reference: !!s.in_reference }))} />}
          table={
            <DataTable
              columns={[
                { key: "month", label: t("stability.month") },
                { key: "labelled", label: t("stability.rows"), align: "end" },
                { key: "auc", label: "AUC", align: "end" },
                { key: "ks", label: "KS", align: "end" },
                { key: "bad", label: t("overview.badRate"), align: "end" },
              ]}
              rows={series.map((s) => ({
                key: s.period,
                cells: { month: i18n.month(s.period, true), labelled: i18n.num(s.labelled ?? 0), auc: f3(s.auc), ks: f3(s.ks), bad: i18n.pct(s.bad_rate ?? null, 2) },
              }))}
            />
          }
        />
      </div>
    );
  }
  if (monitor.kind === "approval_rate") {
    return (
      <div className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <Tile label={`${t("mon.current")} · ${t("overview.approval")}`} value={i18n.pct(d.current?.rate ?? null, 1)} caption={`${period} · ${t("mon.decisions", { n: i18n.num(d.current?.total ?? 0) })}`} />
          <Tile label={`${t("mon.baselineLabel")} · ${t("overview.approval")}`} value={i18n.pct(d.baseline?.rate ?? null, 1)} caption={t("mon.decisions", { n: i18n.num(d.baseline?.total ?? 0) })} />
          <Tile label={t("mon.valueLabel.approval_rate")} value={formatValue("approval_rate", run.value, i18n)} caption={`± ${formatThreshold("approval_rate", th.warn, i18n)} / ± ${formatThreshold("approval_rate", th.alert, i18n)}`} />
        </div>
        <ChartPanel
          title={t("mon.latest")}
          description={`${t("mon.window")} ${d.window_days} · ${t("mon.baseline")} ${d.baseline_days}`}
          legend={<Legend items={[{ label: t("overview.approval"), color: "var(--viz-1)", shape: "line" }, { label: t("mon.baselineLabel"), color: "var(--viz-neutral)", shape: "dash" }]} />}
          chartClassName="h-[240px]"
          chart={<ApprovalTrendChart series={series} facts={d} />}
          table={
            <DataTable
              columns={[
                { key: "date", label: t("dec.time") },
                { key: "rows", label: t("stability.rows"), align: "end" },
                { key: "rate", label: t("overview.approval"), align: "end" },
              ]}
              rows={series.map((s) => ({ key: s.period, cells: { date: i18n.date(`${s.period}T00:00:00`, { dateStyle: "medium" }), rows: i18n.num(s.rows ?? 0), rate: i18n.pct(s.value, 1) } }))}
            />
          }
        />
      </div>
    );
  }
  const rules = d.rules ?? [];
  return (
    <ChartPanel
      title={t("mon.latest")}
      description={`${period} · ${t("mon.decisions", { n: i18n.num(d.current_total ?? 0) })} · ${t("mon.baselineLabel")} ${t("mon.decisions", { n: i18n.num(d.baseline_total ?? 0) })}`}
      legend={<Legend items={(["normal", "warn", "alert"] as const).map((k) => ({ label: t(`alerts.${k}`), color: STATUS_COLOR[k] }))} />}
      chartClassName="h-[300px]"
      chart={<RuleShiftChart rules={rules} thresholds={th} />}
      table={
        <DataTable
          columns={[
            { key: "rule", label: t("overview.rule") },
            { key: "current", label: t("mon.current"), align: "end" },
            { key: "baseline", label: t("mon.baselineLabel"), align: "end" },
            { key: "shift", label: t("mon.shift"), align: "end" },
          ]}
          rows={rules.map((r) => ({
            key: r.code,
            cells: { rule: `${r.code} ${nameOf(r, i18n)}`, current: i18n.pct(r.current, 2), baseline: i18n.pct(r.baseline, 2), shift: formatValue("rule_hit_rate", r.shift, i18n) },
          }))}
        />
      }
    />
  );
}

export default function MonitorPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useMonitor(id);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api<MonitorDetail>(`/monitors/${id}/run`, { method: "POST" }),
    onSuccess: (m) => {
      client.setQueryData(["monitors", id], m);
      client.invalidateQueries({ queryKey: ["monitors"], exact: true });
      client.invalidateQueries({ queryKey: ["alerts"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      client.invalidateQueries({ queryKey: ["stability"] });
      setNotice(t("mon.ran", { level: t(`alerts.${m.runs[0]?.level ?? "normal"}`) }));
    },
  });

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data || !me.data) return <PageSkeleton />;
  const monitor = query.data;
  const Icon = KIND_ICON[monitor.kind];
  const canEdit = me.data.role === "admin" || monitor.owner?.id === me.data.id;
  const lastRun = monitor.runs[0];
  const failed = lastRun?.status === "failed" ? lastRun : null;
  const failedCode = failed?.code ?? undefined;
  const targetHref = monitor.model ? `/models/${monitor.model.id}` : monitor.strategy ? `/strategies/${monitor.strategy.id}` : null;
  const level = levelFor(monitor.kind, monitor.last_value, monitor.thresholds);

  return (
    <>
      <PageHeader
        title={monitor.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 text-body-2-medium text-text-secondary">
              <Icon className="size-4 text-foreground-icon-tertiary" aria-hidden />
              {t(`mon.kinds.${monitor.kind}`)}
            </span>
            {targetHref && (
              <Link href={targetHref} className="font-mono text-body-2-regular text-accent-500 hover:underline">
                {monitor.model?.code ?? monitor.strategy?.code}
              </Link>
            )}
            {monitor.dataset && <span className="text-body-2-regular text-text-tertiary">· {monitor.dataset.name}</span>}
            {!monitor.enabled && <Chip variant="caption" color="neutral">{t("mon.paused")}</Chip>}
          </span>
        }
        actions={
          <>
            {canEdit && (
              <Button variant="secondary" leadingIcon={RiDeleteBinLine} onClick={() => setDeleting(true)}>
                {t("mon.delete")}
              </Button>
            )}
            {canEdit && (
              <Button variant="secondary" leadingIcon={RiEditLine} onClick={() => setEditing(true)}>
                {t("mon.edit")}
              </Button>
            )}
            <Button leadingIcon={RiPlayLine} disabled={run.isPending} onClick={() => run.mutate()}>
              {run.isPending ? t("mon.running") : t("mon.runNow")}
            </Button>
          </>
        }
      />
      <FormError message={run.error ? errorMessage(run.error, t) : null} />

      <section className="grid grid-cols-2 gap-4 rounded-2xl bg-background-secondary-default p-4 sm:grid-cols-3 xl:grid-cols-6">
        <Fact label={t(`mon.valueLabel.${monitor.kind}`)}>
          <span className="flex items-center gap-2">
            <span className="tabular-nums">{formatValue(monitor.kind, monitor.last_value, i18n)}</span>
            {monitor.last_level && <StatusBadge level={monitor.last_level === "error" ? "error" : level} className="bg-background-primary-default" />}
          </span>
        </Fact>
        <Fact label={t("mon.thresholds")}>
          {formatThreshold(monitor.kind, monitor.thresholds.warn, i18n)} / {formatThreshold(monitor.kind, monitor.thresholds.alert, i18n)}
        </Fact>
        <Fact label={t("mon.schedule")}>{scheduleText(monitor.schedule, i18n)}</Fact>
        <Fact label={t("mon.nextRun")}>{monitor.enabled && monitor.next_run_at ? i18n.date(monitor.next_run_at, { dateStyle: "short", timeStyle: "short" }) : "—"}</Fact>
        <Fact label={t("mon.lastRun")}>{monitor.last_run_at ? i18n.date(monitor.last_run_at, { dateStyle: "short", timeStyle: "short" }) : t("mon.never")}</Fact>
        <Fact label={t("mon.owner")}>{monitor.owner?.display_name ?? "—"}</Fact>
      </section>

      {failed && (
        <p className="flex items-start gap-2 rounded-xl bg-status-rose-background px-3 py-2 text-body-2-regular text-status-rose-text">
          <RiErrorWarningLine className="mt-0.5 size-4 shrink-0" aria-hidden />
          {t("mon.failedRun", { error: failedCode && t(`errors.${failedCode}`) !== `errors.${failedCode}` ? t(`errors.${failedCode}`) : (failed.error ?? "") })}
        </p>
      )}
      {monitor.alert && (
        <Link
          href={`/alerts?id=${monitor.alert.id}`}
          className="flex items-center gap-2 rounded-xl bg-status-orange-background px-3 py-2 text-body-2-medium text-status-orange-text hover:underline"
        >
          <RiAlarmWarningLine className="size-4 shrink-0" aria-hidden />
          {t("mon.activeAlert")} #{monitor.alert.id}
          <Chip variant="caption" color={STATUS_CHIP[monitor.alert.status]}>{t(`alr.status.${monitor.alert.status}`)}</Chip>
          <span className="ms-auto">{t("mon.viewAlert")}</span>
        </Link>
      )}

      {monitor.latest ? (
        <LatestResult monitor={monitor} run={monitor.latest} />
      ) : (
        <Panel title={t("mon.latest")}>
          <p className="py-10 text-center text-body-regular text-text-tertiary">{t("mon.noRun")}</p>
        </Panel>
      )}

      <ChartPanel
        title={t("mon.history")}
        description={t("mon.historyDesc")}
        chartClassName="h-[200px]"
        chart={<RunHistoryChart runs={monitor.runs} kind={monitor.kind} thresholds={monitor.thresholds} />}
        table={
          <DataTable
            columns={[
              { key: "time", label: t("mon.time") },
              { key: "trigger", label: t("mon.trigger") },
              { key: "level", label: t("mon.level") },
              { key: "value", label: t("mon.value"), align: "end" },
              { key: "seconds", label: t("mon.seconds"), align: "end" },
            ]}
            rows={monitor.runs.map((r) => ({
              key: String(r.id),
              cells: {
                time: i18n.date(r.created_at, { dateStyle: "short", timeStyle: "medium" }),
                trigger: t(`mon.triggers.${r.trigger}`),
                level: <StatusBadge level={r.level} />,
                value: r.status === "failed" ? (r.error ?? "—") : formatValue(monitor.kind, r.value, i18n),
                seconds: `${i18n.num(r.seconds, { maximumFractionDigits: 2 })} s`,
              },
            }))}
          />
        }
      />

      {editing && (
        <MonitorFormModal
          isOpen
          monitor={monitor}
          onClose={() => setEditing(false)}
          onSaved={(m) => {
            client.setQueryData(["monitors", id], m);
            setEditing(false);
            setNotice(t("settings.saved"));
          }}
        />
      )}
      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("mon.delete")}
        description={t("mon.deleteDesc", { name: monitor.name })}
        confirmLabel={t("mon.delete")}
        onConfirm={async () => {
          await api(`/monitors/${monitor.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["monitors"] });
          client.invalidateQueries({ queryKey: ["alerts"] });
          router.replace("/monitors");
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
