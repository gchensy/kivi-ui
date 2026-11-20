"use client";

import {
  RiArrowLeftSLine,
  RiArrowRightSLine,
  RiDatabase2Fill,
  RiDeleteBinLine,
  RiFunctionAddLine,
  RiLayoutColumnFill,
  RiPercentFill,
  RiPlayLine,
  RiTimeFill,
} from "@remixicon/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Tab, TabList, TabPanel, Tabs } from "@/components/base/tabs/tabs";
import { PageHeader } from "@/components/kivi/app-shell";
import { IvRankingChart } from "@/components/kivi/charts/indicators";
import { MonthlyIntakeChart } from "@/components/kivi/charts/overview";
import { ConfirmDelete } from "@/components/kivi/confirm";
import { FormError } from "@/components/kivi/form-error";
import { Notice } from "@/components/kivi/notice";
import { ChartPanel, DataTable, MetricSwitch, Panel } from "@/components/kivi/panel";
import { SelectField, type Option } from "@/components/kivi/select-field";
import { StatTile } from "@/components/kivi/stat-tile";
import { ErrorState, PageSkeleton, Skeleton } from "@/components/kivi/states";
import { api, ApiError, errorMessage } from "@/lib/api";
import { periodText } from "@/lib/datasets";
import { useI18n } from "@/lib/i18n/provider";
import { CATEGORIES, ivLevel as levelOf, LEVEL_CHIP } from "@/lib/indicators";
import { useDataset, useMe } from "@/lib/queries";
import type { BinMethod, DatasetColumn, DatasetDetail, IndicatorCategory, Monthly, Preview, ScreeningRow } from "@/lib/types";

const TYPE_CHIP = { numeric: "blue", category: "purple", datetime: "orange", text: "neutral" } as const;
function IvCell({ iv }: { iv: number | null }) {
  const i18n = useI18n();
  if (iv === null) return <span className="text-text-tertiary">—</span>;
  const level = levelOf(iv);
  return (
    <span className="flex items-center justify-end gap-2">
      <span className="h-1.5 w-16 rounded-full bg-background-tertiary-default" aria-hidden>
        <span className="block h-1.5 rounded-full" style={{ width: `${Math.min(100, (iv / 0.5) * 100)}%`, background: "var(--viz-1)" }} />
      </span>
      <span className="w-12 text-end tabular-nums">{i18n.num(iv, { minimumFractionDigits: 3, maximumFractionDigits: 3 })}</span>
      <Chip variant="subtle" color={LEVEL_CHIP[level]}>{i18n.t(`indicators.levels.${level}`)}</Chip>
    </span>
  );
}

function summary(column: DatasetColumn, i18n: ReturnType<typeof useI18n>): string {
  const s = column.stats;
  if (column.dtype === "numeric" && s.min !== undefined) {
    const f = (v: unknown) => i18n.num(Number(v), { maximumFractionDigits: 2 });
    return `${f(s.min)} – ${f(s.max)} · μ ${f(s.mean)}`;
  }
  if (column.dtype === "datetime" && s.min) {
    return `${i18n.date(String(s.min), { dateStyle: "medium" })} – ${i18n.date(String(s.max), { dateStyle: "medium" })}`;
  }
  if (column.dtype === "text") return "—";
  if (s.top?.length) return s.top.slice(0, 3).map((t) => `${t.value} ${i18n.pct(t.share, 0)}`).join(" · ");
  return "—";
}

function LabelSettings({ dataset, canEdit, onSaved }: { dataset: DatasetDetail; canEdit: boolean; onSaved: (d: DatasetDetail) => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const [target, setTarget] = useState(dataset.target_column ?? "");
  const [event, setEvent] = useState(dataset.target_event ?? "");
  const [date, setDate] = useState(dataset.date_column ?? "");
  const [id, setId] = useState(dataset.id_column ?? "");
  const [error, setError] = useState<string | null>(null);
  const [eventChoices, setEventChoices] = useState<string[] | null>(null);
  const none: Option = { id: "", label: t("data.none") };
  const byName = Object.fromEntries(dataset.columns.map((c) => [c.column_name, c]));
  const label = (c: DatasetColumn) => (c.name === c.column_name ? c.name : `${c.name} (${c.column_name})`);
  const targetOptions = [none, ...dataset.columns.filter((c) => c.unique_count === 2 && c.dtype !== "datetime").map((c) => ({ id: c.column_name, label: label(c) }))];
  const dateOptions = [none, ...dataset.columns.filter((c) => c.dtype === "datetime").map((c) => ({ id: c.column_name, label: label(c) }))];
  const idOptions = [none, ...dataset.columns.filter((c) => c.dtype !== "datetime" && c.unique_count > 0.9 * dataset.row_count).map((c) => ({ id: c.column_name, label: label(c) }))];
  const targetColumn = target ? byName[target] : undefined;
  const values = eventChoices ?? (targetColumn?.dtype !== "numeric" ? (targetColumn?.stats.top ?? []).map((v) => v.value) : []);

  const save = useMutation({
    mutationFn: () => {
      const clear: string[] = [];
      const body: Record<string, unknown> = { clear };
      if (target !== (dataset.target_column ?? "") || event !== (dataset.target_event ?? "")) {
        if (target) Object.assign(body, { target_column: target, target_event: values.length ? event || null : null });
        else clear.push("target_column");
      }
      if (date !== (dataset.date_column ?? "")) (date ? (body.date_column = date) : clear.push("date_column"));
      if (id !== (dataset.id_column ?? "")) (id ? (body.id_column = id) : clear.push("id_column"));
      return api<DatasetDetail>(`/datasets/${dataset.id}`, { method: "PATCH", body });
    },
    onSuccess: (d) => {
      setError(null);
      setEventChoices(null);
      onSaved(d);
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === "target_event_required") {
        setEventChoices(((err.detail as { values?: string[] })?.values ?? []).map(String));
      }
      setError(errorMessage(err, t));
    },
  });

  return (
    <Panel title={t("data.settings")} description={t("data.settingsDesc")}>
      <div className="flex flex-col gap-3">
        <SelectField label={t("data.target")} value={target} onChange={(v) => { setTarget(v); setEvent(""); setEventChoices(null); }} options={targetOptions} isDisabled={!canEdit} />
        {target && values.length > 0 && (
          <SelectField
            label={t("data.targetEvent")}
            hint={t("data.targetEventHint")}
            value={event}
            onChange={setEvent}
            options={values.map((v) => ({ id: v, label: v }))}
            isDisabled={!canEdit}
          />
        )}
        <SelectField label={t("data.date")} value={date} onChange={setDate} options={dateOptions} isDisabled={!canEdit} />
        <SelectField label={t("data.id")} value={id} onChange={setId} options={idOptions} isDisabled={!canEdit} />
        <FormError message={error} />
        {canEdit && (
          <Button className="self-end" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending ? t("common.saving") : t("data.save")}
          </Button>
        )}
      </div>
    </Panel>
  );
}

function ColumnsTab({ dataset, canEdit, onSaved }: { dataset: DatasetDetail; canEdit: boolean; onSaved: (d: DatasetDetail) => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const [error, setError] = useState<string | null>(null);
  const role = useMutation({
    mutationFn: ({ column, value }: { column: string; value: string }) =>
      api<DatasetDetail>(`/datasets/${dataset.id}`, { method: "PATCH", body: { roles: { [column]: value } } }),
    onSuccess: (d) => {
      setError(null);
      onSaved(d);
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  const roleOptions = [
    { id: "feature", label: t("data.roles.feature") },
    { id: "ignore", label: t("data.roles.ignore") },
  ];
  return (
    <div className="flex flex-col gap-3">
      <FormError message={error} />
      <div className="overflow-x-auto rounded-xl bg-background-primary-default">
        <table className={`bui-table bui-table-sm ${role.isPending ? "opacity-60" : ""}`}>
          <thead>
            <tr>
              <th>{t("data.column")}</th>
              <th>{t("data.type")}</th>
              <th>{t("data.role")}</th>
              <th className="!text-end">{t("data.missing")}</th>
              <th className="!text-end">{t("data.unique")}</th>
              <th className="!text-end">{t("data.iv")}</th>
              <th>{t("data.summary")}</th>
            </tr>
          </thead>
          <tbody>
            {dataset.columns.map((c) => {
              const fixed = c.role === "target" || c.role === "date" || c.role === "id";
              return (
                <tr key={c.column_name}>
                  <td>
                    <div className="flex flex-col">
                      <span className="text-body-2-medium text-text-primary">{c.name}</span>
                      {c.name !== c.column_name && <code className="font-mono text-caption-2-regular text-text-tertiary">{c.column_name}</code>}
                    </div>
                  </td>
                  <td>
                    <Chip variant="subtle" color={TYPE_CHIP[c.dtype]}>{t(`data.types.${c.dtype}`)}</Chip>
                  </td>
                  <td className="w-[130px]">
                    {fixed || !canEdit || c.dtype === "datetime" || c.dtype === "text" ? (
                      <span className={fixed ? "text-body-2-semibold text-text-primary" : "text-text-secondary"}>{t(`data.roles.${c.role}`)}</span>
                    ) : (
                      <SelectField size="sm" value={c.role} onChange={(value) => value !== c.role && role.mutate({ column: c.column_name, value })} options={roleOptions} />
                    )}
                  </td>
                  <td className="text-end">{i18n.pct(c.missing_rate)}</td>
                  <td className="text-end">{i18n.num(c.unique_count)}</td>
                  <td>
                    <IvCell iv={c.iv} />
                  </td>
                  <td className="max-w-[260px] truncate text-text-secondary">{summary(c, i18n)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PreviewTab({ dataset }: { dataset: DatasetDetail }) {
  const i18n = useI18n();
  const { t } = i18n;
  const [offset, setOffset] = useState(0);
  const size = 50;
  const preview = useQuery({
    queryKey: ["datasets", dataset.id, "preview", offset],
    queryFn: () => api<Preview>(`/datasets/${dataset.id}/preview?limit=${size}&offset=${offset}`),
    placeholderData: (previous) => previous,
  });
  if (!preview.data) return <Skeleton className="h-[360px]" />;
  const end = Math.min(offset + size, preview.data.total);
  return (
    <div className="flex flex-col gap-3">
      <div className="max-h-[520px] overflow-auto rounded-xl bg-background-primary-default">
        <table className={`bui-table bui-table-sm ${preview.isFetching ? "opacity-60" : ""}`}>
          <thead className="sticky top-0 z-10">
            <tr>
              <th className="!text-end">#</th>
              {preview.data.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {preview.data.rows.map((row, i) => (
              <tr key={offset + i}>
                <td className="text-end text-text-tertiary tabular-nums">{offset + i + 1}</td>
                {row.map((value, j) => (
                  <td key={j} className="whitespace-nowrap tabular-nums">
                    {value === null ? <span className="text-text-tertiary">—</span> : typeof value === "string" && /^\d{4}-\d\d-\d\dT/.test(value) ? value.slice(0, 10) : String(value)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-between gap-3">
        <span className="text-body-2-regular text-text-tertiary">
          {t("data.previewRange", { start: i18n.num(offset + 1), end: i18n.num(end), total: i18n.num(preview.data.total) })}
        </span>
        <div className="flex gap-2">
          <Button size="small" variant="secondary" leadingIcon={RiArrowLeftSLine} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - size))}>
            {t("data.prev")}
          </Button>
          <Button size="small" variant="secondary" trailingIcon={RiArrowRightSLine} disabled={end >= preview.data.total} onClick={() => setOffset(offset + size)}>
            {t("data.next")}
          </Button>
        </div>
      </div>
    </div>
  );
}

function ScreeningTab({ dataset, onImported }: { dataset: DatasetDetail; onImported: (n: number) => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const client = useQueryClient();
  const [method, setMethod] = useState<BinMethod>("monotonic");
  const [bins, setBins] = useState("5");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [category, setCategory] = useState<IndicatorCategory>("other");
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () => api<ScreeningRow[]>(`/datasets/${dataset.id}/screening`, { body: { method, bins: Number(bins) } }),
    onSuccess: (rows) => {
      setError(null);
      setPicked(new Set(rows.filter((r) => !r.indicator_id && (r.iv ?? 0) >= 0.02).map((r) => r.column)));
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  const register = useMutation({
    mutationFn: () => api<unknown[]>("/indicators/import", { body: { dataset_id: dataset.id, columns: [...picked], category } }),
    onSuccess: (created) => {
      client.invalidateQueries({ queryKey: ["indicators"] });
      client.invalidateQueries({ queryKey: ["datasets", dataset.id] });
      onImported(created.length);
      run.mutate();
    },
    onError: (err) => setError(errorMessage(err, t)),
  });
  const rows = run.data ?? [];
  const items = rows
    .filter((r) => r.iv !== null)
    .slice(0, 15)
    .map((r) => ({ key: r.column, label: r.name, iv: r.iv as number, selected: Boolean(r.indicator_id), level: r.level, trend: r.trend }));
  const methods: BinMethod[] = ["quantile", "uniform", "chimerge", "tree", "monotonic"];

  if (!dataset.target_column) return <FormError message={t("data.needTarget")} />;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <SelectField className="w-[180px]" label={t("data.method")} value={method} onChange={(v) => setMethod(v as BinMethod)} options={methods.map((m) => ({ id: m, label: t(`ind.methods.${m}`) }))} />
        <SelectField className="w-[120px]" label={t("data.bins")} value={bins} onChange={setBins} options={["3", "4", "5", "6", "8", "10"].map((n) => ({ id: n, label: n }))} />
        <Button leadingIcon={RiPlayLine} disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? t("data.running") : t("data.run")}
        </Button>
        <p className="text-body-2-regular text-text-tertiary">{t("ind.methodHints." + method)}</p>
      </div>
      <FormError message={error} />
      {!run.data ? (
        <p className="rounded-xl bg-background-primary-default py-10 text-center text-body-regular text-text-tertiary">{run.isPending ? t("data.running") : t("data.screeningEmpty")}</p>
      ) : (
        <div className="grid gap-4 xl:grid-cols-5">
          <div className="h-[420px] rounded-xl bg-background-primary-default p-3 xl:col-span-2">
            <IvRankingChart items={items} selectedLabel={t("data.registered")} unselectedLabel={t("indicators.notSelected")} />
          </div>
          <div className="flex min-w-0 flex-col gap-3 xl:col-span-3">
            <div className="max-h-[420px] overflow-auto rounded-xl bg-background-primary-default">
              <table className="bui-table bui-table-sm">
                <thead className="sticky top-0 z-10">
                  <tr>
                    <th className="w-8" />
                    <th>{t("data.column")}</th>
                    <th>{t("data.type")}</th>
                    <th className="!text-end">{t("data.iv")}</th>
                    <th>{t("indicators.trend")}</th>
                    <th className="!text-end">{t("data.missing")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.column}>
                      <td>
                        {r.indicator_id ? null : (
                          <Checkbox
                            size="sm"
                            aria-label={r.name}
                            isSelected={picked.has(r.column)}
                            isDisabled={r.iv === null}
                            onChange={(on) => {
                              const next = new Set(picked);
                              if (on) next.add(r.column);
                              else next.delete(r.column);
                              setPicked(next);
                            }}
                          />
                        )}
                      </td>
                      <td>
                        <span className="flex items-center gap-2">
                          {r.name}
                          {r.indicator_id && (
                            <Link href={`/indicators/${r.indicator_id}`}>
                              <Chip variant="subtle" color="blue">{t("data.registered")}</Chip>
                            </Link>
                          )}
                        </span>
                      </td>
                      <td>{t(`data.types.${r.dtype}`)}</td>
                      <td>
                        <IvCell iv={r.iv} />
                      </td>
                      <td className="text-text-secondary">{r.trend ? t(`indicators.trends.${r.trend}`) : "—"}</td>
                      <td className="text-end">{i18n.pct(r.missing_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-end justify-end gap-3">
              <SelectField
                className="w-[180px]"
                label={t("data.importCategory")}
                value={category}
                onChange={(v) => setCategory(v as IndicatorCategory)}
                options={CATEGORIES.map((c) => ({ id: c, label: t(`ind.categories.${c}`) }))}
              />
              <Button leadingIcon={RiFunctionAddLine} disabled={!picked.size || register.isPending} onClick={() => register.mutate()}>
                {t("data.importSelected", { n: picked.size })}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DatasetPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const me = useMe();
  const query = useDataset(id);
  const [metric, setMetric] = useState<"applications" | "bad_rate">("applications");
  const [notice, setNotice] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [tab, setTab] = useState<string>("columns");

  const monthly: Monthly[] = useMemo(
    () =>
      (query.data?.profile.monthly ?? []).map((m) => ({
        month: m.month,
        in_reference: true,
        applications: m.rows,
        bad_rate: m.bad_rate ?? 0,
        mean_score: 0,
        score_psi: 0,
        auc: null,
        ks: null,
        approval_rate: 0,
      })),
    [query.data],
  );
  useEffect(() => {
    if (query.data && !query.data.target_column) setTab("columns");
  }, [query.data]);

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data || !me.data) return <PageSkeleton />;
  const dataset = query.data;
  const canEdit = me.data.role === "admin" || dataset.owner?.id === me.data.id;
  const onSaved = (d: DatasetDetail) => {
    client.setQueryData(["datasets", d.id], d);
    client.invalidateQueries({ queryKey: ["datasets"], exact: true });
    setNotice(t("data.saved"));
  };

  return (
    <>
      <PageHeader
        title={dataset.name}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            {dataset.source === "demo" && <Chip variant="subtle" color="purple">{t("data.demo")}</Chip>}
            {dataset.file_name && <code className="font-mono text-body-2-regular">{dataset.file_name}</code>}
            <span>{dataset.owner?.display_name} · {i18n.date(dataset.created_at, { dateStyle: "medium" })}</span>
            <span>· {t("data.indicators", { n: dataset.indicator_count })}</span>
          </span>
        }
        actions={
          canEdit && (
            <Button variant="secondary" leadingIcon={RiDeleteBinLine} onClick={() => setDeleting(true)}>
              {t("data.delete")}
            </Button>
          )
        }
      />
      {dataset.description && <p className="mx-1 text-body-regular text-text-secondary">{dataset.description}</p>}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={RiDatabase2Fill} tone="sky" label={t("data.rows")} value={i18n.num(dataset.row_count)} caption={dataset.id_column ? `${t("data.id")} ${dataset.id_column}` : t("data.rows")} />
        <StatTile icon={RiLayoutColumnFill} tone="purple" label={t("data.columns")} value={i18n.num(dataset.column_count)} caption={t("data.indicators", { n: dataset.indicator_count })} />
        <StatTile
          icon={RiPercentFill}
          tone="pink"
          label={t("data.badRate")}
          value={dataset.bad_rate === null ? "—" : i18n.pct(dataset.bad_rate, 2)}
          caption={dataset.target_column ? `${t("data.target")} ${dataset.target_column}${dataset.target_event ? ` = ${dataset.target_event}` : ""}` : t("data.noTarget")}
        />
        <StatTile
          icon={RiTimeFill}
          tone="orange"
          label={t("data.period")}
          value={monthly.length ? t("data.monthsCount", { n: monthly.length }) : "—"}
          caption={periodText(dataset, i18n) ?? t("data.noDate")}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {monthly.length > 0 ? (
          <ChartPanel
            className="xl:col-span-2"
            title={t("data.monthly")}
            description={t("data.monthlyDesc")}
            controls={
              <MetricSwitch
                label={t("data.monthly")}
                value={metric}
                onChange={setMetric}
                options={[
                  { id: "applications", label: t("data.rows") },
                  { id: "bad_rate", label: t("data.badRate") },
                ]}
              />
            }
            chart={<MonthlyIntakeChart monthly={monthly} metric={metric} />}
            table={
              <DataTable
                columns={[
                  { key: "month", label: t("overview.month") },
                  { key: "rows", label: t("data.rows"), align: "end" },
                  { key: "bad", label: t("data.badRate"), align: "end" },
                ]}
                rows={monthly.map((m) => ({ key: m.month, cells: { month: i18n.month(m.month, true), rows: i18n.num(m.applications), bad: i18n.pct(m.bad_rate, 2) } }))}
              />
            }
          />
        ) : (
          <Panel className="xl:col-span-2" title={t("data.monthly")} description={t("data.monthlyDesc")}>
            <p className="py-12 text-center text-body-regular text-text-tertiary">{t("data.noDate")}</p>
          </Panel>
        )}
        <LabelSettings key={dataset.updated_at} dataset={dataset} canEdit={canEdit} onSaved={onSaved} />
      </div>

      <section className="flex flex-col gap-4 rounded-2xl bg-background-secondary-default p-4">
        <Tabs selectedKey={tab} onSelectionChange={(key) => setTab(String(key))}>
          <TabList aria-label={dataset.name}>
            <Tab id="columns">{t("data.tabColumns")}</Tab>
            <Tab id="preview">{t("data.tabPreview")}</Tab>
            <Tab id="screening">{t("data.tabScreening")}</Tab>
          </TabList>
          <TabPanel id="columns" className="pt-4">
            <ColumnsTab dataset={dataset} canEdit={canEdit} onSaved={onSaved} />
          </TabPanel>
          <TabPanel id="preview" className="pt-4">
            <PreviewTab dataset={dataset} />
          </TabPanel>
          <TabPanel id="screening" className="pt-4">
            <p className="mb-3 text-body-2-regular text-text-tertiary">{t("data.screeningDesc")}</p>
            <ScreeningTab dataset={dataset} onImported={(n) => setNotice(t("data.imported", { n }))} />
          </TabPanel>
        </Tabs>
      </section>

      <ConfirmDelete
        isOpen={deleting}
        onClose={() => setDeleting(false)}
        title={t("data.deleteTitle")}
        description={t("data.deleteDesc", { name: dataset.name })}
        confirmLabel={t("data.delete")}
        onConfirm={async () => {
          await api(`/datasets/${dataset.id}`, { method: "DELETE" });
          client.removeQueries({ queryKey: ["datasets", dataset.id] });
          await client.invalidateQueries({ queryKey: ["datasets"] });
          client.invalidateQueries({ queryKey: ["indicators"] });
          router.replace("/data");
        }}
      />
      <Notice text={notice} onDone={() => setNotice(null)} />
    </>
  );
}
