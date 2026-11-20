"use client";

import { RiDeleteBinLine, RiFlaskLine } from "@remixicon/react";
import { useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button, ButtonLink } from "@/components/base/buttons/button";
import { PageHeader } from "@/components/kivi/app-shell";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { VersionStatusChip } from "@/components/kivi/model-status";
import { Panel } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { api } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { useMe, useModel } from "@/lib/queries";

export default function ModelPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useModel(id);
  const [deleting, setDeleting] = useState(false);
  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data || !me.data) return <PageSkeleton />;
  const model = query.data;
  const canDelete = (me.data.role === "admin" || model.owner?.id === me.data.id) && !model.online;
  const f3 = (v: number | null) => i18n.num(v, { minimumFractionDigits: 3, maximumFractionDigits: 3 });

  return (
    <>
      <PageHeader
        title={indicatorName(model, i18n.locale)}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{model.code}</code>
            <Chip variant="subtle" color="purple">{t(`mdl.scenes.${model.scene}`)}</Chip>
            <span>{model.owner?.display_name} · {i18n.date(model.created_at, { dateStyle: "medium" })}</span>
          </span>
        }
        actions={
          <>
            {canDelete && (
              <Button variant="secondary" leadingIcon={RiDeleteBinLine} onClick={() => setDeleting(true)}>
                {t("mdl.deleteModel")}
              </Button>
            )}
            <ButtonLink href={`/models/${model.id}/train`} leadingIcon={RiFlaskLine}>
              {t("mdl.train")}
            </ButtonLink>
          </>
        }
      />
      {model.description && <p className="mx-1 text-body-regular text-text-secondary">{model.description}</p>}

      <Panel title={t("mdl.versionList")} description={t("mdl.versionListDesc")}>
        <div className="overflow-x-auto rounded-xl bg-background-primary-default">
          <table className="bui-table bui-table-sm">
            <thead>
              <tr>
                <th>{t("mdl.version")}</th>
                <th>{t("mdl.status")}</th>
                <th>{t("mdl.dataset")}</th>
                <th className="!text-end">{t("mdl.features")}</th>
                <th className="!text-end">AUC · {t("mdl.splits.test")}</th>
                <th className="!text-end">AUC · OOT</th>
                <th className="!text-end">KS · OOT</th>
                <th>{t("mdl.author")}</th>
              </tr>
            </thead>
            <tbody>
              {model.versions.map((v) => (
                <tr key={v.id} className="cursor-pointer hover:bg-background-secondary-hover" onClick={() => router.push(`/models/${model.id}/v/${v.id}`)}>
                  <td className="text-body-2-semibold text-text-primary">v{v.version}</td>
                  <td>
                    <VersionStatusChip status={v.status} />
                  </td>
                  <td className="max-w-[220px] truncate text-text-secondary">{v.dataset?.name ?? "—"}</td>
                  <td className="text-end">{v.feature_count || "—"}</td>
                  <td className="text-end">{f3(v.auc_test)}</td>
                  <td className="text-end">{f3(v.auc_oot)}</td>
                  <td className="text-end">{f3(v.ks_oot)}</td>
                  <td className="whitespace-nowrap text-text-tertiary">
                    {v.author?.display_name ?? "—"} · {i18n.date(v.created_at, { dateStyle: "short", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
              {model.versions.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-10 text-center text-text-tertiary">{t("common.noData")}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("mdl.deleteModel")}
        description={t("mdl.deleteModelDesc", { name: indicatorName(model, i18n.locale) })}
        confirmLabel={t("mdl.deleteModel")}
        onConfirm={async () => {
          await api(`/models/${model.id}`, { method: "DELETE" });
          client.removeQueries({ queryKey: ["models", model.id] });
          await client.invalidateQueries({ queryKey: ["models"] });
          router.replace("/models");
        }}
      />
    </>
  );
}
