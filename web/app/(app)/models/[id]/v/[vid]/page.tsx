"use client";

import {
  RiArrowGoBackLine,
  RiCheckDoubleLine,
  RiCheckLine,
  RiCloseLine,
  RiDeleteBinLine,
  RiLoader4Line,
  RiRocketLine,
  RiSendPlaneLine,
  RiShutDownLine,
  RiSpeedUpLine,
} from "@remixicon/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button, ButtonLink } from "@/components/base/buttons/button";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { BandsChart, KsCurveChart, RocChart, SPLIT_COLOR, SPLIT_ORDER } from "@/components/kivi/charts/models";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { VersionStatusChip } from "@/components/kivi/model-status";
import { Notice } from "@/components/kivi/notice";
import { ChartPanel, DataTable, MetricSwitch, Panel } from "@/components/kivi/panel";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { levelOf, StatusBadge } from "@/components/kivi/status";
import { api, errorMessage } from "@/lib/api";
import { binLabel, bandLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { useDatasets, useMe, useVersion } from "@/lib/queries";
import type { Job, Split, TrainResult, VersionDetail } from "@/lib/types";
import { cx } from "@/utils/cx";

type Action = "submit" | "approve" | "reject" | "online" | "retire";
const PSI = { warn: 0.1, alert: 0.25 };

function SplitCard({ split, result }: { split: Split; result: TrainResult }) {
  const i18n = useI18n();
  const { t } = i18n;
  const e = result.evaluation[split];
  if (!e) return null;
  const f3 = (v: number | null | undefined) => i18n.num(v ?? null, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-body-semibold text-text-primary">
          <span className="h-0.5 w-3.5 rounded-full" style={{ background: SPLIT_COLOR[split] }} aria-hidden />
          {t(`mdl.splits.${split}`)}
        </span>
        <span className="text-caption-1-regular text-text-tertiary">
          {e.period ? `${i18n.month(e.period[0], true)} – ${i18n.month(e.period[1], true)}` : ""}
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div className="flex flex-col">
          <span className="text-caption-1-medium text-text-tertiary">AUC</span>
          <span className="text-display-4-medium text-text-primary">{f3(e.roc?.auc)}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-caption-1-medium text-text-tertiary">KS</span>
          <span className="text-display-4-medium text-text-primary">{f3(e.roc?.ks)}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-caption-1-medium text-text-tertiary">Gini</span>
          <span className="text-display-4-medium text-text-primary">{f3(e.roc?.gini)}</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2lg bg-background-inner-default px-2.5 py-1.5 text-body-2-regular text-text-secondary shadow-card">
        <span>
          {t("mdl.rows", { n: i18n.num(e.rows) })} · {t("indicators.badRate")} {i18n.pct(e.bad_rate, 2)}
        </span>
        {e.psi !== undefined && e.psi !== null && (
          <span className="flex items-center gap-1.5">
            {t("mdl.scorePsi")} {f3(e.psi)}
            <StatusBadge level={levelOf(e.psi, PSI.warn, PSI.alert)} className="bg-background-secondary-default" />
          </span>
        )}
      </div>
    </section>
  );
}

function ReviewModal({ version, action, onClose, onDone }: { version: VersionDetail; action: Action | null; onClose: () => void; onDone: (v: VersionDetail) => void }) {
  const { t } = useI18n();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api<VersionDetail>(`/model-versions/${version.id}/${action}`, { body: { comment } }),
    onSuccess: (v) => {
      setComment("");
      setError(null);
      onDone(v);
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  if (!action) return null;
  return (
    <Modal
      isOpen
      onClose={() => {
        setError(null);
        onClose();
      }}
      title={t("mdl.confirmTitle", { action: t(`mdl.actions.${action}`), version: version.version })}
      description={action === "online" ? t("mdl.onlineHint") : action === "approve" ? t("mdl.fourEyes") : undefined}
    >
      <Textarea label={t("mdl.comment")} placeholder={t("mdl.commentPlaceholder")} value={comment} onChange={setComment} rows={3} />
      <FormError message={error} />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant={action === "reject" || action === "retire" ? "danger" : "primary"} disabled={run.isPending} onClick={() => run.mutate()}>
          {t(`mdl.actions.${action}`)}
        </Button>
      </div>
    </Modal>
  );
}

function ScoreModal({ version, isOpen, onClose }: { version: VersionDetail; isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const client = useQueryClient();
  const datasets = useDatasets();
  const [datasetId, setDatasetId] = useState(version.dataset?.id ?? "");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () => api<Job>(`/model-versions/${version.id}/score`, { body: { dataset_id: datasetId } }),
    onSuccess: (job) => {
      setError(null);
      setJobId(job.id);
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  const job = useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => api<Job>(`/jobs/${jobId}`),
    enabled: Boolean(jobId),
    refetchInterval: (q) => (q.state.data && ["done", "failed"].includes(q.state.data.status) ? false : 1000),
  });
  const done = job.data?.status === "done";
  if (done) client.invalidateQueries({ queryKey: ["datasets"], exact: true });
  const close = () => {
    setJobId(null);
    setError(null);
    onClose();
  };
  return (
    <Modal isOpen={isOpen} onClose={close} title={t("mdl.scoreTitle")} description={t("mdl.scoreDesc", { version: version.version })}>
      <SelectField
        label={t("mdl.scoreDataset")}
        value={datasetId}
        onChange={setDatasetId}
        isDisabled={Boolean(jobId)}
        options={(datasets.data ?? []).filter((d) => d.source !== "score").map((d) => ({ id: d.id, label: d.name }))}
      />
      <FormError message={error ?? (job.data?.status === "failed" ? job.data.error : null)} />
      {jobId && !done && job.data?.status !== "failed" && (
        <p className="flex items-center gap-2 text-body-2-regular text-text-secondary">
          <RiLoader4Line className="size-4 animate-spin" aria-hidden />
          {t("mdl.scoring")}
        </p>
      )}
      {done && (
        <p className="flex items-center gap-2 rounded-xl bg-status-lime-background px-3 py-2 text-body-2-medium text-status-lime-text">
          <RiCheckLine className="size-4" aria-hidden />
          {t("mdl.scored")}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={close}>{t("common.close")}</Button>
        {done ? (
          <ButtonLink href={`/data/${String(job.data?.result.dataset_id)}`}>{t("mdl.openDataset")}</ButtonLink>
        ) : (
          <Button leadingIcon={RiSpeedUpLine} disabled={!datasetId || Boolean(jobId && job.data?.status !== "failed") || start.isPending} onClick={() => start.mutate()}>
            {t("mdl.actions.score")}
          </Button>
        )}
      </div>
    </Modal>
  );
}

function pValue(p: number, i18n: ReturnType<typeof useI18n>): string {
  return p < 0.0001 ? "< 0.0001" : i18n.num(p, { minimumFractionDigits: 4, maximumFractionDigits: 4 });
}

export default function VersionPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id, vid } = useParams<{ id: string; vid: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useVersion(vid);
  const [action, setAction] = useState<Action | null>(null);
  const [scoring, setScoring] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [bandMetric, setBandMetric] = useState<"share" | "bad_rate">("share");
  const [notice, setNotice] = useState<string | null>(null);

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data || !me.data) return <PageSkeleton />;
  const version = query.data;
  const isAdmin = me.data.role === "admin";
  const isAuthor = version.author?.id === me.data.id;
  const name = indicatorName(version.model, i18n.locale);
  const result = "features" in version.result ? (version.result as TrainResult) : null;
  const f3 = (v: number | null | undefined) => i18n.num(v ?? null, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const splits = result ? SPLIT_ORDER.filter((s) => result.evaluation[s]) : [];
  const featureName = (code: string) => {
    const c = result?.selection.candidates.find((x) => x.code === code);
    return c?.name ? indicatorName({ name: c.name, name_en: c.name_en ?? null }, i18n.locale) : code;
  };

  const buttons: { action: Action | "score" | "delete"; icon: typeof RiCheckLine; show: boolean; variant?: "primary" | "secondary" | "danger" }[] = [
    { action: "submit", icon: RiSendPlaneLine, show: version.status === "draft" && (isAuthor || isAdmin) },
    { action: "approve", icon: RiCheckDoubleLine, show: version.status === "in_review" && isAdmin },
    { action: "reject", icon: RiArrowGoBackLine, show: version.status === "in_review" && isAdmin, variant: "secondary" },
    { action: "online", icon: RiRocketLine, show: version.status === "approved" && isAdmin },
    { action: "retire", icon: RiShutDownLine, show: (version.status === "approved" || version.status === "online") && isAdmin, variant: "secondary" },
    { action: "score", icon: RiSpeedUpLine, show: !["training", "failed"].includes(version.status), variant: "secondary" },
    { action: "delete", icon: RiDeleteBinLine, show: ["draft", "failed"].includes(version.status) && (isAuthor || isAdmin), variant: "secondary" },
  ];

  return (
    <>
      <PageHeader
        title={`${name} · v${version.version}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <VersionStatusChip status={version.status} />
            <Link href={`/models/${id}`} className="font-mono text-body-2-regular text-accent-500 hover:underline">{version.model.code}</Link>
            <span>·</span>
            {version.dataset ? <Link href={`/data/${version.dataset.id}`} className="text-accent-500 hover:underline">{version.dataset.name}</Link> : <span>—</span>}
            <span>· {version.author?.display_name} · {i18n.date(version.created_at, { dateStyle: "medium", timeStyle: "short" })}</span>
          </span>
        }
        actions={buttons
          .filter((b) => b.show)
          .map((b) => (
            <Button
              key={b.action}
              variant={b.variant ?? "primary"}
              leadingIcon={b.icon}
              onClick={() => (b.action === "score" ? setScoring(true) : b.action === "delete" ? setDeleting(true) : setAction(b.action))}
            >
              {t(b.action === "delete" ? "mdl.deleteVersion" : `mdl.actions.${b.action}`)}
            </Button>
          ))}
      />
      {version.notes && <p className="mx-1 text-body-regular text-text-secondary">{version.notes}</p>}

      {version.status === "training" && (
        <Panel title={t("mdl.trainingTitle")}>
          <p className="flex items-center gap-2 text-body-regular text-text-secondary">
            <RiLoader4Line className="size-5 animate-spin text-accent-500" aria-hidden />
            {t("mdl.trainingDesc")}
          </p>
        </Panel>
      )}
      {version.status === "failed" && (
        <Panel title={t("mdl.failedTitle")}>
          <FormError message={version.error} />
        </Panel>
      )}

      {result && (
        <>
          {result.notes.length > 0 && (
            <p className="mx-1 rounded-xl bg-status-yellow-background px-3 py-2 text-body-2-regular text-status-yellow-text">
              {result.notes.map((n) => t(`mdl.noteMessages.${n}`)).join("；")}
            </p>
          )}
          <div className={cx("grid gap-4", splits.length === 3 ? "xl:grid-cols-3" : "md:grid-cols-2")}>
            {splits.map((s) => (
              <SplitCard key={s} split={s} result={result} />
            ))}
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <ChartPanel
              title={t("mdl.roc")}
              description={t("mdl.rocDesc")}
              legend={<Legend items={splits.map((s) => ({ label: t(`mdl.splits.${s}`), color: SPLIT_COLOR[s], shape: "line" }))} />}
              chartClassName="h-[300px]"
              chart={<RocChart evaluation={result.evaluation} />}
              table={
                <DataTable
                  columns={[{ key: "fpr", label: "FPR", align: "end" }, ...splits.map((s) => ({ key: s, label: `TPR · ${t(`mdl.splits.${s}`)}`, align: "end" as const }))]}
                  rows={(result.evaluation[splits[0]]?.roc?.curve ?? []).map((p, i) => ({
                    key: i,
                    cells: { fpr: i18n.pct(p.fpr, 1), ...Object.fromEntries(splits.map((s) => [s, i18n.pct(result.evaluation[s]?.roc?.curve[i]?.tpr ?? null)])) },
                  }))}
                />
              }
            />
            <ChartPanel
              title={t("mdl.ks")}
              description={t("mdl.ksDesc", { split: t(`mdl.splits.${result.focus}`) })}
              legend={
                <Legend
                  items={[
                    { label: t("models.cumBad"), color: "var(--viz-1)", shape: "line" },
                    { label: t("models.cumGood"), color: "var(--viz-2)", shape: "line" },
                  ]}
                />
              }
              chartClassName="h-[300px]"
              chart={<KsCurveChart gains={result.gains} />}
              table={
                <DataTable
                  columns={[
                    { key: "decile", label: t("models.decile") },
                    { key: "range", label: t("models.scoreRange") },
                    { key: "count", label: t("models.count"), align: "end" },
                    { key: "rate", label: t("models.badRate"), align: "end" },
                    { key: "ks", label: "KS", align: "end" },
                    { key: "lift", label: t("models.lift"), align: "end" },
                  ]}
                  rows={result.gains.map((g) => ({
                    key: g.decile,
                    cells: { decile: g.decile, range: `${g.min_score}–${g.max_score}`, count: i18n.num(g.count), rate: i18n.pct(g.bad_rate, 2), ks: f3(g.ks), lift: i18n.num(g.lift, { maximumFractionDigits: 2 }) },
                  }))}
                />
              }
            />
          </div>

          <ChartPanel
            title={t("mdl.distribution")}
            description={bandMetric === "share" ? t("mdl.distributionDesc") : t("mdl.distributionBadDesc")}
            controls={
              <MetricSwitch
                label={t("mdl.distribution")}
                value={bandMetric}
                onChange={setBandMetric}
                options={[
                  { id: "share", label: t("models.metricShare") },
                  { id: "bad_rate", label: t("models.metricBadRate") },
                ]}
              />
            }
            legend={<Legend items={splits.map((s) => ({ label: t(`mdl.splits.${s}`), color: SPLIT_COLOR[s] }))} />}
            chart={<BandsChart evaluation={result.evaluation} metric={bandMetric} />}
            table={
              <DataTable
                columns={[{ key: "band", label: t("models.band") }, ...splits.map((s) => ({ key: s, label: t(`mdl.splits.${s}`), align: "end" as const }))]}
                rows={(result.evaluation.train?.bands ?? []).map((b, i) => ({
                  key: b.band,
                  cells: {
                    band: bandLabel(b.lower, b.upper),
                    ...Object.fromEntries(splits.map((s) => [s, i18n.pct(result.evaluation[s]?.bands[i]?.[bandMetric] ?? null, 2)])),
                  },
                }))}
              />
            }
          />

          <Panel
            title={t("mdl.coefficients")}
            description={`${t("mdl.coefficientsDesc")} · ${t("mdl.fit", { r2: f3(result.fit.pseudo_r2), aic: i18n.num(result.fit.aic, { maximumFractionDigits: 0 }) })} · ${t("mdl.intercept")} ${f3(result.intercept)}`}
          >
            <div className="overflow-x-auto rounded-xl bg-background-primary-default">
              <table className="bui-table bui-table-sm">
                <thead>
                  <tr>
                    <th>{t("mdl.variable")}</th>
                    <th className="!text-end">{t("mdl.coefficient")}</th>
                    <th className="!text-end">{t("mdl.pValue")}</th>
                    <th className="!text-end">{t("mdl.vif")}</th>
                    <th className="!text-end">{t("mdl.iv")}</th>
                    {splits.includes("test") && <th>{t("mdl.psiTest")}</th>}
                    {splits.includes("oot") && <th>{t("mdl.psiOot")}</th>}
                  </tr>
                </thead>
                <tbody>
                  {result.features.map((f) => (
                    <tr key={f.code}>
                      <td>
                        <Link href={`/indicators/${f.indicator_id}`} className="flex flex-col hover:underline">
                          <span className="text-body-2-medium text-text-primary">{indicatorName(f, i18n.locale)}</span>
                          <code className="font-mono text-caption-2-regular text-text-tertiary">{f.code}</code>
                        </Link>
                      </td>
                      <td className="text-end">{f3(f.coefficient)}</td>
                      <td className="text-end">{pValue(f.p_value, i18n)}</td>
                      <td className="text-end">{i18n.num(f.vif, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      <td className="text-end">{f3(f.iv)}</td>
                      {(["test", "oot"] as const)
                        .filter((s) => splits.includes(s))
                        .map((s) => (
                          <td key={s}>
                            <span className="flex items-center gap-2 tabular-nums">
                              {f3(f.psi[s])}
                              <StatusBadge level={levelOf(f.psi[s] ?? 0, PSI.warn, PSI.alert)} className="bg-background-secondary-default" />
                            </span>
                          </td>
                        ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title={t("mdl.scorecard")} description={`${t("mdl.scorecardDesc")} · ${t("models.scaleText", { base: result.scale.base_score, odds: result.scale.base_odds, pdo: result.scale.pdo })}`}>
            <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
              {result.features.map((f) => {
                const max = Math.max(...f.bins.map((b) => b.points));
                const min = Math.min(...f.bins.map((b) => b.points));
                return (
                  <div key={f.code} className="flex flex-col gap-2 rounded-xl bg-background-primary-default p-3 shadow-card">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-body-semibold text-text-primary">{indicatorName(f, i18n.locale)}</span>
                      <span className="shrink-0 text-caption-1-medium text-text-tertiary">{t(`ind.methods.${f.spec.method}`)}</span>
                    </div>
                    <ul className="flex flex-col gap-1">
                      {f.bins.map((b) => (
                        <li key={b.code} className="grid grid-cols-[minmax(0,1fr)_96px_36px] items-center gap-2 text-body-2-regular">
                          <span className="truncate text-text-secondary">{binLabel(b, f.unit, i18n)}</span>
                          <span className="h-1.5 rounded-full bg-background-tertiary-default" aria-hidden>
                            <span className="block h-1.5 rounded-full" style={{ width: `${max === min ? 100 : 12 + ((b.points - min) / (max - min)) * 88}%`, background: "var(--viz-1)" }} />
                          </span>
                          <span className="text-end text-body-2-semibold text-text-primary tabular-nums">{b.points}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </Panel>

          <div className="grid gap-4 xl:grid-cols-5">
            <Panel
              className="xl:col-span-3"
              title={t("mdl.selection")}
              description={t("mdl.selectionDesc", { n: result.selection.candidates.length, k: result.features.length })}
            >
              <div className="overflow-x-auto rounded-xl bg-background-primary-default">
                <table className="bui-table bui-table-sm">
                  <thead>
                    <tr>
                      <th>{t("mdl.variable")}</th>
                      <th className="!text-end">{t("mdl.iv")}</th>
                      <th>{t("mdl.status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...result.selection.candidates]
                      .sort((a, b) => Number(b.selected) - Number(a.selected) || (b.iv ?? 0) - (a.iv ?? 0))
                      .map((c) => (
                        <tr key={c.code}>
                          <td>
                            <span className="flex flex-col">
                              <span className="text-body-2-medium text-text-primary">{featureName(c.code)}</span>
                              <code className="font-mono text-caption-2-regular text-text-tertiary">{c.code}</code>
                            </span>
                          </td>
                          <td className="text-end">{f3(c.iv)}</td>
                          <td>
                            {c.selected ? (
                              <Chip variant="subtle" color="lime">{t("mdl.kept")}</Chip>
                            ) : (
                              <span className="flex items-center gap-2">
                                <Chip variant="subtle" color="neutral">
                                  <span className="flex items-center gap-1">
                                    <RiCloseLine className="size-3" aria-hidden />
                                    {t(`mdl.reasons.${c.reason}`)}
                                  </span>
                                </Chip>
                                {c.value !== undefined && c.value !== null && c.reason !== "iv" && c.reason !== "max_features" && (
                                  <span className="text-caption-1-regular text-text-tertiary tabular-nums">
                                    {c.reason === "pvalue" ? `p = ${pValue(c.value, i18n)}` : c.reason === "vif" ? `VIF ${i18n.num(c.value, { maximumFractionDigits: 1 })}` : `β ${f3(c.value)}`}
                                  </span>
                                )}
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <div className="flex min-w-0 flex-col gap-4 xl:col-span-2">
              <Panel title={t("mdl.config")}>
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-body-2-regular">
                  {[
                    [t("mdl.ootMonths"), version.config.train.oot_months || t("mdl.ootNone")],
                    [t("mdl.testRatio"), i18n.pct(version.config.train.test_ratio, 0)],
                    [t("mdl.ivMin"), version.config.train.iv_min],
                    [t("mdl.vifMax"), version.config.train.vif_max],
                    [t("mdl.pMax"), version.config.train.p_max],
                    [t("mdl.maxFeatures"), version.config.train.max_features],
                    [t("mdl.baseScore"), `${version.config.train.base_score} · ${version.config.train.base_odds}:1 · PDO ${version.config.train.pdo}`],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="flex flex-col">
                      <dt className="text-caption-1-medium text-text-tertiary">{label}</dt>
                      <dd className="text-text-primary">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </Panel>
              <Panel title={t("mdl.reviews")}>
                {version.reviews.length === 0 ? (
                  <p className="text-body-2-regular text-text-tertiary">{t("common.noData")}</p>
                ) : (
                  <ol className="flex flex-col gap-3">
                    {version.reviews.map((r, i) => (
                      <li key={i} className="flex gap-3">
                        <span className="mt-1.5 size-2 shrink-0 rounded-full bg-accent-500" aria-hidden />
                        <div className="flex min-w-0 flex-col">
                          <span className="text-body-2-medium text-text-primary">
                            {t(`mdl.reviewActions.${r.action}`)} · {r.actor?.display_name ?? t("common.system")}
                          </span>
                          {r.comment && <span className="text-body-2-regular text-text-secondary">{r.comment}</span>}
                          <span className="text-caption-1-regular text-text-tertiary">{i18n.date(r.created_at)}</span>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </Panel>
            </div>
          </div>
        </>
      )}

      <ReviewModal
        version={version}
        action={action}
        onClose={() => setAction(null)}
        onDone={(v) => {
          const done = action;
          setAction(null);
          client.setQueryData(["versions", v.id], v);
          client.invalidateQueries({ queryKey: ["models"] });
          setNotice(`${t(`mdl.reviewActions.${done}`)} · v${v.version}`);
        }}
      />
      <ScoreModal version={version} isOpen={scoring} onClose={() => setScoring(false)} />
      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("mdl.deleteVersion")}
        description={t("mdl.deleteVersionDesc", { version: version.version })}
        confirmLabel={t("mdl.deleteVersion")}
        onConfirm={async () => {
          await api(`/model-versions/${version.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["models"] });
          router.replace(`/models/${id}`);
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
