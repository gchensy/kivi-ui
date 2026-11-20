"use client";

import { RiAddLine, RiSearchLine } from "@remixicon/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { IvRankingChart } from "@/components/kivi/charts/indicators";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { ChartPanel, DataTable } from "@/components/kivi/panel";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, Skeleton } from "@/components/kivi/states";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { CATEGORIES, indicatorName, ivLevel as levelOf, LEVEL_CHIP } from "@/lib/indicators";
import { useDatasets, useIndicators } from "@/lib/queries";
import type { DatasetDetail, IndicatorCategory, IndicatorDetail, IndicatorItem, IndicatorStatus } from "@/lib/types";

const STATUSES: IndicatorStatus[] = ["draft", "published", "retired"];
const STATUS_CHIP = { draft: "yellow", published: "lime", retired: "neutral" } as const;

function CreateModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { t } = useI18n();
  const router = useRouter();
  const client = useQueryClient();
  const datasets = useDatasets();
  const [datasetId, setDatasetId] = useState<string>("");
  const [column, setColumn] = useState<string>("");
  const [code, setCode] = useState("");
  const [category, setCategory] = useState<IndicatorCategory>("other");
  const [unit, setUnit] = useState<string>("none");
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);
  const detail = useQuery({
    queryKey: ["datasets", datasetId],
    queryFn: () => api<DatasetDetail>(`/datasets/${datasetId}`),
    enabled: Boolean(datasetId),
  });
  const features = (detail.data?.columns ?? []).filter((c) => c.role === "feature" && (c.dtype === "numeric" || c.dtype === "category"));
  const create = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<IndicatorDetail>("/indicators", { body }),
    onSuccess: (indicator) => {
      client.invalidateQueries({ queryKey: ["indicators"] });
      onClose();
      router.push(`/indicators/${indicator.id}`);
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
      dataset_id: datasetId,
      column,
      code,
      name: String(form.get("name") ?? ""),
      name_en: String(form.get("name_en") ?? "") || null,
      description: String(form.get("description") ?? ""),
      category,
      unit: unit === "none" ? null : unit,
      status: "draft",
    });
  };
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("ind.createTitle")} description={t("ind.createDesc")}>
      <form onSubmit={submit} className="flex max-h-[70vh] flex-col gap-4 overflow-y-auto pe-1" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <SelectField
            label={t("ind.dataset")}
            value={datasetId}
            onChange={(v) => {
              setDatasetId(v);
              setColumn("");
            }}
            options={(datasets.data ?? []).map((d) => ({ id: d.id, label: d.name }))}
          />
          <SelectField
            label={t("ind.column")}
            value={column}
            onChange={(v) => {
              setColumn(v);
              if (!code) setCode(/^[a-z]/.test(v) ? v : `x_${v}`);
            }}
            options={features.map((c) => ({ id: c.column_name, label: c.name }))}
            isDisabled={!features.length}
          />
        </div>
        <Input label={t("ind.code")} hint={t("ind.codeHint")} value={code} onChange={setCode} inputDir="ltr" isRequired isInvalid={invalid.includes("code")} />
        <div className="grid grid-cols-2 gap-3">
          <Input name="name" label={t("ind.name")} isRequired isInvalid={invalid.includes("name")} />
          <Input name="name_en" label={t("ind.nameEn")} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField label={t("ind.category")} value={category} onChange={(v) => setCategory(v as IndicatorCategory)} options={CATEGORIES.map((c) => ({ id: c, label: t(`ind.categories.${c}`) }))} />
          <SelectField label={t("ind.unit")} value={unit} onChange={setUnit} options={["none", "count", "ratio", "cny", "years"].map((u) => ({ id: u, label: t(`ind.units.${u}`) }))} />
        </div>
        <Textarea name="description" label={t("ind.description")} rows={2} />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={create.isPending || !datasetId || !column || !code}>{t("ind.create")}</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function IndicatorsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const router = useRouter();
  const [category, setCategory] = useState<string>("all");
  const [status, setStatus] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setQ(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  const params = useMemo(() => {
    const p = new URLSearchParams();
    if (category !== "all") p.set("category", category);
    if (status !== "all") p.set("status", status);
    if (q) p.set("q", q);
    return p;
  }, [category, status, q]);
  const list = useIndicators(params);
  const data = list.data;
  const counts = data?.counts ?? {};
  const total = Object.values(counts).reduce((a, b) => a + (b ?? 0), 0);
  const name = (item: IndicatorItem) => indicatorName(item, i18n.locale);
  const ranked = (data?.items ?? []).filter((i) => i.default_scheme).slice(0, 16);

  return (
    <>
      <PageHeader title={t("ind.title")} subtitle={t("ind.subtitle")} actions={<Button leadingIcon={RiAddLine} onClick={() => setCreating(true)}>{t("ind.create")}</Button>} />
      <div className="flex flex-wrap items-center justify-between gap-3 px-1">
        <SegmentedControl aria-label={t("ind.category")} selectedKeys={new Set([category])} onSelectionChange={(keys) => setCategory(String([...keys][0] ?? "all"))}>
          <SegmentedControlItem id="all">
            <span className="flex items-center gap-1.5">
              {t("ind.all")}
              <span className="text-caption-1-medium text-text-tertiary tabular-nums">{total}</span>
            </span>
          </SegmentedControlItem>
          {CATEGORIES.filter((c) => counts[c]).map((c) => (
            <SegmentedControlItem key={c} id={c}>
              <span className="flex items-center gap-1.5">
                {t(`ind.categories.${c}`)}
                <span className="text-caption-1-medium text-text-tertiary tabular-nums">{counts[c]}</span>
              </span>
            </SegmentedControlItem>
          ))}
        </SegmentedControl>
        <div className="flex items-center gap-2">
          <SelectField
            className="w-[140px]"
            size="sm"
            value={status}
            onChange={setStatus}
            options={[{ id: "all", label: t("ind.allStatus") }, ...STATUSES.map((s) => ({ id: s, label: t(`ind.statuses.${s}`) }))]}
          />
          <Input aria-label={t("common.search")} placeholder={t("ind.searchPlaceholder")} leadingIcon={RiSearchLine} value={search} onChange={setSearch} size="small" className="w-[220px]" />
        </div>
      </div>

      {list.error ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !data ? (
        <Skeleton className="h-[480px]" />
      ) : data.items.length === 0 ? (
        <p className="rounded-2xl bg-background-secondary-default py-16 text-center text-body-regular text-text-tertiary">{t("ind.empty")}</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-5">
          <ChartPanel
            className="xl:col-span-2"
            title={t("ind.ranking")}
            description={t("ind.rankingDesc")}
            chartClassName="h-[460px]"
            chart={
              <IvRankingChart
                items={ranked.map((item) => ({
                  key: item.id,
                  label: name(item),
                  iv: item.default_scheme!.iv,
                  selected: item.status === "published",
                  level: levelOf(item.default_scheme!.iv),
                  trend: item.default_scheme!.trend,
                }))}
                onSelect={(key) => router.push(`/indicators/${key}`)}
                selectedLabel={t("ind.statuses.published")}
                unselectedLabel={`${t("ind.statuses.draft")} / ${t("ind.statuses.retired")}`}
              />
            }
            table={
              <DataTable
                columns={[
                  { key: "name", label: t("ind.indicator") },
                  { key: "iv", label: "IV", align: "end" },
                ]}
                rows={ranked.map((item) => ({ key: item.id, cells: { name: name(item), iv: i18n.num(item.default_scheme!.iv, { minimumFractionDigits: 3 }) } }))}
              />
            }
          />
          <section className="flex min-w-0 flex-col gap-3 rounded-2xl bg-background-secondary-default p-4 xl:col-span-3">
            <div className={`overflow-x-auto rounded-xl bg-background-primary-default ${list.isFetching ? "opacity-60" : ""}`}>
              <table className="bui-table bui-table-sm">
                <thead>
                  <tr>
                    <th>{t("ind.indicator")}</th>
                    <th>{t("ind.category")}</th>
                    <th className="!text-end">IV</th>
                    <th>{t("ind.scheme")}</th>
                    <th>{t("ind.status")}</th>
                    <th>{t("ind.source")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((item) => {
                    const scheme = item.default_scheme;
                    return (
                      <tr key={item.id} className="cursor-pointer hover:bg-background-secondary-hover" onClick={() => router.push(`/indicators/${item.id}`)}>
                        <td>
                          <Link href={`/indicators/${item.id}`} className="flex flex-col outline-none focus-visible:underline" onClick={(e) => e.stopPropagation()}>
                            <span className="text-body-2-medium text-text-primary">{name(item)}</span>
                            <code className="font-mono text-caption-2-regular text-text-tertiary">{item.code}</code>
                          </Link>
                        </td>
                        <td className="whitespace-nowrap text-text-secondary">{t(`ind.categories.${item.category}`)}</td>
                        <td className="text-end">
                          {scheme ? (
                            <span className="flex items-center justify-end gap-2">
                              <span className="tabular-nums">{i18n.num(scheme.iv, { minimumFractionDigits: 3, maximumFractionDigits: 3 })}</span>
                              <Chip variant="subtle" color={LEVEL_CHIP[levelOf(scheme.iv)]}>{t(`indicators.levels.${levelOf(scheme.iv)}`)}</Chip>
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="whitespace-nowrap text-text-secondary">
                          {scheme ? t(`ind.methods.${scheme.method}`) : t("ind.noScheme")}
                        </td>
                        <td>
                          <Chip variant="subtle" color={STATUS_CHIP[item.status]}>{t(`ind.statuses.${item.status}`)}</Chip>
                        </td>
                        <td className="max-w-[140px] truncate text-text-tertiary" title={item.dataset?.name}>{item.dataset?.name ?? t("ind.datasetMissing")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <span className="text-body-2-regular text-text-tertiary">{t("common.total", { n: data.total })}</span>
          </section>
        </div>
      )}
      <CreateModal isOpen={creating} onClose={() => setCreating(false)} />
    </>
  );
}
