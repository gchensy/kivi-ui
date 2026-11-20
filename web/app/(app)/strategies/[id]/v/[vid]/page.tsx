"use client";

import {
  RiArrowGoBackLine,
  RiCheckDoubleLine,
  RiDeleteBinLine,
  RiErrorWarningLine,
  RiPlayLine,
  RiRocketLine,
  RiSaveLine,
  RiSendPlaneLine,
  RiShutDownLine,
} from "@remixicon/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Tab, TabList, TabPanel, Tabs } from "@/components/base/tabs/tabs";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { DecisionMixBar, PassRateChart, SwapMatrix } from "@/components/kivi/charts/strategies";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { VersionStatusChip } from "@/components/kivi/model-status";
import { Notice } from "@/components/kivi/notice";
import { Panel } from "@/components/kivi/panel";
import { DECISION_CHIP, RulesEditor, RulesView, TraceView } from "@/components/kivi/rules";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { useDatasets, useFieldOptions, useMe, useStrategy, useStrategyVersion } from "@/lib/queries";
import type { BacktestSummary, Decision, DecisionResult, StrategyDefinition, StrategyVersionDetail } from "@/lib/types";
import { cx } from "@/utils/cx";

type Action = "submit" | "approve" | "reject" | "online" | "retire";
const SAMPLE = {
  phone: "13800001234",
  age: 35,
  monthly_income: 9000,
  debt_ratio: 0.35,
  credit_utilization: 0.42,
  inquiries_6m: 2,
  overdue_24m: 0,
  employment_years: 5,
  loan_amount: 30000,
  loan_term: "12",
  housing: "own",
  education: "bachelor",
  channel: "app",
};

function ReviewModal({ version, action, onClose, onDone }: { version: StrategyVersionDetail; action: Action | null; onClose: () => void; onDone: (v: StrategyVersionDetail) => void }) {
  const { t } = useI18n();
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api<StrategyVersionDetail>(`/strategy-versions/${version.id}/${action}`, { body: { comment } }),
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
      title={t("stg.confirmTitle", { action: t(`stg.actions.${action}`), version: version.version })}
      description={action === "online" ? t("stg.onlineHint") : action === "approve" ? t("mdl.fourEyes") : undefined}
    >
      <Textarea label={t("mdl.comment")} placeholder={t("mdl.commentPlaceholder")} value={comment} onChange={setComment} rows={3} />
      <FormError message={error} />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant={action === "reject" || action === "retire" ? "danger" : "primary"} disabled={run.isPending} onClick={() => run.mutate()}>
          {t(`stg.actions.${action}`)}
        </Button>
      </div>
    </Modal>
  );
}

function RateTile({ label, value, compare, decision }: { label: string; value: number | null | undefined; compare?: number | null; decision?: Decision }) {
  const i18n = useI18n();
  const delta = compare !== undefined && compare !== null && value !== null && value !== undefined ? value - compare : null;
  return (
    <div className="flex flex-col gap-1 rounded-xl bg-background-primary-default p-3 shadow-card">
      <span className="flex items-center gap-1.5 text-caption-1-medium text-text-tertiary">
        {decision && <span className="size-2 rounded-[3px]" style={{ background: `var(--viz-${decision === "pass" ? "good" : decision === "review" ? "warning" : "critical"})` }} aria-hidden />}
        {label}
      </span>
      <span className="text-title-2-semibold text-text-primary">{i18n.pct(value ?? null)}</span>
      {delta !== null && (
        <span className="text-caption-1-medium text-text-secondary tabular-nums">
          {delta > 0 ? "+" : ""}
          {i18n.num(delta * 100, { maximumFractionDigits: 1 })} pp
        </span>
      )}
    </div>
  );
}

function BacktestPanel({ version, onRan }: { version: StrategyVersionDetail; onRan: (v: StrategyVersionDetail) => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const datasets = useDatasets();
  const strategy = useStrategy(version.strategy.id);
  const labelled = (datasets.data ?? []).filter((d) => d.target_column && d.source !== "score");
  const [datasetId, setDatasetId] = useState(version.backtest.dataset?.id ?? "");
  const [compare, setCompare] = useState(version.backtest.compare?.version_id ?? "");
  useEffect(() => {
    if (!datasetId && labelled.length) setDatasetId(labelled.find((d) => d.date_column)?.id ?? labelled[0].id);
  }, [datasetId, labelled]);
  const run = useMutation({
    mutationFn: () => api<StrategyVersionDetail>(`/strategy-versions/${version.id}/backtest`, { body: { dataset_id: datasetId, compare_version_id: compare || null } }),
    onSuccess: onRan,
  });
  const result = version.backtest;
  const s = result.summary;
  const c = result.compare;
  const ruleNames = new Map(version.definition.rules.map((r) => [r.code, r]));
  const others = (strategy.data?.versions ?? []).filter((v) => v.id !== version.id);
  const swapIn = c ? c.swap.filter((x) => x.from !== "pass" && x.to === "pass").reduce((n, x) => n + x.rows, 0) : 0;
  const swapOut = c ? c.swap.filter((x) => x.from === "pass" && x.to !== "pass").reduce((n, x) => n + x.rows, 0) : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField className="w-[280px]" label={t("stg.dataset")} value={datasetId} onChange={setDatasetId} options={labelled.map((d) => ({ id: d.id, label: d.name }))} />
        <SelectField
          className="w-[180px]"
          label={t("stg.compareWith")}
          value={compare}
          onChange={setCompare}
          options={[{ id: "", label: t("stg.noCompare") }, ...others.map((v) => ({ id: v.id, label: `v${v.version} · ${t(`mdl.statuses.${v.status}`)}` }))]}
        />
        <Button leadingIcon={RiPlayLine} disabled={!datasetId || run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? t("stg.running") : t("stg.run")}
        </Button>
        {result.ran_at && (
          <span className="text-body-2-regular text-text-tertiary">
            {t("stg.lastRun", { dataset: result.dataset?.name ?? "", time: i18n.date(result.ran_at), seconds: result.seconds ?? "—" })}
          </span>
        )}
      </div>
      <FormError message={run.error ? errorMessage(run.error, t) : null} />
      {!s ? (
        <p className="rounded-xl bg-background-primary-default py-10 text-center text-body-regular text-text-tertiary">{t("stg.neverRun")}</p>
      ) : (
        <>
          {s.missing_fields.length > 0 && (
            <p className="flex items-start gap-2 rounded-xl bg-status-yellow-background px-3 py-2 text-body-2-regular text-status-yellow-text">
              <RiErrorWarningLine className="mt-0.5 size-4 shrink-0" aria-hidden />
              {t("stg.missingFields", { fields: s.missing_fields.join(", ") })}
            </p>
          )}
          <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
            <RateTile label={t("stg.decisions.pass")} value={s.pass_rate} compare={c?.summary.pass_rate} decision="pass" />
            <RateTile label={t("stg.decisions.review")} value={s.review_rate} compare={c?.summary.review_rate} decision="review" />
            <RateTile label={t("stg.decisions.reject")} value={s.reject_rate} compare={c?.summary.reject_rate} decision="reject" />
            {(["pass", "review", "reject"] as const).map((d) => (
              <RateTile
                key={d}
                label={`${t("stg.badByDecision")} · ${t(`stg.decisions.${d}`)}`}
                value={s.bad_rate_by_decision?.[d]}
                compare={c?.summary.bad_rate_by_decision?.[d]}
              />
            ))}
          </div>
          <Panel title={t("stg.mix")} className="!bg-background-primary-default">
            <div className="flex flex-col gap-3">
              <Legend items={(["pass", "review", "reject"] as const).map((d) => ({ label: t(`stg.decisions.${d}`), color: `var(--viz-${d === "pass" ? "good" : d === "review" ? "warning" : "critical"})` }))} />
              <DecisionMixBar summary={s} label={`v${version.version} · ${i18n.num(s.rows)}`} />
              {c && <DecisionMixBar summary={c.summary} label={`v${c.version}`} />}
            </div>
          </Panel>

          <Panel title={t("stg.ruleStats")} description={t("stg.ruleStatsDesc")}>
            <div className="overflow-x-auto rounded-xl bg-background-primary-default">
              <table className="bui-table bui-table-sm">
                <thead>
                  <tr>
                    <th>{t("dec.rules")}</th>
                    <th className="!text-end">{t("stg.hits")}</th>
                    <th>{t("stg.hitRate")}</th>
                    <th className="!text-end">{t("stg.exclusive")}</th>
                    <th className="!text-end">{t("stg.decisive")}</th>
                    <th className="!text-end">{t("stg.badRate")}</th>
                  </tr>
                </thead>
                <tbody>
                  {s.rules.map((r) => {
                    const rule = ruleNames.get(r.code);
                    const max = Math.max(...s.rules.map((x) => x.hit_rate ?? 0), 0.0001);
                    return (
                      <tr key={r.code} className={r.enabled ? undefined : "opacity-50"}>
                        <td>
                          <span className="flex items-center gap-2">
                            <code className="font-mono text-caption-1-semibold text-text-secondary">{r.code}</code>
                            <span className="truncate text-body-2-medium text-text-primary">{rule ? (i18n.locale === "en-US" && rule.name_en ? rule.name_en : rule.name) : ""}</span>
                            {rule && <Chip variant="subtle" color={DECISION_CHIP[rule.decision]}>{t(`stg.decisions.${rule.decision}`)}</Chip>}
                          </span>
                        </td>
                        <td className="text-end">{i18n.num(r.hits)}</td>
                        <td>
                          <span className="flex items-center gap-2">
                            <span className="h-1.5 w-16 rounded-full bg-background-tertiary-default" aria-hidden>
                              <span className="block h-1.5 rounded-full" style={{ width: `${((r.hit_rate ?? 0) / max) * 100}%`, background: "var(--viz-1)" }} />
                            </span>
                            <span className="tabular-nums">{i18n.pct(r.hit_rate)}</span>
                          </span>
                        </td>
                        <td className="text-end">{i18n.num(r.exclusive)}</td>
                        <td className="text-end">{i18n.num(r.decisive)}</td>
                        <td className="text-end">{i18n.pct(r.bad_rate, 1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>
          <div className="grid gap-4 xl:grid-cols-2">
            {s.monthly && s.monthly.length > 0 && (
              <Panel title={t("stg.monthly")}>
                <div className="flex flex-col gap-2">
                  <Legend
                    items={[
                      { label: `v${version.version}`, color: "var(--viz-1)", shape: "line" },
                      ...(c ? [{ label: `v${c.version}`, color: "var(--viz-2)", shape: "line" as const }] : []),
                    ]}
                  />
                  <div className="h-[240px]">
                    <PassRateChart current={s} compare={c?.summary} currentLabel={`v${version.version}`} compareLabel={c ? `v${c.version}` : undefined} />
                  </div>
                </div>
              </Panel>
            )}
            {c && (
              <Panel title={t("stg.swap")} description={t("stg.swapDesc", { from: c.version })}>
                <div className="flex flex-col gap-3">
                  <SwapMatrix cells={c.swap} />
                  <div className="flex flex-wrap gap-2">
                    <Chip variant="subtle" color="lime">{t("stg.swapIn", { n: i18n.num(swapIn) })}</Chip>
                    <Chip variant="subtle" color="rose">{t("stg.swapOut", { n: i18n.num(swapOut) })}</Chip>
                  </div>
                </div>
              </Panel>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function ConsolePanel({ version }: { version: StrategyVersionDetail }) {
  const i18n = useI18n();
  const { t } = i18n;
  const [text, setText] = useState(JSON.stringify(SAMPLE, null, 2));
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (data: Record<string, unknown>) => api<DecisionResult>(`/strategy-versions/${version.id}/evaluate`, { body: { data } }),
    onError: (err) => setError(errorMessage(err, t)),
  });
  const submit = () => {
    try {
      const data = JSON.parse(text);
      setError(null);
      run.mutate(data);
    } catch {
      setError(t("stg.invalidJson"));
    }
  };
  const r = run.data;
  return (
    <div className="grid gap-4 xl:grid-cols-5">
      <div className="flex flex-col gap-3 xl:col-span-2">
        <p className="text-body-2-regular text-text-tertiary">{t("stg.consoleDesc")}</p>
        <textarea
          className="min-h-[360px] w-full rounded-xl bg-background-primary-default p-3 font-mono text-caption-1-regular text-text-primary shadow-card outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring"
          value={text}
          spellCheck={false}
          onChange={(e) => setText(e.target.value)}
          aria-label="JSON"
        />
        <FormError message={error} />
        <div className="flex gap-2">
          <Button leadingIcon={RiPlayLine} disabled={run.isPending} onClick={submit}>{t("stg.evaluate")}</Button>
          <Button variant="ghost" onClick={() => setText(JSON.stringify(SAMPLE, null, 2))}>{t("stg.fillSample")}</Button>
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-3 xl:col-span-3">
        {r ? (
          <>
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-background-primary-default p-3 shadow-card">
              <span className="text-body-medium text-text-secondary">{t("stg.result")}</span>
              <Chip variant="bold" color={DECISION_CHIP[r.decision]}>{t(`stg.decisions.${r.decision}`)}</Chip>
              {r.reason && <code className="font-mono text-caption-1-medium text-text-secondary">{r.reason}</code>}
              {Object.entries(r.scores).map(([code, s]) => (
                <span key={code} className="text-body-2-regular text-text-secondary">
                  {code} <span className="text-body-2-semibold text-text-primary tabular-nums">{s.score}</span> · PD {i18n.pct(s.probability, 1)}
                </span>
              ))}
              <span className="ms-auto text-caption-1-regular text-text-tertiary">{t("stg.latency", { ms: r.latency_ms })}</span>
            </div>
            {r.missing_fields.length > 0 && (
              <p className="text-caption-1-regular text-text-tertiary">{t("stg.missingFields", { fields: r.missing_fields.join(", ") })}</p>
            )}
            <TraceView trace={r.trace ?? []} />
          </>
        ) : (
          <p className="rounded-xl bg-background-primary-default py-16 text-center text-body-regular text-text-tertiary">{t("stg.consoleDesc")}</p>
        )}
      </div>
    </div>
  );
}

export default function StrategyVersionPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id, vid } = useParams<{ id: string; vid: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useStrategyVersion(vid);
  const version = query.data;
  const options = useFieldOptions(version?.backtest.dataset?.id);
  const [draft, setDraft] = useState<StrategyDefinition | null>(null);
  const [action, setAction] = useState<Action | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState("rules");
  useEffect(() => {
    if (version) setDraft(version.definition);
  }, [version]);

  const save = useMutation({
    mutationFn: (definition: StrategyDefinition) => api<StrategyVersionDetail>(`/strategy-versions/${vid}`, { method: "PUT", body: { definition } }),
    onSuccess: (v) => {
      client.setQueryData(["strategy-versions", vid], v);
      client.invalidateQueries({ queryKey: ["strategies"] });
      setNotice(t("stg.saved"));
    },
  });

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!version || !draft || !me.data) return <PageSkeleton />;
  const isAdmin = me.data.role === "admin";
  const isAuthor = version.author?.id === me.data.id;
  const editable = version.status === "draft" && (isAdmin || isAuthor);
  const dirty = JSON.stringify(draft) !== JSON.stringify(version.definition);
  const update = (v: StrategyVersionDetail) => {
    client.setQueryData(["strategy-versions", vid], v);
    client.invalidateQueries({ queryKey: ["strategies"] });
  };

  const buttons: { action: Action | "delete"; icon: typeof RiSaveLine; show: boolean; variant?: "primary" | "secondary" }[] = [
    { action: "submit", icon: RiSendPlaneLine, show: version.status === "draft" && (isAuthor || isAdmin) && !dirty },
    { action: "approve", icon: RiCheckDoubleLine, show: version.status === "in_review" && isAdmin },
    { action: "reject", icon: RiArrowGoBackLine, show: version.status === "in_review" && isAdmin, variant: "secondary" },
    { action: "online", icon: RiRocketLine, show: version.status === "approved" && isAdmin },
    { action: "retire", icon: RiShutDownLine, show: (version.status === "approved" || version.status === "online") && isAdmin, variant: "secondary" },
    { action: "delete", icon: RiDeleteBinLine, show: version.status === "draft" && (isAuthor || isAdmin), variant: "secondary" },
  ];

  return (
    <>
      <PageHeader
        title={`${indicatorName(version.strategy, i18n.locale)} · v${version.version}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <VersionStatusChip status={version.status} />
            <Link href={`/strategies/${id}`} className="font-mono text-body-2-regular text-accent-500 hover:underline">{version.strategy.code}</Link>
            <span>· {version.author?.display_name} · {i18n.date(version.updated_at, { dateStyle: "medium", timeStyle: "short" })}</span>
          </span>
        }
        actions={buttons
          .filter((b) => b.show)
          .map((b) => (
            <Button key={b.action} variant={b.variant ?? "primary"} leadingIcon={b.icon} onClick={() => (b.action === "delete" ? setDeleting(true) : setAction(b.action))}>
              {t(`stg.actions.${b.action}`)}
            </Button>
          ))}
      />
      {version.notes && <p className="mx-1 text-body-regular text-text-secondary">{version.notes}</p>}

      <section className="flex flex-col gap-4 rounded-2xl bg-background-secondary-default p-4">
        <Tabs selectedKey={tab} onSelectionChange={(k) => setTab(String(k))}>
          <TabList aria-label={version.strategy.code}>
            <Tab id="rules">{t("stg.rulesTitle")} · {version.definition.rules.length}</Tab>
            <Tab id="backtest">{t("stg.backtest")}</Tab>
            <Tab id="console">{t("stg.console")}</Tab>
            <Tab id="reviews">{t("stg.reviews")}</Tab>
          </TabList>
          <TabPanel id="rules" className="flex flex-col gap-3 pt-4">
            <p className="text-body-2-regular text-text-tertiary">{editable ? t("stg.rulesDesc") : t("stg.readOnly")}</p>
            {editable ? (
              <>
                <RulesEditor definition={draft} onChange={setDraft} options={options.data} />
                <FormError message={save.error ? errorMessage(save.error, t) : null} />
                <div className={cx("sticky bottom-0 flex items-center justify-end gap-3 rounded-xl bg-background-secondary-default/90 py-2 backdrop-blur", !dirty && "opacity-70")}>
                  {dirty && <span className="text-body-2-medium text-status-yellow-text">{t("stg.unsaved")}</span>}
                  <Button variant="secondary" disabled={!dirty} onClick={() => setDraft(version.definition)}>{t("common.cancel")}</Button>
                  <Button leadingIcon={RiSaveLine} disabled={!dirty || save.isPending} onClick={() => save.mutate(draft)}>{t("stg.save")}</Button>
                </div>
              </>
            ) : (
              <RulesView definition={version.definition} />
            )}
          </TabPanel>
          <TabPanel id="backtest" className="pt-4">
            <p className="mb-3 text-body-2-regular text-text-tertiary">{t("stg.backtestDesc")}</p>
            <BacktestPanel version={version} onRan={update} />
          </TabPanel>
          <TabPanel id="console" className="pt-4">
            <ConsolePanel version={version} />
          </TabPanel>
          <TabPanel id="reviews" className="pt-4">
            {version.reviews.length === 0 ? (
              <p className="text-body-2-regular text-text-tertiary">{t("common.noData")}</p>
            ) : (
              <ol className="flex flex-col gap-3">
                {version.reviews.map((r, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="mt-1.5 size-2 shrink-0 rounded-full bg-accent-500" aria-hidden />
                    <div className="flex flex-col">
                      <span className="text-body-2-medium text-text-primary">{t(`mdl.reviewActions.${r.action}`)} · {r.actor?.display_name ?? t("common.system")}</span>
                      {r.comment && <span className="text-body-2-regular text-text-secondary">{r.comment}</span>}
                      <span className="text-caption-1-regular text-text-tertiary">{i18n.date(r.created_at)}</span>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </TabPanel>
        </Tabs>
      </section>

      <ReviewModal
        version={version}
        action={action}
        onClose={() => setAction(null)}
        onDone={(v) => {
          const done = action;
          setAction(null);
          update(v);
          setNotice(`${t(`mdl.reviewActions.${done}`)} · v${v.version}`);
        }}
      />
      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("stg.actions.delete")}
        description={t("stg.deleteVersionDesc", { version: version.version })}
        confirmLabel={t("stg.actions.delete")}
        onConfirm={async () => {
          await api(`/strategy-versions/${version.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["strategies"] });
          router.replace(`/strategies/${id}`);
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
