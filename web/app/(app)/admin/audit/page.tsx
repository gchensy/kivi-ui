"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Pagination } from "@/components/base/pagination/pagination";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { PageHeader } from "@/components/kivi/app-shell";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import type { AuditLog, AuditPage } from "@/lib/types";

const SIZE = 20;
type Filter = "" | "auth." | "user." | "dataset.,indicator.,scheme." | "model.,version." | "strategy,list.,token." | "monitor.,alert.";

function describe(log: AuditLog, i18n: ReturnType<typeof useI18n>): string {
  const d = log.detail as {
    username?: string; role?: string; changes?: Record<string, [string, string]>; fields?: string[];
    name?: string; code?: string; scheme?: string; rows?: number; count?: number; iv?: number; version?: number;
  };
  if (d.version !== undefined) return `${d.code ?? ""} v${d.version}`;
  if (d.scheme) return `${d.code ?? ""} · ${d.scheme}${d.iv !== undefined ? ` · IV ${i18n.num(d.iv, { maximumFractionDigits: 3 })}` : ""}`;
  if (d.count !== undefined) return `${d.name ?? ""} · ${d.count}`;
  if (d.rows !== undefined) return `${d.name ?? ""} · ${i18n.num(d.rows)}`;
  if (d.changes) {
    return Object.entries(d.changes)
      .map(([key, [before, after]]) => {
        const label = (v: string) => {
          const text = i18n.t(`users.${v}`);
          return text === `users.${v}` ? v : text;
        };
        return `${i18n.t(`users.${key}`)}: ${label(before)} → ${label(after)}`;
      })
      .join("，");
  }
  if (d.fields) return d.fields.join(", ");
  if (d.role) return i18n.t(`users.${d.role}`);
  return "";
}

export default function AuditPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const [filter, setFilter] = useState<Filter>("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), size: String(SIZE) });
  if (filter) params.set("action", filter);
  const list = useQuery({
    queryKey: ["audit", filter, page],
    queryFn: () => api<AuditPage>(`/audit-logs?${params}`),
    placeholderData: keepPreviousData,
  });
  if (list.error) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;
  const data = list.data;

  return (
    <>
      <PageHeader title={t("audit.title")} subtitle={t("audit.subtitle")} />
      <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
        <SegmentedControl
          aria-label={t("audit.action")}
          selectedKeys={new Set([filter || "all"])}
          onSelectionChange={(keys) => {
            const next = [...keys][0] as string | undefined;
            if (next) {
              setFilter(next === "all" ? "" : (next as Filter));
              setPage(1);
            }
          }}
        >
          <SegmentedControlItem id="all">{t("audit.filterAll")}</SegmentedControlItem>
          <SegmentedControlItem id="auth.">{t("audit.filterAuth")}</SegmentedControlItem>
          <SegmentedControlItem id="user.">{t("audit.filterUser")}</SegmentedControlItem>
          <SegmentedControlItem id="dataset.,indicator.,scheme.">{t("audit.filterData")}</SegmentedControlItem>
          <SegmentedControlItem id="model.,version.">{t("audit.filterModel")}</SegmentedControlItem>
          <SegmentedControlItem id="strategy,list.,token.">{t("audit.filterStrategy")}</SegmentedControlItem>
          <SegmentedControlItem id="monitor.,alert.">{t("audit.filterMonitor")}</SegmentedControlItem>
        </SegmentedControl>
        <div className="overflow-x-auto rounded-xl bg-background-primary-default">
          {!data ? (
            <Skeleton className="h-[420px] rounded-xl" />
          ) : (
            <table className={`bui-table bui-table-sm ${list.isFetching ? "opacity-60" : ""} transition-opacity`}>
              <thead>
                <tr>
                  <th>{t("audit.time")}</th>
                  <th>{t("audit.actor")}</th>
                  <th>{t("audit.action")}</th>
                  <th>{t("audit.target")}</th>
                  <th>{t("audit.detail")}</th>
                  <th>{t("audit.ip")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((log) => {
                  const failed = log.action.endsWith("failed");
                  const detail = log.detail as { username?: string; name?: string; code?: string };
                  const target = detail.username ?? detail.code ?? detail.name;
                  return (
                    <tr key={log.id}>
                      <td className="whitespace-nowrap text-text-secondary tabular-nums">{i18n.date(log.created_at, { dateStyle: "short", timeStyle: "medium" })}</td>
                      <td>{log.actor ? `${log.actor.display_name} (${log.actor.username})` : t("common.system")}</td>
                      <td>
                        <Chip variant="subtle" color={failed ? "rose" : log.action.startsWith("auth.") ? "blue" : "purple"}>
                          {t(`audit.actions.${log.action}`)}
                        </Chip>
                      </td>
                      <td className="text-text-secondary">{target ?? (log.entity_type === "user" && log.actor ? log.actor.username : log.entity_id ?? "—")}</td>
                      <td className="max-w-[320px] truncate text-text-secondary">{describe(log, i18n) || "—"}</td>
                      <td className="font-mono text-caption-1-regular text-text-tertiary">{log.ip ?? "—"}</td>
                    </tr>
                  );
                })}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-10 text-center text-text-tertiary">{t("common.noData")}</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {data && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-body-2-regular text-text-tertiary">{t("common.total", { n: data.total })}</span>
            {data.total > SIZE && <Pagination page={page} totalPages={Math.ceil(data.total / SIZE)} onChange={setPage} />}
          </div>
        )}
      </section>
    </>
  );
}
