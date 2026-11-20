"use client";

import { RiAddLine, RiDeleteBinLine } from "@remixicon/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { PageHeader } from "@/components/kivi/app-shell";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { VersionStatusChip } from "@/components/kivi/model-status";
import { Panel } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { useMe, useStrategy } from "@/lib/queries";
import type { StrategyVersionDetail } from "@/lib/types";

export default function StrategyPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useStrategy(id);
  const [deleting, setDeleting] = useState(false);
  const create = useMutation({
    mutationFn: () => api<StrategyVersionDetail>(`/strategies/${id}/versions`, { body: { notes: "" } }),
    onSuccess: (v) => {
      client.invalidateQueries({ queryKey: ["strategies"] });
      router.push(`/strategies/${id}/v/${v.id}`);
    },
  });
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data || !me.data) return <PageSkeleton />;
  const strategy = query.data;
  const canDelete = (me.data.role === "admin" || strategy.owner?.id === me.data.id) && !strategy.online;

  return (
    <>
      <PageHeader
        title={indicatorName(strategy, i18n.locale)}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{strategy.code}</code>
            <Chip variant="subtle" color="cyan">{t(`stg.scenes.${strategy.scene}`)}</Chip>
            <span>{strategy.owner?.display_name} · {i18n.date(strategy.created_at, { dateStyle: "medium" })}</span>
          </span>
        }
        actions={
          <>
            {canDelete && (
              <Button variant="secondary" leadingIcon={RiDeleteBinLine} onClick={() => setDeleting(true)}>
                {t("stg.deleteStrategy")}
              </Button>
            )}
            <Button leadingIcon={RiAddLine} disabled={create.isPending} onClick={() => create.mutate()} title={t("stg.newVersionHint")}>
              {t("stg.newVersion")}
            </Button>
          </>
        }
      />
      {strategy.description && <p className="mx-1 text-body-regular text-text-secondary">{strategy.description}</p>}
      <p className="mx-1 rounded-xl bg-status-blue-background px-3 py-2 font-mono text-body-2-regular text-status-blue-text">
        {t("stg.apiHint", { code: strategy.code })}
      </p>
      <FormError message={create.error ? errorMessage(create.error, t) : null} />

      <Panel title={t("stg.versions")} description={t("stg.versionsDesc")}>
        <div className="overflow-x-auto rounded-xl bg-background-primary-default">
          <table className="bui-table bui-table-sm">
            <thead>
              <tr>
                <th>{t("mdl.version")}</th>
                <th>{t("mdl.status")}</th>
                <th className="!text-end">{t("stg.rulesTitle")}</th>
                <th className="!text-end">{t("stg.passRate")}</th>
                <th>{t("mdl.notes")}</th>
                <th>{t("mdl.author")}</th>
              </tr>
            </thead>
            <tbody>
              {strategy.versions.map((v) => (
                <tr key={v.id} className="cursor-pointer hover:bg-background-secondary-hover" onClick={() => router.push(`/strategies/${id}/v/${v.id}`)}>
                  <td className="text-body-2-semibold text-text-primary">v{v.version}</td>
                  <td>
                    <VersionStatusChip status={v.status} />
                  </td>
                  <td className="text-end">{v.rule_count}</td>
                  <td className="text-end">{i18n.pct(v.pass_rate)}</td>
                  <td className="max-w-[320px] truncate text-text-secondary">{v.notes || "—"}</td>
                  <td className="whitespace-nowrap text-text-tertiary">
                    {v.author?.display_name ?? "—"} · {i18n.date(v.updated_at, { dateStyle: "short", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("stg.deleteStrategy")}
        description={t("stg.deleteStrategyDesc", { name: indicatorName(strategy, i18n.locale) })}
        confirmLabel={t("stg.deleteStrategy")}
        onConfirm={async () => {
          await api(`/strategies/${strategy.id}`, { method: "DELETE" });
          await client.invalidateQueries({ queryKey: ["strategies"] });
          router.replace("/strategies");
        }}
      />
    </>
  );
}
