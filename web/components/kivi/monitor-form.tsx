"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";

import { Checkbox } from "@/components/base/checkbox/checkbox";
import { Button } from "@/components/base/buttons/button";
import { Input } from "@/components/base/input/input";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Switch } from "@/components/base/switch/switch";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n/provider";
import { useDatasets, useIndicators, useModels, useStrategies } from "@/lib/queries";
import type { Freq, MonitorDetail, MonitorItem, MonitorKind } from "@/lib/types";

import { FormError } from "./form-error";
import { Modal } from "./modal";
import { KINDS, MODEL_KINDS, SHIFT_KINDS } from "./monitoring";
import { SelectField } from "./select-field";

const DEFAULTS: Record<MonitorKind, { warn: number; alert: number }> = {
  indicator_psi: { warn: 0.1, alert: 0.25 },
  score_psi: { warn: 0.1, alert: 0.25 },
  model_ks: { warn: 0.1, alert: 0.2 },
  approval_rate: { warn: 0.05, alert: 0.1 },
  rule_hit_rate: { warn: 0.05, alert: 0.1 },
};
const FREQS: Freq[] = ["hourly", "daily", "weekly", "manual"];
const HOURS = Array.from({ length: 24 }, (_, h) => String(h));
const MINUTES = ["0", "5", "10", "15", "20", "30", "40", "45", "50"];

/** Create a monitor, or edit one (the check type and its target are fixed after creation). */
export function MonitorFormModal({
  isOpen,
  onClose,
  onSaved,
  monitor,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSaved: (monitor: MonitorDetail) => void;
  monitor?: MonitorItem;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const client = useQueryClient();
  const editing = !!monitor;
  const models = useModels();
  const strategies = useStrategies();
  const datasets = useDatasets();
  const allIndicators = useMemo(() => new URLSearchParams(), []);
  const indicators = useIndicators(allIndicators);

  const [kind, setKind] = useState<MonitorKind>(monitor?.kind ?? "score_psi");
  const [name, setName] = useState(monitor?.name ?? "");
  const [modelId, setModelId] = useState(monitor?.model?.id ?? "");
  const [strategyId, setStrategyId] = useState(monitor?.strategy?.id ?? "");
  const [datasetId, setDatasetId] = useState(monitor?.dataset?.id ?? "");
  const [useFeatures, setUseFeatures] = useState(!(monitor?.params.indicator_ids?.length));
  const [picked, setPicked] = useState<Set<string>>(new Set(monitor?.params.indicator_ids ?? []));
  const [refStart, setRefStart] = useState(monitor?.params.reference?.start ?? "");
  const [refEnd, setRefEnd] = useState(monitor?.params.reference?.end ?? "");
  const [windowDays, setWindowDays] = useState(String(monitor?.params.window_days ?? 7));
  const [baselineDays, setBaselineDays] = useState(String(monitor?.params.baseline_days ?? 30));
  const [minRequests, setMinRequests] = useState(String(monitor?.params.min_requests ?? 30));
  const [warn, setWarn] = useState(String(monitor?.thresholds.warn ?? DEFAULTS[kind].warn));
  const [alert, setAlert] = useState(String(monitor?.thresholds.alert ?? DEFAULTS[kind].alert));
  const [freq, setFreq] = useState<Freq>(monitor?.schedule.freq ?? "daily");
  const [hour, setHour] = useState(String(monitor?.schedule.hour ?? 6));
  const [minute, setMinute] = useState(String(monitor?.schedule.minute ?? 0));
  const [weekday, setWeekday] = useState(String(monitor?.schedule.weekday ?? 0));
  const [enabled, setEnabled] = useState(monitor?.enabled ?? true);
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string[]>([]);

  const onStrategy = SHIFT_KINDS.has(kind);
  const onDataset = MODEL_KINDS.has(kind);
  const chooseIndicators = kind === "indicator_psi" && !useFeatures;
  const dated = (datasets.data ?? []).filter((d) => d.date_column && d.source !== "score");

  const changeKind = (next: MonitorKind) => {
    setKind(next);
    setWarn(String(DEFAULTS[next].warn));
    setAlert(String(DEFAULTS[next].alert));
  };

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      editing ? api<MonitorDetail>(`/monitors/${monitor.id}`, { method: "PATCH", body }) : api<MonitorDetail>("/monitors", { body }),
    onSuccess: (saved) => {
      client.invalidateQueries({ queryKey: ["monitors"] });
      client.invalidateQueries({ queryKey: ["overview"] });
      setError(null);
      onSaved(saved);
    },
    onError: (err) => {
      setError(errorMessage(err, t));
      if (err instanceof ApiError) setInvalid(err.fields);
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const params: Record<string, unknown> = {};
    if (onStrategy) {
      Object.assign(params, { window_days: Number(windowDays), baseline_days: Number(baselineDays), min_requests: Number(minRequests) });
    } else {
      // Indicators deleted since the monitor was saved are dropped rather than sent back.
      if (chooseIndicators) params.indicator_ids = [...picked].filter((id) => !indicators.data || indicators.data.items.some((i) => i.id === id));
      if (refStart && refEnd) params.reference = { start: refStart, end: refEnd };
    }
    const body: Record<string, unknown> = {
      name,
      params,
      thresholds: { warn: Number(warn), alert: Number(alert) },
      schedule: { freq, hour: Number(hour), minute: Number(minute), weekday: Number(weekday) },
      enabled,
    };
    if (!onStrategy) body.dataset_id = datasetId || null;
    if (!editing) {
      Object.assign(body, {
        kind,
        model_id: !onStrategy && !(kind === "indicator_psi" && chooseIndicators) ? modelId || null : null,
        strategy_id: onStrategy ? strategyId || null : null,
      });
      if (!onStrategy && !datasetId) delete body.dataset_id;
    }
    save.mutate(body);
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={editing ? t("mon.editTitle") : t("mon.createTitle")} description={t(`mon.kindDesc.${kind}`)} wide>
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label={t("mon.name")} value={name} onChange={setName} isRequired isInvalid={invalid.includes("name")} />
          <SelectField
            label={t("mon.kind")}
            value={kind}
            isDisabled={editing}
            onChange={(v) => changeKind(v as MonitorKind)}
            options={KINDS.map((k) => ({ id: k, label: t(`mon.kinds.${k}`) }))}
          />
        </div>

        <fieldset className="flex flex-col gap-3 rounded-xl bg-background-secondary-default p-3">
          <legend className="sr-only">{t("mon.target")}</legend>
          {kind === "indicator_psi" && !editing && (
            <SegmentedControl
              aria-label={t("mon.indicators")}
              selectedKeys={new Set([useFeatures ? "model" : "pick"])}
              onSelectionChange={(keys) => setUseFeatures([...keys][0] === "model")}
            >
              <SegmentedControlItem id="model">{t("mon.modelFeatures")}</SegmentedControlItem>
              <SegmentedControlItem id="pick">{t("mon.chooseIndicators")}</SegmentedControlItem>
            </SegmentedControl>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            {onStrategy ? (
              <SelectField
                label={t("mon.strategy")}
                value={strategyId || null}
                isDisabled={editing}
                onChange={setStrategyId}
                options={(strategies.data ?? []).map((s) => ({ id: s.id, label: `${s.code}${s.online ? ` · v${s.online.version}` : ""}` }))}
              />
            ) : (
              !chooseIndicators && (
                <SelectField
                  label={t("mon.model")}
                  value={modelId || null}
                  isDisabled={editing}
                  onChange={setModelId}
                  options={(models.data ?? []).filter((m) => m.online).map((m) => ({ id: m.id, label: `${m.code} · v${m.online?.version}` }))}
                />
              )
            )}
            {onDataset && (
              <SelectField
                label={t("mon.dataset")}
                hint={t("mon.datasetHint")}
                value={datasetId}
                onChange={setDatasetId}
                options={[...(chooseIndicators ? [] : [{ id: "", label: t("mon.datasetDefault") }]), ...dated.map((d) => ({ id: d.id, label: d.name }))]}
              />
            )}
          </div>
          {chooseIndicators && (
            <div className="flex max-h-[180px] flex-col gap-1 overflow-y-auto rounded-lg bg-background-primary-default p-2">
              {(indicators.data?.items ?? [])
                .filter((ind) => ind.default_scheme)
                .map((ind) => (
                  <Checkbox
                    key={ind.id}
                    size="sm"
                    isSelected={picked.has(ind.id)}
                    onChange={(on) => {
                      const next = new Set(picked);
                      if (on) next.add(ind.id);
                      else next.delete(ind.id);
                      setPicked(next);
                    }}
                  >
                    <span className="font-mono text-caption-1-medium text-text-secondary">{ind.code}</span> {i18n.locale === "en-US" && ind.name_en ? ind.name_en : ind.name}
                  </Checkbox>
                ))}
            </div>
          )}
          {onStrategy ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <Input label={t("mon.window")} type="number" inputDir="ltr" value={windowDays} onChange={setWindowDays} />
              <Input label={t("mon.baseline")} type="number" inputDir="ltr" value={baselineDays} onChange={setBaselineDays} />
              <Input label={t("mon.minRequests")} type="number" inputDir="ltr" value={minRequests} onChange={setMinRequests} />
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              <Input label={`${t("mon.reference")} · ${t("mon.referenceStart")}`} placeholder="2026-01" inputDir="ltr" value={refStart} onChange={setRefStart} hint={t("mon.referenceAuto")} />
              <Input label={t("mon.referenceEnd")} placeholder="2026-06" inputDir="ltr" value={refEnd} onChange={setRefEnd} />
            </div>
          )}
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-2">
          <Input label={t("mon.warn")} type="number" inputDir="ltr" value={warn} onChange={setWarn} hint={t(`mon.thresholdHint.${kind}`)} isInvalid={invalid.includes("thresholds")} />
          <Input label={t("mon.alert")} type="number" inputDir="ltr" value={alert} onChange={setAlert} isInvalid={invalid.includes("thresholds")} />
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <SelectField className="w-[140px]" label={t("mon.schedule")} value={freq} onChange={(v) => setFreq(v as Freq)} options={FREQS.map((f) => ({ id: f, label: t(`mon.freq.${f}`) }))} />
          {freq === "weekly" && (
            <SelectField className="w-[120px]" label={t("mon.weekday")} value={weekday} onChange={setWeekday} options={["0", "1", "2", "3", "4", "5", "6"].map((d) => ({ id: d, label: t(`mon.weekdays.${d}`) }))} />
          )}
          {(freq === "daily" || freq === "weekly") && (
            <SelectField className="w-[96px]" label={t("mon.hour")} value={hour} onChange={setHour} options={HOURS.map((h) => ({ id: h, label: h.padStart(2, "0") }))} />
          )}
          {freq !== "manual" && (
            <SelectField className="w-[96px]" label={t("mon.minute")} value={minute} onChange={setMinute} options={[...new Set([...MINUTES, minute])].map((m) => ({ id: m, label: m.padStart(2, "0") }))} />
          )}
          <Switch isSelected={enabled} onChange={setEnabled} className="mb-2">
            {t("mon.enabled")}
          </Switch>
        </div>

        <FormError message={error} />
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={save.isPending}>{editing ? t("common.save") : t("mon.create")}</Button>
        </div>
      </form>
    </Modal>
  );
}
