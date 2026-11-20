"use client";

import { RiAlarmWarningLine, RiArrowDownSLine, RiArrowUpSLine, RiCheckLine, RiHandHeartLine } from "@remixicon/react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Pagination } from "@/components/base/pagination/pagination";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Textarea } from "@/components/base/textarea/textarea";
import { STATUS_CHIP } from "@/components/kivi/alerts-list";
import { PageHeader } from "@/components/kivi/app-shell";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { alertText, formatThreshold, formatValue, KIND_ICON } from "@/components/kivi/monitoring";
import { Notice } from "@/components/kivi/notice";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { StatusBadge } from "@/components/kivi/status";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import type { AlertItem, AlertPage } from "@/lib/types";
import { cx } from "@/utils/cx";

const SIZE = 20;
type Filter = "active" | "open" | "acknowledged" | "resolved" | "all";
type Action = "acknowledge" | "resolve";

function ActionModal({ alert, action, onClose, onDone }: { alert: AlertItem; action: Action | null; onClose: () => void; onDone: (a: AlertItem) => void }) {
  const { t } = useI18n();
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api<AlertItem>(`/alerts/${alert.id}/${action}`, { body: { note } }),
    onSuccess: (a) => {
      setNote("");
      setError(null);
      onDone(a);
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  if (!action) return null;
  const resolve = action === "resolve";
  return (
    <Modal isOpen onClose={onClose} title={resolve ? t("alr.resolveTitle") : t("alr.ackTitle")} description={resolve ? t("alr.resolveDesc") : t("alr.ackDesc")}>
      <Textarea label={t("alr.note")} placeholder={t("alr.notePlaceholder")} value={note} onChange={setNote} rows={3} isRequired={resolve} />
      <FormError message={error} />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
        <Button disabled={run.isPending || (resolve && !note.trim())} onClick={() => run.mutate()}>
          {resolve ? t("alr.resolve") : t("alr.acknowledge")}
        </Button>
      </div>
    </Modal>
  );
}

function Timeline({ alert }: { alert: AlertItem }) {
  const i18n = useI18n();
  const { t } = i18n;
  return (
    <ol className="flex flex-col gap-2.5 border-s border-border-button-default ps-4">
      {[...alert.events].reverse().map((e, i) => (
        <li key={i} className="relative flex flex-col">
          <span className="absolute -start-[21px] top-1.5 size-2 rounded-full bg-accent-500" aria-hidden />
          <span className="text-body-2-medium text-text-primary">
            {t(`alr.events.${e.action}`)}
            {e.level && (e.action === "escalated" || e.action === "eased") && <> {t(`alerts.${e.level}`)}</>}
            {e.level && e.action === "opened" && <> · {t(`alerts.${e.level}`)}</>}
            {e.value !== undefined && e.value !== null && <span className="text-text-secondary tabular-nums"> · {formatValue(alert.monitor.kind, e.value, i18n)}</span>}
            {e.actor && <span className="text-text-secondary"> · {e.actor.display_name}</span>}
          </span>
          {e.note && <span className="text-body-2-regular text-text-secondary">{e.note}</span>}
          <span className="text-caption-1-regular text-text-tertiary">{i18n.date(e.at, { dateStyle: "medium", timeStyle: "short" })}</span>
        </li>
      ))}
    </ol>
  );
}

function AlertCard({ alert, expanded, onToggle, onAction }: { alert: AlertItem; expanded: boolean; onToggle: () => void; onAction: (a: Action) => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const Icon = KIND_ICON[alert.monitor.kind];
  const resolved = alert.status === "resolved";
  return (
    <li className={cx("flex flex-col gap-3 rounded-2xl bg-background-primary-default p-4 shadow-card", resolved && "opacity-80")}>
      <div className="flex flex-wrap items-start gap-3">
        <StatusBadge level={alert.level === "alert" ? "alert" : "warn"} className="mt-0.5 bg-background-secondary-default" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-body-medium text-text-primary">{alertText(alert, i18n)}</p>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-caption-1-regular text-text-tertiary">
            <Link href={`/monitors/${alert.monitor.id}`} className="flex items-center gap-1 text-text-secondary hover:underline">
              <Icon className="size-3.5" aria-hidden />
              {alert.monitor.name}
            </Link>
            <span>· #{alert.id}</span>
            <span>· {t("alr.occurrences", { n: alert.occurrences })}</span>
            <span>· {t("alr.lastSeen")} {i18n.date(alert.last_seen_at, { dateStyle: "short", timeStyle: "short" })}</span>
            {alert.assignee && <span>· {t("alr.assignee")} {alert.assignee.display_name}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Chip variant="subtle" color={STATUS_CHIP[alert.status]}>{t(`alr.status.${alert.status}`)}</Chip>
          {alert.status === "open" && (
            <Button size="small" variant="secondary" leadingIcon={RiHandHeartLine} onClick={() => onAction("acknowledge")}>
              {t("alr.acknowledge")}
            </Button>
          )}
          {!resolved && (
            <Button size="small" leadingIcon={RiCheckLine} onClick={() => onAction("resolve")}>
              {t("alr.resolve")}
            </Button>
          )}
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            aria-label={t("alr.timeline")}
            className="flex size-8 items-center justify-center rounded-lg text-foreground-icon-secondary hover:bg-background-secondary-hover"
          >
            {expanded ? <RiArrowUpSLine className="size-5" aria-hidden /> : <RiArrowDownSLine className="size-5" aria-hidden />}
          </button>
        </div>
      </div>
      {expanded && (
        <div className="grid gap-4 rounded-xl bg-background-secondary-default p-3 md:grid-cols-2">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-body-2-regular">
            <dt className="text-text-tertiary">{t("alr.value")}</dt>
            <dd className="text-text-primary tabular-nums">{formatValue(alert.monitor.kind, alert.value, i18n)}</dd>
            <dt className="text-text-tertiary">{t("alr.threshold")}</dt>
            <dd className="text-text-primary tabular-nums">{alert.threshold !== null ? formatThreshold(alert.monitor.kind, alert.threshold, i18n) : "—"}</dd>
            <dt className="text-text-tertiary">{t("alr.peak")}</dt>
            <dd className="text-text-primary">{t(`alerts.${alert.peak_level}`)}</dd>
            <dt className="text-text-tertiary">{t("alr.firstSeen")}</dt>
            <dd className="text-text-primary">{i18n.date(alert.first_seen_at, { dateStyle: "medium", timeStyle: "short" })}</dd>
            {alert.resolved_at && (
              <>
                <dt className="text-text-tertiary">{t("alr.status.resolved")}</dt>
                <dd className="text-text-primary">
                  {alert.resolution === "recovered" ? t("alr.recovered") : t("alr.resolvedBy", { name: alert.resolver?.display_name ?? "—" })} ·{" "}
                  {i18n.date(alert.resolved_at, { dateStyle: "medium", timeStyle: "short" })}
                </dd>
              </>
            )}
            {alert.note && (
              <>
                <dt className="text-text-tertiary">{t("alr.note")}</dt>
                <dd className="text-text-primary">{alert.note}</dd>
              </>
            )}
          </dl>
          <div className="flex flex-col gap-2">
            <span className="text-caption-1-medium text-text-tertiary">{t("alr.timeline")}</span>
            <Timeline alert={alert} />
          </div>
        </div>
      )}
    </li>
  );
}

function AlertsCentre() {
  const i18n = useI18n();
  const { t } = i18n;
  const client = useQueryClient();
  const router = useRouter();
  const search = useSearchParams();
  const focus = search.get("id");
  const [filter, setFilter] = useState<Filter>("active");
  const [level, setLevel] = useState("");
  const [page, setPage] = useState(1);
  const [expanded, setExpanded] = useState<Set<number>>(new Set(focus ? [Number(focus)] : []));
  const [acting, setActing] = useState<{ alert: AlertItem; action: Action } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const params = new URLSearchParams({ page: String(page), size: String(SIZE) });
  if (filter !== "all") params.set("status", filter);
  if (level) params.set("level", level);
  const list = useQuery({
    queryKey: ["alerts", params.toString()],
    queryFn: ({ signal }) => api<AlertPage>(`/alerts?${params}`, { signal }),
    placeholderData: keepPreviousData,
  });
  const focused = useQuery({
    queryKey: ["alerts", "one", focus],
    queryFn: ({ signal }) => api<AlertItem>(`/alerts/${focus}`, { signal }),
    enabled: !!focus,
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  if (list.error) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  const data = list.data;
  const counts = data?.counts;
  const items = data?.items ?? [];
  const pinned = focused.data && !items.some((a) => a.id === focused.data.id) ? focused.data : null;
  const toggle = (id: number) => {
    const next = new Set(expanded);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setExpanded(next);
  };

  return (
    <>
      <PageHeader title={t("alr.title")} subtitle={t("alr.subtitle")} />
      <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
        <div className="flex flex-wrap items-center gap-3">
          <SegmentedControl
            aria-label={t("alr.title")}
            selectedKeys={new Set([filter])}
            onSelectionChange={(keys) => {
              const next = [...keys][0] as Filter | undefined;
              if (next) {
                setFilter(next);
                setPage(1);
              }
            }}
          >
            <SegmentedControlItem id="active">
              {t("alr.active")} · {counts ? i18n.num(counts.open + counts.acknowledged) : "—"}
            </SegmentedControlItem>
            {(["open", "acknowledged", "resolved"] as const).map((s) => (
              <SegmentedControlItem key={s} id={s}>
                {t(`alr.status.${s}`)} · {counts ? i18n.num(counts[s]) : "—"}
              </SegmentedControlItem>
            ))}
            <SegmentedControlItem id="all">{t("alr.all")}</SegmentedControlItem>
          </SegmentedControl>
          <SelectField
            className="w-[140px]"
            size="sm"
            value={level}
            onChange={(v) => {
              setLevel(v);
              setPage(1);
            }}
            options={[{ id: "", label: t("alr.allLevels") }, { id: "alert", label: t("alerts.alert") }, { id: "warn", label: t("alerts.warn") }]}
          />
        </div>
        {!data ? (
          <Skeleton className="h-[320px] rounded-xl" />
        ) : (
          <ul className={cx("flex flex-col gap-3 transition-opacity", list.isFetching && "opacity-60")}>
            {pinned && (
              <AlertCard alert={pinned} expanded={expanded.has(pinned.id)} onToggle={() => toggle(pinned.id)} onAction={(action) => setActing({ alert: pinned, action })} />
            )}
            {items.map((a) => (
              <AlertCard key={a.id} alert={a} expanded={expanded.has(a.id)} onToggle={() => toggle(a.id)} onAction={(action) => setActing({ alert: a, action })} />
            ))}
            {items.length === 0 && !pinned && (
              <li className="flex flex-col items-center gap-2 rounded-xl bg-background-primary-default py-12 text-center">
                <RiAlarmWarningLine className="size-7 text-foreground-icon-tertiary" aria-hidden />
                <span className="text-body-regular text-text-tertiary">{filter === "active" ? t("alerts.none") : t("alr.empty")}</span>
              </li>
            )}
          </ul>
        )}
        {data && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-body-2-regular text-text-tertiary">{t("common.total", { n: i18n.num(data.total) })}</span>
            {data.total > SIZE && <Pagination page={page} totalPages={Math.ceil(data.total / SIZE)} onChange={setPage} />}
          </div>
        )}
      </section>
      {acting && (
        <ActionModal
          alert={acting.alert}
          action={acting.action}
          onClose={() => setActing(null)}
          onDone={(a) => {
            setActing(null);
            client.invalidateQueries({ queryKey: ["alerts"] });
            client.invalidateQueries({ queryKey: ["overview"] });
            client.invalidateQueries({ queryKey: ["monitors"] });
            setNotice(`#${a.id} ${t(`alr.status.${a.status}`)}`);
            if (focus && Number(focus) === a.id && a.status === "resolved") router.replace("/alerts");
          }}
        />
      )}
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}

export default function AlertsPage() {
  return (
    <Suspense>
      <AlertsCentre />
    </Suspense>
  );
}
