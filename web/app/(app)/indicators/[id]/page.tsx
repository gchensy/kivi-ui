"use client";

import {
  RiCheckLine,
  RiDeleteBinLine,
  RiDownloadLine,
  RiEditLine,
  RiErrorWarningLine,
  RiSaveLine,
  RiStarFill,
} from "@remixicon/react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Input } from "@/components/base/input/input";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Slider } from "@/components/base/slider/slider";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { BinChart, type BinMetric } from "@/components/kivi/charts/indicators";
import { Legend } from "@/components/kivi/charts/kit";
import { PsiBars } from "@/components/kivi/charts/stability";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { Modal } from "@/components/kivi/modal";
import { Notice } from "@/components/kivi/notice";
import { ChartPanel, DataTable, MetricSwitch, Panel } from "@/components/kivi/panel";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, PageSkeleton, Skeleton } from "@/components/kivi/states";
import { levelOf as psiLevel, STATUS_COLOR, StatusBadge } from "@/components/kivi/status";
import { api, errorMessage } from "@/lib/api";
import { parseNumbers } from "@/lib/datasets";
import { binLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { CATEGORIES, indicatorName, LEVEL_CHIP } from "@/lib/indicators";
import { useIndicator, useMe } from "@/lib/queries";
import type { BinMethod, BinningResult, BinSpec, IndicatorCategory, IndicatorDetail, IndicatorStatus, Scheme, Stability } from "@/lib/types";
import { cx } from "@/utils/cx";

const NUMERIC_METHODS: BinMethod[] = ["quantile", "uniform", "chimerge", "tree", "monotonic", "manual"];
const DEFAULT_SPEC: BinSpec = { method: "monotonic", bins: 5, cuts: [], special: [], min_bin_share: 0.05, direction: "auto", alpha: 0.05 };
const THRESHOLDS = { warn: 0.1, alert: 0.25 };
const STATUS_CHIP = { draft: "yellow", published: "lime", retired: "neutral" } as const;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

function Fact({ label, value, tone }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-xl bg-background-primary-default px-3 py-2 shadow-card">
      <span className="truncate text-caption-1-medium text-text-tertiary">{label}</span>
      <span className={cx("truncate text-body-semibold text-text-primary", tone)}>{value}</span>
    </div>
  );
}

function EditModal({ indicator, isOpen, onClose, onSaved }: { indicator: IndicatorDetail; isOpen: boolean; onClose: () => void; onSaved: (i: IndicatorDetail) => void }) {
  const { t } = useI18n();
  const [category, setCategory] = useState<IndicatorCategory>(indicator.category);
  const [status, setStatus] = useState<IndicatorStatus>(indicator.status);
  const [unit, setUnit] = useState<string>(indicator.unit ?? "none");
  const [error, setError] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<IndicatorDetail>(`/indicators/${indicator.id}`, { method: "PATCH", body }),
    onSuccess: (i) => {
      setError(null);
      onSaved(i);
      onClose();
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    save.mutate({
      name: String(form.get("name") ?? ""),
      name_en: String(form.get("name_en") ?? ""),
      description: String(form.get("description") ?? ""),
      category,
      status,
      ...(unit === "none" ? { clear_unit: true } : { unit }),
    });
  };
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("ind.editTitle")}>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <Input name="name" label={t("ind.name")} defaultValue={indicator.name} isRequired />
          <Input name="name_en" label={t("ind.nameEn")} defaultValue={indicator.name_en ?? ""} />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <SelectField label={t("ind.category")} value={category} onChange={(v) => setCategory(v as IndicatorCategory)} options={CATEGORIES.map((c) => ({ id: c, label: t(`ind.categories.${c}`) }))} />
          <SelectField label={t("ind.status")} value={status} onChange={(v) => setStatus(v as IndicatorStatus)} options={(["draft", "published", "retired"] as const).map((s) => ({ id: s, label: t(`ind.statuses.${s}`) }))} />
          <SelectField label={t("ind.unit")} value={unit} onChange={setUnit} options={["none", "count", "ratio", "cny", "years"].map((u) => ({ id: u, label: t(`ind.units.${u}`) }))} />
        </div>
        <Textarea name="description" label={t("ind.description")} defaultValue={indicator.description} rows={3} />
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={save.isPending}>{t("common.save")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function SaveSchemeModal({ isOpen, onClose, onSave, busy, error }: { isOpen: boolean; onClose: () => void; onSave: (name: string, makeDefault: boolean) => void; busy: boolean; error: string | null }) {
  const { t } = useI18n();
  const [makeDefault, setMakeDefault] = useState(true);
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t("ind.saveScheme")}>
      <form
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSave(String(new FormData(event.currentTarget).get("name") ?? ""), makeDefault);
        }}
      >
        <Input name="name" label={t("ind.schemeName")} isRequired autoFocus />
        <Checkbox isSelected={makeDefault} onChange={setMakeDefault}>
          {t("ind.makeDefault")}
        </Checkbox>
        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" leadingIcon={RiSaveLine} disabled={busy}>{t("common.save")}</Button>
        </div>
      </form>
    </Modal>
  );
}

function MethodPicker({ value, onChange, methods }: { value: BinMethod; onChange: (m: BinMethod) => void; methods: BinMethod[] }) {
  const { t } = useI18n();
  return (
    <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label={t("data.method")}>
      {methods.map((m) => {
        const selected = m === value;
        return (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(m)}
            className={cx(
              "flex cursor-pointer items-center justify-between gap-2 rounded-xl border px-3 py-2 text-start text-body-2-medium outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus-ring",
              selected
                ? "border-accent-500 bg-accent-50 text-text-primary dark:bg-accent-950/40"
                : "border-border-button-default bg-background-primary-default text-text-secondary hover:border-border-button-hover",
            )}
          >
            {t(`ind.methods.${m}`)}
            {selected && <RiCheckLine className="size-4 shrink-0 text-accent-500" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}

export default function IndicatorPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useIndicator(id);
  const indicator = query.data;
  const [spec, setSpec] = useState<BinSpec | null>(null);
  const [cutsText, setCutsText] = useState("");
  const [specialText, setSpecialText] = useState("");
  const [metric, setMetric] = useState<BinMetric>("woe");
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Start the workbench from the default scheme's parameters.
  useEffect(() => {
    if (!indicator || spec) return;
    const base = indicator.schemes.find((s) => s.id === indicator.default_scheme?.id)?.spec ?? DEFAULT_SPEC;
    const start = { ...DEFAULT_SPEC, ...base, method: indicator.kind === "category" ? "category" : base.method } as BinSpec;
    setSpec(start);
    setCutsText(start.cuts.join(", "));
    setSpecialText(start.special.join(", "));
  }, [indicator, spec]);

  const effective: BinSpec | null = spec && { ...spec, cuts: parseNumbers(cutsText), special: parseNumbers(specialText) };
  const debounced = useDebounced(effective, 300);
  const ready = Boolean(debounced && indicator?.dataset?.target_column && (debounced.method !== "manual" || debounced.cuts.length));
  const preview = useQuery({
    queryKey: ["indicators", id, "binning", JSON.stringify(debounced)],
    queryFn: () => api<BinningResult>(`/indicators/${id}/binning`, { body: debounced as unknown as Record<string, unknown> }),
    enabled: ready,
    placeholderData: keepPreviousData,
    retry: false,
  });
  const stability = useQuery({
    queryKey: ["indicators", id, "stability", indicator?.default_scheme?.id],
    queryFn: () => api<Stability>(`/indicators/${id}/stability`),
    enabled: Boolean(indicator?.default_scheme && indicator.dataset?.date_column),
    retry: false,
  });

  const refresh = (next?: IndicatorDetail) => {
    if (next) client.setQueryData(["indicators", id], next);
    else client.invalidateQueries({ queryKey: ["indicators", id], exact: true });
    client.invalidateQueries({ queryKey: ["indicators", "list"] });
    client.invalidateQueries({ queryKey: ["indicators", id, "stability"] });
  };
  const saveScheme = useMutation({
    mutationFn: ({ name, makeDefault }: { name: string; makeDefault: boolean }) =>
      api<Scheme>(`/indicators/${id}/schemes`, { body: { name, spec: effective, make_default: makeDefault } }),
    onSuccess: (scheme) => {
      setSaving(false);
      setSaveError(null);
      setNotice(t("ind.schemeSaved", { name: scheme.name }));
      refresh();
    },
    onError: (err) => setSaveError(errorMessage(err, t)),
  });
  const schemeAction = useMutation({
    mutationFn: ({ scheme, action }: { scheme: Scheme; action: "default" | "delete" }) =>
      api<IndicatorDetail>(`/indicators/${id}/schemes/${scheme.id}${action === "default" ? "/default" : ""}`, { method: action === "default" ? "POST" : "DELETE" }),
    onSuccess: (next) => refresh(next),
  });

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!indicator || !spec || !me.data) return <PageSkeleton />;
  const canDelete = me.data.role === "admin" || indicator.owner?.id === me.data.id;
  const name = indicatorName(indicator, i18n.locale);
  const result = preview.data;
  const methods: BinMethod[] = indicator.kind === "category" ? ["category"] : NUMERIC_METHODS;
  const update = (patch: Partial<BinSpec>) => setSpec({ ...spec, ...patch });
  const f3 = (v: number) => i18n.num(v, { minimumFractionDigits: 3, maximumFractionDigits: 3 });

  return (
    <>
      <PageHeader
        title={name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-secondary">{indicator.code}</code>
            <Chip variant="subtle" color="blue">{t(`ind.categories.${indicator.category}`)}</Chip>
            <Chip variant="subtle" color={STATUS_CHIP[indicator.status]}>{t(`ind.statuses.${indicator.status}`)}</Chip>
            <span>{t(`ind.kinds.${indicator.kind}`)}</span>
            <span>·</span>
            {indicator.dataset ? (
              <Link href={`/data/${indicator.dataset.id}`} className="text-accent-500 hover:underline">
                {indicator.dataset.name} · {indicator.column_name}
              </Link>
            ) : (
              <span>{t("ind.datasetMissing")}</span>
            )}
          </span>
        }
        actions={
          <>
            <Button variant="secondary" leadingIcon={RiEditLine} onClick={() => setEditing(true)}>{t("ind.edit")}</Button>
            {canDelete && <Button variant="secondary" leadingIcon={RiDeleteBinLine} onClick={() => setDeleting(true)}>{t("ind.delete")}</Button>}
          </>
        }
      />
      {indicator.description && <p className="mx-1 text-body-regular text-text-secondary">{indicator.description}</p>}

      <div className="grid gap-4 xl:grid-cols-3">
        <Panel title={t("ind.workbench")} description={t("ind.workbenchDesc")}>
          <div className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <MethodPicker value={spec.method} onChange={(method) => update({ method })} methods={methods} />
              <p className="text-caption-1-regular text-text-tertiary">{t(`ind.methodHints.${spec.method}`)}</p>
            </div>
            {spec.method !== "manual" && spec.method !== "category" && (
              <Slider label={t("ind.bins")} minValue={2} maxValue={12} step={1} value={spec.bins} onChange={(v) => update({ bins: v as number })} />
            )}
            {(spec.method === "tree" || spec.method === "category") && (
              <Slider
                label={t("ind.minShare")}
                minValue={0.01}
                maxValue={0.2}
                step={0.01}
                value={spec.min_bin_share}
                formatValue={(v) => i18n.pct(v, 0)}
                onChange={(v) => update({ min_bin_share: v as number })}
              />
            )}
            {spec.method === "monotonic" && (
              <div className="flex flex-col gap-1.5">
                <span className="text-body-medium text-text-secondary">{t("ind.direction")}</span>
                <SegmentedControl aria-label={t("ind.direction")} selectedKeys={new Set([spec.direction])} onSelectionChange={(keys) => update({ direction: ([...keys][0] as BinSpec["direction"]) ?? "auto" })}>
                  {(["auto", "increasing", "decreasing"] as const).map((d) => (
                    <SegmentedControlItem key={d} id={d}>{t(`ind.directions.${d}`)}</SegmentedControlItem>
                  ))}
                </SegmentedControl>
              </div>
            )}
            {spec.method === "manual" && (
              <Input label={t("ind.cuts")} placeholder={t("ind.cutsPlaceholder")} value={cutsText} onChange={setCutsText} inputDir="ltr" />
            )}
            {indicator.kind === "numeric" && (
              <Input label={t("ind.special")} placeholder={t("ind.specialPlaceholder")} value={specialText} onChange={setSpecialText} inputDir="ltr" />
            )}
            <Button leadingIcon={RiSaveLine} disabled={!result || preview.isError} onClick={() => setSaving(true)}>
              {t("ind.saveScheme")}
            </Button>
          </div>
        </Panel>

        <div className="flex min-w-0 flex-col gap-4 xl:col-span-2">
          {!indicator.dataset?.target_column ? (
            <FormError message={indicator.dataset ? t("data.needTarget") : t("ind.datasetMissing")} />
          ) : preview.isError ? (
            <FormError message={errorMessage(preview.error, t)} />
          ) : !result ? (
            <Skeleton className="h-[440px]" />
          ) : (
            <>
              <div className={cx("grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6", preview.isFetching && "opacity-60")}>
                <Fact label="IV" value={f3(result.iv)} />
                <Fact label={t("indicators.level")} value={<Chip variant="subtle" color={LEVEL_CHIP[result.level]}>{t(`indicators.levels.${result.level}`)}</Chip>} />
                <Fact label={t("indicators.trend")} value={t(`indicators.trends.${result.trend}`)} />
                <Fact label={t("indicators.missingRate")} value={i18n.pct(result.missing_rate)} />
                <Fact label={t("ind.binCountLabel")} value={t("ind.bins_count", { n: result.bins.length })} />
                <Fact label={t("indicators.badRate")} value={i18n.pct(result.bad_rate, 2)} />
              </div>
              {result.notes.length > 0 && (
                <p className="flex items-start gap-2 rounded-xl bg-status-yellow-background px-3 py-2 text-body-2-regular text-status-yellow-text">
                  <RiErrorWarningLine className="mt-0.5 size-4 shrink-0" aria-hidden />
                  {result.notes.join("；")}
                </p>
              )}
              <div className={cx(preview.isFetching && "opacity-60 transition-opacity")}>
                <ChartPanel
                  title={t("indicators.detail")}
                  description={`${t(metric === "woe" ? "indicators.woeDesc" : metric === "bad_rate" ? "indicators.badRateDesc" : "indicators.shareDesc")} · ${t("ind.rows", { n: i18n.num(result.rows) })}`}
                  controls={
                    <MetricSwitch
                      label={t("indicators.detail")}
                      value={metric}
                      onChange={setMetric}
                      options={[
                        { id: "woe", label: t("indicators.metricWoe") },
                        { id: "bad_rate", label: t("indicators.metricBadRate") },
                        { id: "share", label: t("indicators.metricShare") },
                      ]}
                    />
                  }
                  legend={
                    metric === "woe" ? (
                      <Legend
                        items={[
                          { label: t("indicators.higherRisk"), color: "var(--viz-pos)" },
                          { label: t("indicators.lowerRisk"), color: "var(--viz-neg)" },
                        ]}
                      />
                    ) : undefined
                  }
                  chartClassName="h-[300px]"
                  chart={<BinChart bins={result.bins} unit={indicator.unit} metric={metric} overallBadRate={result.bad_rate} />}
                  table={
                    <DataTable
                      columns={[
                        { key: "bin", label: t("indicators.bin") },
                        { key: "count", label: t("indicators.count"), align: "end" },
                        { key: "share", label: t("indicators.share"), align: "end" },
                        { key: "bad", label: t("indicators.bad"), align: "end" },
                        { key: "rate", label: t("indicators.badRate"), align: "end" },
                        { key: "woe", label: "WOE", align: "end" },
                        { key: "iv", label: "IV", align: "end" },
                      ]}
                      rows={result.bins.map((b) => ({
                        key: b.code,
                        cells: {
                          bin: binLabel(b, indicator.unit, i18n),
                          count: i18n.num(b.count),
                          share: i18n.pct(b.share),
                          bad: i18n.num(b.bad),
                          rate: i18n.pct(b.bad_rate, 2),
                          woe: f3(b.woe),
                          iv: i18n.num(b.iv, { minimumFractionDigits: 4, maximumFractionDigits: 4 }),
                        },
                      }))}
                    />
                  }
                />
              </div>
            </>
          )}
        </div>
      </div>

      <div className="grid gap-4">
        <Panel title={t("ind.schemes")} description={t("ind.schemesDesc")}>
          <div className="overflow-x-auto rounded-xl bg-background-primary-default">
            <table className={cx("bui-table bui-table-sm", schemeAction.isPending && "opacity-60")}>
              <thead>
                <tr>
                  <th>{t("ind.schemeName")}</th>
                  <th>{t("data.method")}</th>
                  <th className="!text-end">IV</th>
                  <th>{t("indicators.trend")}</th>
                  <th>{t("ind.author")}</th>
                  <th className="!text-end">{t("common.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {indicator.schemes.map((s) => {
                  const isDefault = s.id === indicator.default_scheme?.id;
                  return (
                    <tr key={s.id}>
                      <td>
                        <span className="flex items-center gap-1.5">
                          {isDefault && <RiStarFill className="size-4 text-accent-500" aria-label={t("ind.default")} />}
                          <span className="text-body-2-medium text-text-primary">{s.name}</span>
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-text-secondary">
                        {t(`ind.methods.${s.method}`)} · {t("ind.bins_count", { n: s.bins.length })}
                      </td>
                      <td className="text-end tabular-nums">{f3(s.iv)}</td>
                      <td className="text-text-secondary">{t(`indicators.trends.${s.trend}`)}</td>
                      <td className="whitespace-nowrap text-text-tertiary">
                        {s.author?.display_name ?? t("common.system")} · {i18n.date(s.created_at, { dateStyle: "short" })}
                      </td>
                      <td>
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            size="xs"
                            variant="ghost"
                            leadingIcon={RiDownloadLine}
                            onClick={() => {
                              setSpec({ ...DEFAULT_SPEC, ...s.spec });
                              setCutsText((s.spec.cuts ?? []).join(", "));
                              setSpecialText((s.spec.special ?? []).join(", "));
                            }}
                          >
                            {t("ind.load")}
                          </Button>
                          {!isDefault && (
                            <Button size="xs" variant="ghost" onClick={() => schemeAction.mutate({ scheme: s, action: "default" })}>
                              {t("ind.setDefault")}
                            </Button>
                          )}
                          {indicator.schemes.length > 1 && (
                            <Button size="xs" variant="ghost" onClick={() => schemeAction.mutate({ scheme: s, action: "delete" })}>
                              {t("ind.deleteScheme")}
                            </Button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>

        {indicator.dataset?.date_column ? (
          stability.data ? (
            <ChartPanel
              title={t("ind.stability")}
              description={t("ind.stabilityDesc", { n: stability.data.months.filter((m) => m.in_reference).length })}
              legend={
                <Legend
                  items={[
                    { label: t("alerts.normal"), color: STATUS_COLOR.normal },
                    { label: t("alerts.warn"), color: STATUS_COLOR.warn },
                    { label: t("alerts.alert"), color: STATUS_COLOR.alert },
                  ]}
                />
              }
              chartClassName="h-[240px]"
              chart={<PsiBars data={stability.data.months.map((m) => ({ month: m.month, psi: m.psi ?? 0, in_reference: m.in_reference, rows: m.rows }))} thresholds={THRESHOLDS} referenceLabel={t("ind.reference")} />}
              table={
                <DataTable
                  columns={[
                    { key: "month", label: t("stability.month") },
                    { key: "rows", label: t("data.rows"), align: "end" },
                    { key: "psi", label: "PSI", align: "end" },
                    { key: "level", label: t("stability.level") },
                  ]}
                  rows={stability.data.months.map((m) => ({
                    key: m.month,
                    cells: {
                      month: i18n.month(m.month, true),
                      rows: i18n.num(m.rows),
                      psi: f3(m.psi ?? 0),
                      level: <StatusBadge level={psiLevel(m.psi ?? 0, THRESHOLDS.warn, THRESHOLDS.alert)} />,
                    },
                  }))}
                />
              }
            />
          ) : stability.isError ? (
            <Panel title={t("ind.stability")}>
              <FormError message={errorMessage(stability.error, t)} />
            </Panel>
          ) : (
            <Skeleton className="h-[320px]" />
          )
        ) : (
          <Panel title={t("ind.stability")}>
            <p className="py-10 text-center text-body-regular text-text-tertiary">{t("ind.stabilityNoDate")}</p>
          </Panel>
        )}
      </div>

      <EditModal key={indicator.updated_at} indicator={indicator} isOpen={editing} onClose={() => setEditing(false)} onSaved={(next) => { refresh(next); setNotice(t("ind.saved")); }} />
      <SaveSchemeModal
        isOpen={saving}
        onClose={() => setSaving(false)}
        busy={saveScheme.isPending}
        error={saveError}
        onSave={(schemeName, makeDefault) => saveScheme.mutate({ name: schemeName, makeDefault })}
      />
      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("ind.deleteTitle")}
        description={t("ind.deleteDesc", { name })}
        confirmLabel={t("ind.delete")}
        onConfirm={async () => {
          await api(`/indicators/${indicator.id}`, { method: "DELETE" });
          client.removeQueries({ queryKey: ["indicators", indicator.id] });
          await client.invalidateQueries({ queryKey: ["indicators"] });
          router.replace("/indicators");
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
