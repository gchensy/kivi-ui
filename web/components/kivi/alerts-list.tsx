"use client";

import Link from "next/link";

import { Chip } from "@/components/base/badges/chip";
import { useI18n } from "@/lib/i18n/provider";
import type { AlertItem, AlertStatus } from "@/lib/types";

import { alertText } from "./monitoring";
import { StatusBadge } from "./status";

export const STATUS_CHIP: Record<AlertStatus, "orange" | "blue" | "neutral"> = { open: "orange", acknowledged: "blue", resolved: "neutral" };

/** A compact list of alerts: level, what happened, which monitor and where it stands. */
export function AlertsList({ alerts, limit }: { alerts: AlertItem[]; limit?: number }) {
  const i18n = useI18n();
  const shown = limit ? alerts.slice(0, limit) : alerts;
  if (!shown.length) {
    return <p className="py-6 text-center text-body-regular text-text-tertiary">{i18n.t("alerts.none")}</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {shown.map((alert) => (
        <li key={alert.id}>
          <Link
            href={`/alerts?id=${alert.id}`}
            className="flex flex-col gap-1.5 rounded-xl bg-background-primary-default p-3 shadow-card outline-none transition-colors hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-body-2-medium text-text-secondary">{alert.monitor.name}</span>
              <StatusBadge level={alert.level === "alert" ? "alert" : "warn"} className="bg-background-secondary-default" />
            </div>
            <p className="text-body-2-regular text-text-primary">{alertText(alert, i18n)}</p>
            <p className="flex flex-wrap items-center gap-2 text-caption-1-regular text-text-tertiary">
              <Chip variant="caption" color={STATUS_CHIP[alert.status]}>{i18n.t(`alr.status.${alert.status}`)}</Chip>
              <span>#{alert.id}</span>
              <span>· {i18n.date(alert.last_seen_at, { dateStyle: "short", timeStyle: "short" })}</span>
              {alert.assignee && <span>· {alert.assignee.display_name}</span>}
            </p>
          </Link>
        </li>
      ))}
    </ul>
  );
}
