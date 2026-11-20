"use client";

import { RiDatabase2Line, RiFileTextLine, RiTimeLine, RiUploadCloud2Line } from "@remixicon/react";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { FileUpload } from "@/components/base/file-upload/file-upload";
import { Input } from "@/components/base/input/input";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { errorMessage, upload } from "@/lib/api";
import { periodText } from "@/lib/datasets";
import { useI18n } from "@/lib/i18n/provider";
import { useDatasets } from "@/lib/queries";
import type { Dataset, DatasetDetail } from "@/lib/types";

function UploadModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [resetKey, setResetKey] = useState(0);

  const close = () => {
    setFile(null);
    setError(null);
    setResetKey((k) => k + 1);
    onClose();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!file) {
      setError(t("data.chooseFile"));
      return;
    }
    const form = new FormData(event.currentTarget);
    form.set("file", file);
    setBusy(true);
    setError(null);
    try {
      const dataset = await upload<DatasetDetail>("/datasets", form);
      await client.invalidateQueries({ queryKey: ["datasets"] });
      close();
      router.push(`/data/${dataset.id}`);
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={close} title={t("data.uploadTitle")} description={t("data.uploadDesc")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="flex flex-col gap-1.5">
          <span className="text-body-medium text-text-secondary">{t("data.file")}</span>
          <FileUpload
            key={resetKey}
            allowedExtensions={["csv", "txt"]}
            maxBytes={20 * 1024 * 1024}
            onUploadComplete={setFile}
            labels={{
              prompt: t("data.dropPrompt"),
              select: t("data.dropSelect"),
              max: t("data.dropMax"),
              uploading: t("data.dropReading"),
              uploaded: t("data.dropReady"),
              unsupported: t("data.dropUnsupported"),
              tooLarge: t("data.dropTooLarge"),
            }}
          />
        </div>
        <Input name="name" label={t("data.name")} placeholder={file ? file.name.replace(/\.[^.]+$/, "") : t("data.namePlaceholder")} />
        <Textarea name="description" label={t("data.description")} rows={2} />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={close}>{t("common.cancel")}</Button>
          <Button type="submit" leadingIcon={RiUploadCloud2Line} disabled={busy || !file}>
            {busy ? t("data.uploading") : t("data.upload")}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <span className="truncate text-caption-1-medium text-text-tertiary">{label}</span>
      <span className="truncate text-body-semibold text-text-primary">{value}</span>
    </div>
  );
}

function DatasetCard({ dataset }: { dataset: Dataset }) {
  const i18n = useI18n();
  const { t } = i18n;
  const period = periodText(dataset, i18n);
  return (
    <Link
      href={`/data/${dataset.id}`}
      className="group flex min-w-0 flex-col gap-4 rounded-2xl bg-background-secondary-default p-4 outline-none transition-[box-shadow,background-color] hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
    >
      <div className="flex items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-2lg bg-linear-to-b from-sky-400 to-sky-500">
          <RiDatabase2Line className="size-5 text-white" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex items-center gap-2">
            <h2 className="truncate text-headline-medium text-text-primary">{dataset.name}</h2>
            {dataset.source === "demo" && <Chip variant="subtle" color="purple">{t("data.demo")}</Chip>}
            {dataset.source === "score" && <Chip variant="subtle" color="orange">{t("data.scoreSource")}</Chip>}
          </div>
          <p className="line-clamp-2 text-body-2-regular text-text-secondary">{dataset.description || dataset.file_name || "—"}</p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 rounded-xl bg-background-primary-default p-3 shadow-card">
        <Stat label={t("data.rows")} value={i18n.num(dataset.row_count)} />
        <Stat label={t("data.columns")} value={i18n.num(dataset.column_count)} />
        <Stat label={t("data.badRate")} value={dataset.bad_rate === null ? t("data.noTarget") : i18n.pct(dataset.bad_rate, 2)} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-caption-1-regular text-text-tertiary">
        <span className="flex items-center gap-1">
          <RiTimeLine className="size-3.5" aria-hidden />
          {period ?? t("data.noDate")}
        </span>
        <span className="flex items-center gap-1">
          <RiFileTextLine className="size-3.5" aria-hidden />
          {dataset.target_column ? `${t("data.target")} ${dataset.target_column}` : t("data.noTarget")}
        </span>
        <span className="ms-auto">
          {dataset.owner?.display_name ?? "—"} · {i18n.date(dataset.created_at, { dateStyle: "medium" })}
        </span>
      </div>
    </Link>
  );
}

export default function DataPage() {
  const { t } = useI18n();
  const datasets = useDatasets();
  const [uploading, setUploading] = useState(false);

  return (
    <>
      <PageHeader
        title={t("data.title")}
        subtitle={t("data.subtitle")}
        actions={<Button leadingIcon={RiUploadCloud2Line} onClick={() => setUploading(true)}>{t("data.upload")}</Button>}
      />
      {datasets.error ? (
        <ErrorState error={datasets.error} onRetry={() => datasets.refetch()} />
      ) : !datasets.data ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          <Skeleton className="h-[220px]" />
          <Skeleton className="h-[220px]" />
        </div>
      ) : datasets.data.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
          <RiDatabase2Line className="size-8 text-foreground-icon-tertiary" aria-hidden />
          <p className="text-body-regular text-text-secondary">{t("data.empty")}</p>
          <Button leadingIcon={RiUploadCloud2Line} onClick={() => setUploading(true)}>{t("data.upload")}</Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {datasets.data.map((dataset) => (
            <DatasetCard key={dataset.id} dataset={dataset} />
          ))}
        </div>
      )}
      <UploadModal isOpen={uploading} onClose={() => setUploading(false)} />
    </>
  );
}
