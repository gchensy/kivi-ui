"use client";

import { RiAddLine, RiShieldUserLine } from "@remixicon/react";
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
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName } from "@/lib/indicators";
import { LIST_DIMENSIONS, LIST_KIND_CHIP, LIST_KIND_GRADIENT, LIST_KINDS } from "@/lib/lists";
import { useLists } from "@/lib/queries";
import type { ListKind, RiskList } from "@/lib/types";
import { cx } from "@/utils/cx";

function CreateListModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const client = useQueryClient();
  const [kind, setKind] = useState<ListKind>("black");
  const [dimension, setDimension] = useState("phone");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<RiskList>("/risk-lists", { body }),
    onSuccess: (list) => {
      client.invalidateQueries({ queryKey: ["risk-lists"] });
      onClose();
      router.push(`/lists/${list.id}`);
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
      kind,
      dimension,
    });
  };
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("lst.createTitle")} description={t("lst.createDesc")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Input name="code" label={t("lst.code")} hint={t("mdl.codeHint")} inputDir="ltr" isRequired isInvalid={invalid.includes("code")} />
        <div className="grid grid-cols-2 gap-3">
          <SelectField label={t("lst.kind")} value={kind} onChange={(v) => setKind(v as ListKind)} options={LIST_KINDS.map((k) => ({ id: k, label: t(`lst.kinds.${k}`) }))} />
          <SelectField label={t("lst.dimension")} value={dimension} onChange={setDimension} options={LIST_DIMENSIONS.map((d) => ({ id: d, label: t(`lst.dimensions.${d}`) }))} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Input name="name" label={t("lst.name")} isRequired isInvalid={invalid.includes("name")} />
          <Input name="name_en" label={t("lst.nameEn")} />
        </div>
        <Textarea name="description" label={t("lst.description")} rows={2} />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={create.isPending}>{t("lst.create")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function ListCard({ list }: { list: RiskList }) {
  const i18n = useI18n();
  const { t } = i18n;
  const expired = list.item_count - list.active_count;
  return (
    <Link
      href={`/lists/${list.id}`}
      className="flex min-w-0 flex-col gap-4 rounded-2xl bg-background-secondary-default p-4 outline-none transition-colors hover:bg-background-secondary-hover focus-visible:ring-2 focus-visible:ring-border-focus-ring"
    >
      <div className="flex items-start gap-3">
        <span className={cx("flex size-10 shrink-0 items-center justify-center rounded-2lg bg-linear-to-b", LIST_KIND_GRADIENT[list.kind])}>
          <RiShieldUserLine className="size-5 text-white" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="truncate text-headline-medium text-text-primary">{indicatorName(list, i18n.locale)}</h2>
          <div className="flex flex-wrap items-center gap-1.5">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{list.code}</code>
            <Chip variant="subtle" color={LIST_KIND_CHIP[list.kind]}>{t(`lst.kinds.${list.kind}`)}</Chip>
            <Chip variant="subtle" color="neutral">{t(`lst.dimensions.${list.dimension}`)}</Chip>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 rounded-xl bg-background-primary-default p-3 shadow-card">
        <div className="flex flex-col gap-0.5">
          <span className="text-caption-1-medium text-text-tertiary">{t("lst.items")}</span>
          <span className="text-title-3-semibold text-text-primary">{i18n.num(list.item_count)}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-caption-1-medium text-text-tertiary">{t("lst.activeEntries")}</span>
          <span className="text-title-3-semibold text-text-primary">
            {i18n.num(list.active_count)}
            {expired > 0 && <span className="ms-1.5 text-caption-1-regular text-text-tertiary">−{i18n.num(expired)}</span>}
          </span>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption-1-regular text-text-tertiary">
        <span className="min-w-0 flex-1 truncate">{list.description || "—"}</span>
        <span>{list.owner?.display_name ?? "—"} · {i18n.date(list.updated_at, { dateStyle: "medium" })}</span>
      </div>
    </Link>
  );
}

export default function ListsPage() {
  const { t } = useI18n();
  const lists = useLists();
  const [creating, setCreating] = useState(false);
  return (
    <>
      <PageHeader title={t("lst.title")} subtitle={t("lst.subtitle")} actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("lst.create")}</Button>} />
      {lists.error ? (
        <ErrorState error={lists.error} onRetry={() => lists.refetch()} />
      ) : !lists.data ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          <Skeleton className="h-[200px]" />
          <Skeleton className="h-[200px]" />
        </div>
      ) : lists.data.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl bg-background-secondary-default px-6 py-16 text-center">
          <RiShieldUserLine className="size-8 text-foreground-icon-tertiary" aria-hidden />
          <p className="text-body-regular text-text-secondary">{t("lst.empty")}</p>
          <Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("lst.create")}</Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {lists.data.map((l) => (
            <ListCard key={l.id} list={l} />
          ))}
        </div>
      )}
      <CreateListModal isOpen={creating} onClose={() => setCreating(false)} />
    </>
  );
}
