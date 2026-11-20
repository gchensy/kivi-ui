"use client";

import { RiCloseLine, RiSearchLine } from "@remixicon/react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Input } from "@/components/base/input/input";
import { Pagination } from "@/components/base/pagination/pagination";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { PageHeader } from "@/components/kivi/app-shell";
import { DecisionMixBar } from "@/components/kivi/charts/strategies";
import { Modal } from "@/components/kivi/modal";
import { DECISION_CHIP, TraceView } from "@/components/kivi/rules";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useStrategies } from "@/lib/queries";
import type { BacktestSummary, Decision, DecisionDetail, DecisionRow } from "@/lib/types";

const SIZE = 20;
const DECISIONS: Decision[] = ["pass", "review", "reject"];

function firstScore(scores: DecisionRow["scores"]) {
  const entry = Object.entries(scores)[0];
  return entry ? { code: entry[0], ...entry[1] } : null;
}

function DetailModal({ requestId, onClose }: { requestId: string | null; onClose: () => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const detail = useQuery({
    queryKey: ["decisions", "detail", requestId],
    queryFn: ({ signal }) => api<DecisionDetail>(`/decisions/${encodeURIComponent(requestId ?? "")}`, { signal }),
    enabled: !!requestId,
  });
  const d = detail.data;
  return (
    <Modal isOpen={!!requestId} onClose={onClose} title={t("dec.detail")} description={<code className="font-mono">{requestId}</code>} wide>
      {detail.error ? (
        <ErrorState error={detail.error} onRetry={() => detail.refetch()} />
      ) : !d ? (
        <Skeleton className="h-[320px]" />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3 rounded-xl bg-background-secondary-default p-3">
            <Chip variant="bold" color={DECISION_CHIP[d.decision]}>{t(`stg.decisions.${d.decision}`)}</Chip>
            {d.reason && (
              <span className="text-body-2-regular text-text-secondary">
                {t("dec.reason")} <code className="font-mono text-text-primary">{d.reason}</code>
              </span>
            )}
            <span className="font-mono text-body-2-regular text-text-secondary">{d.strategy_code} v{d.version}</span>
            {Object.entries(d.scores).map(([code, s]) => (
              <span key={code} className="text-body-2-regular text-text-secondary">
                {code} <span className="text-body-2-semibold text-text-primary tabular-nums">{s.score}</span> · PD {i18n.pct(s.probability, 1)}
              </span>
            ))}
            <span className="ms-auto text-caption-1-regular text-text-tertiary">
              {t(`dec.sources.${d.source}`)} · {i18n.num(d.latency_ms, { maximumFractionDigits: 1 })} ms · {i18n.date(d.created_at, { dateStyle: "medium", timeStyle: "medium" })}
            </span>
          </div>
          <div className="grid gap-4 md:grid-cols-5">
            <div className="flex min-w-0 flex-col gap-2 md:col-span-2">
              <h3 className="text-body-semibold text-text-primary">{t("dec.input")}</h3>
              {Object.keys(d.input).length === 0 ? (
                <p className="text-body-2-regular text-text-tertiary">{t("common.noData")}</p>
              ) : (
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 rounded-xl bg-background-secondary-default p-3">
                  {Object.entries(d.input).map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="font-mono text-caption-1-medium text-text-tertiary">{key}</dt>
                      <dd className="min-w-0 truncate font-mono text-caption-1-medium text-text-primary">{value === null ? "null" : String(value)}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-2 md:col-span-3">
              <h3 className="text-body-semibold text-text-primary">{t("stg.trace")}</h3>
              {d.trace.length === 0 ? (
                <p className="text-body-2-regular text-text-tertiary">{t("common.noData")}</p>
              ) : (
                <TraceView trace={d.trace} emptyHint={t("dec.noTrace")} />
              )}
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}

export default function DecisionsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const strategies = useStrategies();
  const [strategy, setStrategy] = useState("");
  const [decision, setDecision] = useState<Decision | "">("");
  const [source, setSource] = useState("");
  const [rule, setRule] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<string | null>(null);
  const params = new URLSearchParams({ page: String(page), size: String(SIZE) });
  if (strategy) params.set("strategy", strategy);
  if (decision) params.set("decision", decision);
  if (source) params.set("source", source);
  if (rule) params.set("rule", rule);
  if (search.trim()) params.set("q", search.trim());
  const list = useQuery({
    queryKey: ["decisions", params.toString()],
    queryFn: ({ signal }) => api<{ items: DecisionRow[]; total: number; counts: Record<Decision, number> }>(`/decisions?${params}`, { signal }),
    placeholderData: keepPreviousData,
  });
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setPage(1);
  };
  if (list.error) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  const data = list.data;
  const counts = data?.counts ?? { pass: 0, review: 0, reject: 0 };
  const all = counts.pass + counts.review + counts.reject;
  const mix = {
    ...counts,
    rows: all,
    pass_rate: all ? counts.pass / all : 0,
    review_rate: all ? counts.review / all : 0,
    reject_rate: all ? counts.reject / all : 0,
  } as BacktestSummary;

  return (
    <>
      <PageHeader title={t("dec.title")} subtitle={t("dec.subtitle")} />
      <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
        <div className="flex flex-wrap items-end gap-3">
          <SelectField
            className="w-[220px]"
            size="sm"
            label={t("dec.strategy")}
            value={strategy}
            onChange={reset(setStrategy)}
            options={[{ id: "", label: t("dec.allStrategies") }, ...(strategies.data ?? []).map((s) => ({ id: s.code, label: s.code }))]}
          />
          <SelectField
            className="w-[140px]"
            size="sm"
            label={t("dec.source")}
            value={source}
            onChange={reset(setSource)}
            options={[{ id: "", label: t("dec.all") }, ...(["api", "console", "demo"] as const).map((s) => ({ id: s, label: t(`dec.sources.${s}`) }))]}
          />
          <Input
            aria-label={t("dec.requestId")}
            placeholder={t("dec.searchPlaceholder")}
            leadingIcon={RiSearchLine}
            value={search}
            onChange={reset(setSearch)}
            inputDir="ltr"
            size="small"
            className="w-[240px]"
          />
          {rule && (
            <button
              type="button"
              onClick={() => reset(setRule)("")}
              className="flex h-8 items-center gap-1 rounded-full bg-status-purple-background px-3 text-body-2-medium text-status-purple-text"
            >
              {t("dec.rules")} · <code className="font-mono">{rule}</code>
              <RiCloseLine className="size-4" aria-label={t("common.close")} />
            </button>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <SegmentedControl
            aria-label={t("dec.decision")}
            selectedKeys={new Set([decision || "all"])}
            onSelectionChange={(keys) => {
              const next = [...keys][0] as string | undefined;
              if (next) reset(setDecision)(next === "all" ? "" : (next as Decision));
            }}
          >
            <SegmentedControlItem id="all">{t("dec.all")} · {i18n.num(all)}</SegmentedControlItem>
            {DECISIONS.map((d) => (
              <SegmentedControlItem key={d} id={d}>
                {t(`stg.decisions.${d}`)} · {i18n.num(counts[d])}
              </SegmentedControlItem>
            ))}
          </SegmentedControl>
          {all > 0 && (
            <div className="min-w-[240px] flex-1">
              <DecisionMixBar summary={mix} label="" />
            </div>
          )}
        </div>
        <div className="overflow-x-auto rounded-xl bg-background-primary-default">
          {!data ? (
            <Skeleton className="h-[420px] rounded-xl" />
          ) : (
            <table className={`bui-table bui-table-sm ${list.isFetching ? "opacity-60" : ""} transition-opacity`}>
              <thead>
                <tr>
                  <th>{t("dec.time")}</th>
                  <th>{t("dec.requestId")}</th>
                  <th>{t("dec.strategy")}</th>
                  <th>{t("dec.decision")}</th>
                  <th>{t("dec.rules")}</th>
                  <th className="!text-end">{t("dec.score")}</th>
                  <th className="!text-end">{t("dec.latency")}</th>
                  <th>{t("dec.source")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => {
                  const score = firstScore(row.scores);
                  return (
                    <tr key={row.request_id} className="cursor-pointer hover:bg-background-secondary-hover" onClick={() => setOpen(row.request_id)}>
                      <td className="whitespace-nowrap text-text-secondary tabular-nums">{i18n.date(row.created_at, { dateStyle: "short", timeStyle: "medium" })}</td>
                      <td className="max-w-[200px] truncate font-mono text-caption-1-medium text-text-primary">{row.request_id}</td>
                      <td className="whitespace-nowrap font-mono text-caption-1-medium text-text-secondary">{row.strategy_code} v{row.version}</td>
                      <td>
                        <Chip variant="subtle" color={DECISION_CHIP[row.decision]}>{t(`stg.decisions.${row.decision}`)}</Chip>
                      </td>
                      <td>
                        <span className="flex flex-wrap gap-1">
                          {row.hit_rules.length === 0
                            ? <span className="text-text-tertiary">—</span>
                            : row.hit_rules.map((code) => (
                                <button
                                  key={code}
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    reset(setRule)(code);
                                  }}
                                  className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary hover:bg-background-tertiary-hover"
                                >
                                  {code}
                                </button>
                              ))}
                        </span>
                      </td>
                      <td className="text-end tabular-nums">{score ? score.score : "—"}</td>
                      <td className="text-end text-text-secondary tabular-nums">{i18n.num(row.latency_ms, { maximumFractionDigits: 1 })} ms</td>
                      <td className="text-text-tertiary">{t(`dec.sources.${row.source}`)}</td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={8} className="py-10 text-center text-text-tertiary">{t("common.noData")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {data && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-body-2-regular text-text-tertiary">{t("common.total", { n: i18n.num(data.total) })}</span>
            {data.total > SIZE && <Pagination page={page} totalPages={Math.ceil(data.total / SIZE)} onChange={setPage} />}
          </div>
        )}
      </section>
      <DetailModal requestId={open} onClose={() => setOpen(null)} />
    </>
  );
}
