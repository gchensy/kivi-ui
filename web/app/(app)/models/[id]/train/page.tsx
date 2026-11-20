"use client";

import { RiFlaskLine } from "@remixicon/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Input } from "@/components/base/input/input";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Switch } from "@/components/base/switch/switch";
import { Textarea } from "@/components/base/textarea/textarea";
import { PageHeader } from "@/components/kivi/app-shell";
import { FormError } from "@/components/kivi/form-error";
import { Panel } from "@/components/kivi/panel";
import { SelectField } from "@/components/kivi/select-field";
import { ErrorState, PageSkeleton, Skeleton } from "@/components/kivi/states";
import { api, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { indicatorName, ivLevel, LEVEL_CHIP } from "@/lib/indicators";
import { useDatasets, useModel } from "@/lib/queries";
import type { IndicatorPage, TrainConfig, VersionDetail } from "@/lib/types";

const DEFAULTS: TrainConfig = {
  oot_months: 3,
  test_ratio: 0.3,
  seed: 42,
  iv_min: 0.02,
  vif_max: 5,
  p_max: 0.05,
  require_positive: true,
  max_features: 12,
  base_score: 600,
  base_odds: 20,
  pdo: 50,
};

function Step({ n, title, description, children }: { n: number; title: string; description: string; children: React.ReactNode }) {
  return (
    <Panel
      title={
        <span className="flex items-center gap-2.5">
          <span className="flex size-6 items-center justify-center rounded-full bg-linear-to-b from-accent-500 to-accent-600 text-caption-1-semibold text-white">{n}</span>
          {title}
        </span>
      }
      description={description}
    >
      {children}
    </Panel>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number }) {
  return (
    <Input
      label={label}
      type="number"
      inputMode="decimal"
      value={String(value)}
      onChange={(text) => {
        const v = Number(text);
        if (text !== "" && Number.isFinite(v)) onChange(v);
      }}
      inputDir="ltr"
    />
  );
}

export default function TrainPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQueryClient();
  const model = useModel(id);
  const datasets = useDatasets();
  const [datasetId, setDatasetId] = useState<string>("");
  const [config, setConfig] = useState<TrainConfig>(DEFAULTS);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const labelled = (datasets.data ?? []).filter((d) => d.target_column);
  const dataset = labelled.find((d) => d.id === datasetId);

  useEffect(() => {
    if (!datasetId && labelled.length && model.data) {
      const previous = model.data.online?.dataset?.id ?? model.data.latest?.dataset?.id;
      setDatasetId(labelled.find((d) => d.id === previous)?.id ?? labelled[0].id);
    }
  }, [datasetId, labelled, model.data]);

  const indicators = useQuery({
    queryKey: ["indicators", "list", `dataset_id=${datasetId}`],
    queryFn: () => api<IndicatorPage>(`/indicators?dataset_id=${datasetId}`),
    enabled: Boolean(datasetId),
  });
  const items = useMemo(() => (indicators.data?.items ?? []).filter((i) => i.status !== "retired"), [indicators.data]);
  useEffect(() => {
    setPicked(new Set(items.filter((i) => (i.default_scheme?.iv ?? 0) >= 0.02).map((i) => i.id)));
  }, [items]);
  const datasetMonths = dataset?.profile.monthly?.length ?? 0;
  const datasetHasDate = Boolean(dataset?.date_column);
  useEffect(() => {
    setConfig((c) => ({ ...c, oot_months: datasetHasDate ? Math.min(DEFAULTS.oot_months, Math.max(datasetMonths - 1, 0)) : 0 }));
  }, [datasetId, datasetHasDate, datasetMonths]);

  const train = useMutation({
    mutationFn: () => api<VersionDetail>(`/models/${id}/versions`, { body: { dataset_id: datasetId, indicator_ids: [...picked], config, notes } }),
    onSuccess: (version) => {
      client.invalidateQueries({ queryKey: ["models"] });
      router.push(`/models/${id}/v/${version.id}`);
    },
    onError: (err) => setError(errorMessage(err, t)),
  });

  if (model.error) return <ErrorState error={model.error} onRetry={() => model.refetch()} />;
  if (!model.data) return <PageSkeleton />;
  const set = <K extends keyof TrainConfig>(key: K, value: TrainConfig[K]) => setConfig((c) => ({ ...c, [key]: value }));
  const months = dataset?.profile.monthly?.length ?? 0;
  const toggle = (key: string, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(key);
    else next.delete(key);
    setPicked(next);
  };

  return (
    <>
      <PageHeader title={t("mdl.wizardTitle", { name: indicatorName(model.data, i18n.locale) })} subtitle={t("mdl.wizardDesc")} />

      <Step n={1} title={t("mdl.step1")} description={t("mdl.step1Desc")}>
        <div className="grid gap-4 md:grid-cols-4">
          <SelectField
            className="md:col-span-2"
            label={t("mdl.dataset")}
            value={datasetId}
            onChange={setDatasetId}
            options={labelled.map((d) => ({ id: d.id, label: `${d.name} · ${i18n.num(d.row_count)}` }))}
          />
          <SelectField
            label={t("mdl.ootMonths")}
            value={String(config.oot_months)}
            onChange={(v) => set("oot_months", Number(v))}
            isDisabled={!dataset?.date_column}
            hint={dataset && !dataset.date_column ? t("mdl.noDateHint") : undefined}
            options={[0, 1, 2, 3, 4, 6].filter((n) => n < Math.max(months, 1)).map((n) => ({ id: String(n), label: n ? `${n}` : t("mdl.ootNone") }))}
          />
          <div className="flex flex-col gap-1.5">
            <span className="text-body-medium text-text-secondary">{t("mdl.testRatio")}</span>
            <SegmentedControl aria-label={t("mdl.testRatio")} selectedKeys={new Set([String(config.test_ratio)])} onSelectionChange={(keys) => set("test_ratio", Number([...keys][0] ?? 0.3))}>
              {["0", "0.2", "0.3"].map((r) => (
                <SegmentedControlItem key={r} id={r}>{i18n.pct(Number(r), 0)}</SegmentedControlItem>
              ))}
            </SegmentedControl>
          </div>
        </div>
      </Step>

      <Step n={2} title={t("mdl.step2")} description={t("mdl.step2Desc")}>
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button size="small" variant="secondary" onClick={() => setPicked(new Set(items.filter((i) => (i.default_scheme?.iv ?? 0) >= 0.02).map((i) => i.id)))}>
              {t("mdl.selectStrong")}
            </Button>
            <Button size="small" variant="ghost" onClick={() => setPicked(new Set(items.map((i) => i.id)))}>{t("mdl.selectAll")}</Button>
            <Button size="small" variant="ghost" onClick={() => setPicked(new Set())}>{t("mdl.selectNone")}</Button>
            <span className="ms-auto text-body-2-medium text-text-secondary">{t("mdl.selected", { n: picked.size })}</span>
          </div>
          {!indicators.data ? (
            <Skeleton className="h-[240px]" />
          ) : (
            <div className="max-h-[360px] overflow-auto rounded-xl bg-background-primary-default">
              <table className="bui-table bui-table-sm">
                <thead className="sticky top-0 z-10">
                  <tr>
                    <th className="w-8" />
                    <th>{t("ind.indicator")}</th>
                    <th>{t("ind.category")}</th>
                    <th className="!text-end">IV</th>
                    <th>{t("ind.scheme")}</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => {
                    const iv = item.default_scheme?.iv ?? null;
                    return (
                      <tr key={item.id}>
                        <td>
                          <Checkbox size="sm" aria-label={item.code} isSelected={picked.has(item.id)} onChange={(on) => toggle(item.id, on)} />
                        </td>
                        <td>
                          <span className="flex flex-col">
                            <span className="text-body-2-medium text-text-primary">{indicatorName(item, i18n.locale)}</span>
                            <code className="font-mono text-caption-2-regular text-text-tertiary">{item.code}</code>
                          </span>
                        </td>
                        <td className="text-text-secondary">{t(`ind.categories.${item.category}`)}</td>
                        <td className="text-end">
                          {iv === null ? "—" : (
                            <span className="flex items-center justify-end gap-2">
                              <span className="tabular-nums">{i18n.num(iv, { minimumFractionDigits: 3, maximumFractionDigits: 3 })}</span>
                              <Chip variant="subtle" color={LEVEL_CHIP[ivLevel(iv)]}>{t(`indicators.levels.${ivLevel(iv)}`)}</Chip>
                            </span>
                          )}
                        </td>
                        <td className="text-text-secondary">{item.default_scheme ? t(`ind.methods.${item.default_scheme.method}`) : t("ind.noScheme")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Step>

      <Step n={3} title={t("mdl.step3")} description={t("mdl.step3Desc")}>
        <div className="flex flex-col gap-5">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <NumberField label={t("mdl.ivMin")} value={config.iv_min} step={0.01} min={0} max={1} onChange={(v) => set("iv_min", v)} />
            <NumberField label={t("mdl.vifMax")} value={config.vif_max} step={0.5} min={1} max={100} onChange={(v) => set("vif_max", v)} />
            <NumberField label={t("mdl.pMax")} value={config.p_max} step={0.01} min={0.001} max={1} onChange={(v) => set("p_max", v)} />
            <NumberField label={t("mdl.maxFeatures")} value={config.max_features} min={1} max={40} onChange={(v) => set("max_features", Math.round(v))} />
          </div>
          <Switch isSelected={config.require_positive} onChange={(on) => set("require_positive", on)}>
            {t("mdl.requirePositive")}
          </Switch>
          <div className="grid gap-4 sm:grid-cols-3">
            <NumberField label={t("mdl.baseScore")} value={config.base_score} min={100} max={1000} onChange={(v) => set("base_score", Math.round(v))} />
            <NumberField label={t("mdl.baseOdds")} value={config.base_odds} min={1} max={1000} onChange={(v) => set("base_odds", v)} />
            <NumberField label={t("mdl.pdo")} value={config.pdo} min={1} max={200} onChange={(v) => set("pdo", v)} />
          </div>
          <p className="text-body-2-regular text-text-tertiary">{t("mdl.scalePreview", { base: config.base_score, odds: config.base_odds, pdo: config.pdo })}</p>
          <Textarea label={t("mdl.notes")} value={notes} onChange={setNotes} rows={2} />
          <FormError message={error ?? (!datasetId ? t("mdl.needDataset") : null)} />
          <div className="flex justify-end">
            <Button leadingIcon={RiFlaskLine} disabled={!datasetId || !picked.size || train.isPending} onClick={() => train.mutate()}>
              {train.isPending ? t("mdl.starting") : t("mdl.start")}
            </Button>
          </div>
        </div>
      </Step>
    </>
  );
}
