"use client";

import { RiAddLine, RiRadarLine } from "@remixicon/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Switch } from "@/components/base/switch/switch";
import { STATUS_CHIP } from "@/components/kivi/alerts-list";
import { PageHeader } from "@/components/kivi/app-shell";
import { MonitorFormModal } from "@/components/kivi/monitor-form";
import { formatThreshold, formatValue, KIND_ICON, scheduleText, Sparkline, targetText } from "@/components/kivi/monitoring";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { StatusBadge } from "@/components/kivi/status";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useMe, useMonitors } from "@/lib/queries";
import type { MonitorItem } from "@/lib/types";

function EnabledSwitch({ monitor, canEdit }: { monitor: MonitorItem; canEdit: boolean }) {
  const { t } = useI18n();
  const client = useQueryClient();
  const toggle = useMutation({
    mutationFn: (enabled: boolean) => api(`/monitors/${monitor.id}`, { method: "PATCH", body: { enabled } }),
    onSettled: () => client.invalidateQueries({ queryKey: ["monitors"] }),
  });
  return (
    <Switch size="sm" isSelected={toggle.isPending ? toggle.variables : monitor.enabled} isDisabled={!canEdit || toggle.isPending} onChange={(on) => toggle.mutate(on)} aria-label={t("mon.enabled")}>
      <span className="text-caption-1-medium text-text-secondary">{monitor.enabled ? t("mon.enabled") : t("mon.paused")}</span>
    </Switch>
  );
}

export default function MonitorsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const router = useRouter();
  const me = useMe();
  const monitors = useMonitors();
  const [creating, setCreating] = useState(false);
  const isAdmin = me.data?.role === "admin";

  return (
    <>
      <PageHeader title={t("mon.title")} subtitle={t("mon.subtitle")} actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("mon.create")}</Button>} />
      {monitors.error ? (
        <ErrorState error={monitors.error} onRetry={() => monitors.refetch()} />
      ) : !monitors.data ? (
        <Skeleton className="h-[320px]" />
      ) : monitors.data.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
          <RiRadarLine className="size-8 text-foreground-icon-tertiary" aria-hidden />
          <p className="text-body-regular text-text-secondary">{t("mon.empty")}</p>
          <Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("mon.create")}</Button>
        </div>
      ) : (
        <section className="rounded-2xl bg-background-secondary-default p-4">
          <div className="overflow-x-auto rounded-xl bg-background-primary-default">
            <table className="bui-table bui-table-sm">
              <thead>
                <tr>
                  <th>{t("mon.name")}</th>
                  <th>{t("mon.target")}</th>
                  <th>{t("mon.latest")}</th>
                  <th aria-label="trend" />
                  <th>{t("mon.thresholds")}</th>
                  <th>{t("mon.schedule")}</th>
                  <th>{t("mon.enabled")}</th>
                </tr>
              </thead>
              <tbody>
                {monitors.data.map((m) => {
                  const Icon = KIND_ICON[m.kind];
                  const canEdit = isAdmin || m.owner?.id === me.data?.id;
                  return (
                    <tr key={m.id} className="cursor-pointer hover:bg-background-secondary-hover" onClick={() => router.push(`/monitors/${m.id}`)}>
                      <td>
                        <span className="flex items-center gap-2">
                          <Icon className="size-4 shrink-0 text-foreground-icon-tertiary" aria-hidden />
                          <span className="flex min-w-0 flex-col">
                            <Link href={`/monitors/${m.id}`} className="truncate text-body-2-medium text-text-primary hover:underline" onClick={(e) => e.stopPropagation()}>
                              {m.name}
                            </Link>
                            <span className="text-caption-1-regular text-text-tertiary">{t(`mon.kinds.${m.kind}`)}</span>
                          </span>
                        </span>
                      </td>
                      <td className="whitespace-nowrap">
                        <code className="font-mono text-caption-1-medium text-text-secondary">{targetText(m)}</code>
                        {m.dataset && <span className="block max-w-[200px] truncate text-caption-1-regular text-text-tertiary">{m.dataset.name}</span>}
                      </td>
                      <td>
                        <span className="flex items-center gap-2 whitespace-nowrap">
                          <span className="text-body-2-semibold text-text-primary tabular-nums">{formatValue(m.kind, m.last_value, i18n)}</span>
                          {m.last_level && <StatusBadge level={m.last_level} className="bg-background-secondary-default" />}
                          {m.alert && (
                            <Chip variant="caption" color={STATUS_CHIP[m.alert.status]}>
                              #{m.alert.id} {t(`alr.status.${m.alert.status}`)}
                            </Chip>
                          )}
                        </span>
                        <span className="block whitespace-nowrap text-caption-1-regular text-text-tertiary">
                          {t("mon.lastRun")} {m.last_run_at ? i18n.date(m.last_run_at, { dateStyle: "short", timeStyle: "short" }) : t("mon.never")}
                        </span>
                      </td>
                      <td>
                        <Sparkline values={m.trend} level={m.last_level} />
                      </td>
                      <td className="whitespace-nowrap text-text-secondary tabular-nums">
                        {formatThreshold(m.kind, m.thresholds.warn, i18n)} / {formatThreshold(m.kind, m.thresholds.alert, i18n)}
                      </td>
                      <td className="whitespace-nowrap text-text-secondary">
                        {scheduleText(m.schedule, i18n)}
                        {m.enabled && m.next_run_at && (
                          <span className="block text-caption-1-regular text-text-tertiary">
                            {t("mon.nextRun")} {i18n.date(m.next_run_at, { dateStyle: "short", timeStyle: "short" })}
                          </span>
                        )}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <EnabledSwitch monitor={m} canEdit={canEdit} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {creating && <MonitorFormModal isOpen onClose={() => setCreating(false)} onSaved={(m) => router.push(`/monitors/${m.id}`)} />}
    </>
  );
}
