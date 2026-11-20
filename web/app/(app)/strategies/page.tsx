"use client";

import { RiAddLine, RiFlowChart } from "@remixicon/react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { VersionStatusChip } from "@/components/kivi/model-status";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { useStrategies } from "@/lib/queries";
import type { StrategyDetail, StrategyItem, StrategyScene } from "@/lib/types";

const SCENES: StrategyScene[] = ["admission", "fraud", "limit", "pricing", "behavior", "collection", "other"];

function CreateStrategyModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const client = useQueryClient();
  const [scene, setScene] = useState<StrategyScene>("admission");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<StrategyDetail>("/strategies", { body }),
    onSuccess: (strategy) => {
      client.invalidateQueries({ queryKey: ["strategies"] });
      onClose();
      router.push(`/strategies/${strategy.id}/v/${strategy.versions[0].id}`);
    },
    onError: (err) => {
      setError(errorMessage(err, t));
      if (err instanceof ApiError) setInvalid([...err.fields, ...(err.code === "code_taken" ? ["code"] : [])]);
    },
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    create.mutate({
      code: String(form.get("code") ?? ""),
      name: String(form.get("name") ?? ""),
      name_en: String(form.get("name_en") ?? "") || null,
      description: String(form.get("description") ?? ""),
      scene,
    });
  };
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("stg.createTitle")} description={t("stg.createDesc")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <Input name="code" label={t("stg.code")} hint={t("mdl.codeHint")} inputDir="ltr" isRequired isInvalid={invalid.includes("code")} />
          <SelectField label={t("stg.scene")} value={scene} onChange={(v) => setScene(v as StrategyScene)} options={SCENES.map((s) => ({ id: s, label: t(`stg.scenes.${s}`) }))} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input name="name" label={t("stg.name")} isRequired isInvalid={invalid.includes("name")} />
          <Input name="name_en" label={t("stg.nameEn")} />
        </div>
        <Textarea name="description" label={t("stg.description")} rows={2} />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={create.isPending}>{t("stg.create")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function StrategyCard({ strategy }: { strategy: StrategyItem }) {
  const i18n = useI18n();
  const { t } = i18n;
  const online = strategy.online;
  return (
    <Link
      href={`/strategies/${strategy.id}`}
      className="flex min-w-0 flex-col gap-4 rounded-2xl bg-background-secondary-default p-4 outline-none transition-colors hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2lg bg-linear-to-b from-emerald-500 to-emerald-600">
          <RiFlowChart className="size-5 text-white" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="truncate text-headline-medium text-text-primary">{indicatorName(strategy, i18n.locale)}</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{strategy.code}</code>
            <Chip variant="subtle" color="cyan">{t(`stg.scenes.${strategy.scene}`)}</Chip>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 rounded-xl bg-background-primary-default p-3 shadow-card">
        <div className="flex flex-col gap-0.5">
          <span className="text-caption-1-medium text-text-tertiary">{t("stg.online")}</span>
          {online ? <VersionStatusChip status="online" label={`v${online.version}`} /> : <span className="text-caption-1-regular text-text-tertiary">{t("stg.noOnline")}</span>}
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-caption-1-medium text-text-tertiary">{t("stg.rulesTitle")}</span>
          <span className="text-title-3-semibold text-text-primary">{online?.rule_count ?? strategy.latest?.rule_count ?? 0}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-caption-1-medium text-text-tertiary">{t("stg.passRate")}</span>
          <span className="text-title-3-semibold text-text-primary">{i18n.pct(online?.pass_rate ?? null)}</span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption-1-regular text-text-tertiary">
        <span>{t("mdl.versions", { n: strategy.version_count })}</span>
        {strategy.latest && (
          <span className="flex items-center gap-1">
            {t("mdl.latest")} v{strategy.latest.version}
            <VersionStatusChip status={strategy.latest.status} />
          </span>
        )}
        <span className="ms-auto">{strategy.owner?.display_name ?? "—"} · {i18n.date(strategy.updated_at, { dateStyle: "medium" })}</span>
      </div>
    </Link>
  );
}

export default function StrategiesPage() {
  const { t } = useI18n();
  const strategies = useStrategies();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader title={t("stg.title")} subtitle={t("stg.subtitle")} actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("stg.create")}</Button>} />
      {strategies.error ? (
        <ErrorState error={strategies.error} onRetry={() => strategies.refetch()} />
      ) : !strategies.data ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          <Skeleton className="h-[220px]" />
        </div>
      ) : strategies.data.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
          <RiFlowChart className="size-8 text-foreground-icon-tertiary" aria-hidden />
          <p className="text-body-regular text-text-secondary">{t("stg.empty")}</p>
          <Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("stg.create")}</Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {strategies.data.map((s) => (
            <StrategyCard key={s.id} strategy={s} />
          ))}
        </div>
      )}
      <CreateStrategyModal isOpen={creating} onClose={() => setCreating(false)} />
    </>
  );
}
