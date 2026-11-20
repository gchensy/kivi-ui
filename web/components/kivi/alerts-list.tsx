"use client";

import { useI18n } from "@/lib/i18n/provider";
import type { Alert } from "@/lib/types";

import { StatusBadge } from "./status";

export function alertText(alert: Alert, i18n: ReturnType<typeof useI18n>): string {
  const f3 = (v?: number) => i18n.num(v ?? null, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  switch (alert.kind) {
    case "feature_psi":
      return i18n.t("alerts.feature_psi_text", {
        subject: i18n.pick(alert.subject_label),
        value: f3(alert.value),
        threshold: i18n.num(alert.threshold ?? null, { minimumFractionDigits: 2 }),
      });
    case "score_psi":
      return i18n.t("alerts.score_psi_text", {
        value: f3(alert.value),
        threshold: i18n.num(alert.threshold ?? null, { minimumFractionDigits: 2 }),
      });
    case "ks_drop":
      return i18n.t("alerts.ks_drop_text", { train: f3(alert.train), oot: f3(alert.oot), value: i18n.pct(alert.value) });
    case "approval_shift":
      return i18n.t("alerts.approval_shift_text", { current: i18n.pct(alert.current), previous: i18n.pct(alert.previous) });
  }
}

export function AlertsList({ alerts, limit }: { alerts: Alert[]; limit?: number }) {
  const i18n = useI18n();
  const shown = limit ? alerts.slice(0, limit) : alerts;
  if (!shown.length) {
    return <p className="py-6 text-center text-body-regular text-text-tertiary">{i18n.t("alerts.none")}</p>;
  }
  return (
    <ul className="flex flex-col gap-2">
      {shown.map((alert) => (
        <li key={alert.id} className="flex flex-col gap-1.5 rounded-xl bg-background-primary-default p-3 shadow-card">
          <div className="flex items-center justify-between gap-2">
            <span className="text-body-2-medium text-text-secondary">{i18n.t(`alerts.${alert.kind}`)}</span>
            <StatusBadge level={alert.level} className="bg-background-secondary-default" />
          </div>
          <p className="text-body-2-regular text-text-primary">{alertText(alert, i18n)}</p>
          <p className="text-caption-1-regular text-text-tertiary">
            {alert.id}
            {alert.month ? ` · ${i18n.month(alert.month, true)}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}
