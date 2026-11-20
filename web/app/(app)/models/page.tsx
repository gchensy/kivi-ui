"use client";

import { RiAddLine, RiStackLine } from "@remixicon/react";
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
import { useModels } from "@/lib/queries";
import type { ModelDetail, RiskModel, Scene } from "@/lib/types";

const SCENES: Scene[] = ["application", "behavior", "collection", "fraud", "other"];

function CreateModelModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const client = useQueryClient();
  const [scene, setScene] = useState<Scene>("application");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<ModelDetail>("/models", { body }),
    onSuccess: (model) => {
      client.invalidateQueries({ queryKey: ["models"] });
      onClose();
      router.push(`/models/${model.id}`);
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
    <Modal isOpen={isOpen} onClose={onClose} title={t("mdl.createTitle")} description={t("mdl.createDesc")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <Input name="code" label={t("mdl.code")} hint={t("mdl.codeHint")} inputDir="ltr" isRequired isInvalid={invalid.includes("code")} />
          <SelectField label={t("mdl.scene")} value={scene} onChange={(v) => setScene(v as Scene)} options={SCENES.map((s) => ({ id: s, label: t(`mdl.scenes.${s}`) }))} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input name="name" label={t("mdl.name")} isRequired isInvalid={invalid.includes("name")} />
          <Input name="name_en" label={t("mdl.nameEn")} />
        </div>
        <Textarea name="description" label={t("mdl.description")} rows={2} />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={create.isPending}>{t("mdl.create")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="truncate text-caption-1-medium text-text-tertiary">{label}</span>
      <span className="text-title-3-semibold text-text-primary tabular-nums">{value}</span>
    </div>
  );
}

function ModelCard({ model }: { model: RiskModel }) {
  const i18n = useI18n();
  const { t } = i18n;
  const online = model.online;
  const f3 = (v: number | null | undefined) => i18n.num(v ?? null, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  return (
    <Link
      href={`/models/${model.id}`}
      className="flex min-w-0 flex-col gap-4 rounded-2xl bg-background-secondary-default p-4 outline-none transition-colors hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2lg bg-linear-to-b from-purple-500 to-purple-600">
          <RiStackLine className="size-5 text-white" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="truncate text-headline-medium text-text-primary">{indicatorName(model, i18n.locale)}</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{model.code}</code>
            <Chip variant="subtle" color="purple">{t(`mdl.scenes.${model.scene}`)}</Chip>
          </div>
        </div>
      </div>
      <div className="flex flex-col gap-3 rounded-xl bg-background-primary-default p-3 shadow-card">
        <div className="flex items-center justify-between gap-2">
          <span className="text-caption-1-medium text-text-tertiary">{t("mdl.online")}</span>
          {online ? <VersionStatusChip status="online" label={`v${online.version}`} /> : <span className="text-caption-1-regular text-text-tertiary">{t("mdl.noOnline")}</span>}
        </div>
        {online && (
          <div className="grid grid-cols-3 gap-3">
            <Metric label="AUC · OOT" value={f3(online.auc_oot ?? online.auc_test)} />
            <Metric label="KS · OOT" value={f3(online.ks_oot ?? online.ks_test)} />
            <Metric label={t("mdl.features")} value={i18n.num(online.feature_count)} />
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption-1-regular text-text-tertiary">
        <span>{t("mdl.versions", { n: model.version_count })}</span>
        {model.latest && (
          <span className="flex items-center gap-1">
            {t("mdl.latest")} v{model.latest.version}
            <VersionStatusChip status={model.latest.status} />
          </span>
        )}
        <span className="ms-auto">{model.owner?.display_name ?? "—"} · {i18n.date(model.updated_at, { dateStyle: "medium" })}</span>
      </div>
    </Link>
  );
}

export default function ModelsPage() {
  const { t } = useI18n();
  const models = useModels();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader title={t("mdl.title")} subtitle={t("mdl.subtitle")} actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("mdl.create")}</Button>} />
      {models.error ? (
        <ErrorState error={models.error} onRetry={() => models.refetch()} />
      ) : !models.data ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          <Skeleton className="h-[230px]" />
          <Skeleton className="h-[230px]" />
        </div>
      ) : models.data.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
          <RiStackLine className="size-8 text-foreground-icon-tertiary" aria-hidden />
          <p className="text-body-regular text-text-secondary">{t("mdl.empty")}</p>
          <Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("mdl.create")}</Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {models.data.map((model) => (
            <ModelCard key={model.id} model={model} />
          ))}
        </div>
      )}
      <CreateModelModal isOpen={creating} onClose={() => setCreating(false)} />
    </>
  );
}
