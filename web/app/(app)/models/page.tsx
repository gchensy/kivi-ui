"use client";

import { useState } from "react";

import { PageHeader } from "@/components/kivi/app-shell";
import { Legend } from "@/components/kivi/charts/kit";
import { KsCurveChart, RocChart, ScoreDistributionChart, SPLIT_COLOR } from "@/components/kivi/charts/models";
import { ChartPanel, DataTable, MetricSwitch, Panel } from "@/components/kivi/panel";
import { ErrorState, PageSkeleton } from "@/components/kivi/states";
import { bandLabel, binLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n/provider";
import { useAnalytics } from "@/lib/queries";

function MetricCard({ label, train, oot }: { label: string; train: number; oot: number }) {
  const i18n = useI18n();
  const f = (v: number) => i18n.num(v, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const change = oot - train;
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-background-secondary-default p-4">
      <p className="text-body-medium text-text-secondary">{label}</p>
      <div className="flex items-end gap-6">
        {([
          ["train", train],
          ["oot", oot],
        ] as const).map(([split, value]) => (
          <div key={split} className="flex flex-col gap-1">
            <span className="flex items-center gap-1.5 text-caption-1-medium text-text-tertiary">
              <span className="h-0.5 w-3 rounded-full" style={{ background: SPLIT_COLOR[split] }} aria-hidden />
              {i18n.t(split === "train" ? "models.trainShort" : "models.ootShort")}
            </span>
            <span className="text-display-4-medium text-text-primary">{f(value)}</span>
          </div>
        ))}
        <span className="ms-auto mb-1 rounded-full bg-background-primary-default px-2 py-0.5 text-body-2-medium text-text-secondary tabular-nums shadow-card">
          {change >= 0 ? "+" : ""}
          {f(change)}
        </span>
      </div>
    </section>
  );
}

export default function ModelsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const query = useAnalytics();
  const [bandMetric, setBandMetric] = useState<"share" | "bad_rate">("share");

  if (query.error) return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  if (!query.data) return <PageSkeleton />;
  const { model, meta } = query.data;
  const f3 = (v: number) => i18n.num(v, { minimumFractionDigits: 3, maximumFractionDigits: 3 });
  const splitLegend = (
    <Legend
      items={[
        { label: `${t("models.train")} ${i18n.month(meta.sample.train_months[0])}–${i18n.month(meta.sample.train_months[1])}`, color: SPLIT_COLOR.train, shape: "line" },
        { label: `${t("models.oot")} ${i18n.month(meta.sample.oot_months[0])}–${i18n.month(meta.sample.oot_months[1])}`, color: SPLIT_COLOR.oot, shape: "line" },
      ]}
    />
  );

  return (
    <>
      <PageHeader
        title={t("models.title")}
        subtitle={t("models.subtitle", { model: i18n.pick(model.name), version: model.version, features: model.features.length })}
        actions={
          <span className="flex items-center gap-2 rounded-xl bg-background-secondary-default px-3 py-2 text-body-2-regular text-text-secondary">
            <span className="text-body-2-semibold text-text-primary">{t("models.scale")}</span>
            {t("models.scaleText", { base: model.scale.base_score, odds: model.scale.base_odds, pdo: model.scale.pdo })}
          </span>
        }
      />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <MetricCard label="AUC" train={model.roc.train.auc} oot={model.roc.oot.auc} />
        <MetricCard label="KS" train={model.roc.train.ks} oot={model.roc.oot.ks} />
        <MetricCard label="Gini" train={model.roc.train.gini} oot={model.roc.oot.gini} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <ChartPanel
          title={t("models.roc")}
          description={t("models.rocDesc")}
          legend={splitLegend}
          chartClassName="h-[320px]"
          chart={<RocChart roc={model.roc} />}
          table={
            <DataTable
              columns={[
                { key: "fpr", label: "FPR", align: "end" },
                { key: "train", label: `TPR ${t("models.trainShort")}`, align: "end" },
                { key: "oot", label: `TPR ${t("models.ootShort")}`, align: "end" },
              ]}
              rows={model.roc.train.curve.map((p, i) => ({
                key: i,
                cells: { fpr: i18n.pct(p.fpr, 1), train: i18n.pct(p.tpr), oot: i18n.pct(model.roc.oot.curve[i]?.tpr) },
              }))}
            />
          }
        />
        <ChartPanel
          title={t("models.gains")}
          description={t("models.gainsDesc")}
          legend={
            <Legend
              items={[
                { label: t("models.cumBad"), color: "var(--viz-1)", shape: "line" },
                { label: t("models.cumGood"), color: "var(--viz-2)", shape: "line" },
              ]}
            />
          }
          chartClassName="h-[320px]"
          chart={<KsCurveChart gains={model.gains} />}
          table={
            <DataTable
              columns={[
                { key: "decile", label: t("models.decile") },
                { key: "range", label: t("models.scoreRange") },
                { key: "count", label: t("models.count"), align: "end" },
                { key: "rate", label: t("models.badRate"), align: "end" },
                { key: "bad", label: t("models.cumBad"), align: "end" },
                { key: "good", label: t("models.cumGood"), align: "end" },
                { key: "ks", label: "KS", align: "end" },
                { key: "lift", label: t("models.lift"), align: "end" },
              ]}
              rows={model.gains.map((g) => ({
                key: g.decile,
                cells: {
                  decile: g.decile,
                  range: `${g.min_score}–${g.max_score}`,
                  count: i18n.num(g.count),
                  rate: i18n.pct(g.bad_rate, 2),
                  bad: i18n.pct(g.cum_bad_pct),
                  good: i18n.pct(g.cum_good_pct),
                  ks: f3(g.ks),
                  lift: i18n.num(g.lift, { maximumFractionDigits: 2 }),
                },
              }))}
            />
          }
        />
      </div>

      <ChartPanel
        title={t("models.distribution")}
        description={bandMetric === "share" ? t("models.distributionDesc") : t("models.distributionBadDesc")}
        controls={
          <MetricSwitch
            label={t("models.distribution")}
            value={bandMetric}
            onChange={setBandMetric}
            options={[
              { id: "share", label: t("models.metricShare") },
              { id: "bad_rate", label: t("models.metricBadRate") },
            ]}
          />
        }
        legend={
          <Legend
            items={[
              { label: t("models.train"), color: SPLIT_COLOR.train },
              { label: t("models.oot"), color: SPLIT_COLOR.oot },
            ]}
          />
        }
        chart={<ScoreDistributionChart bands={model.bands} metric={bandMetric} />}
        table={
          <DataTable
            columns={[
              { key: "band", label: t("models.band") },
              { key: "trainShare", label: `${t("models.share")} · ${t("models.trainShort")}`, align: "end" },
              { key: "ootShare", label: `${t("models.share")} · ${t("models.ootShort")}`, align: "end" },
              { key: "trainBad", label: `${t("models.badRate")} · ${t("models.trainShort")}`, align: "end" },
              { key: "ootBad", label: `${t("models.badRate")} · ${t("models.ootShort")}`, align: "end" },
            ]}
            rows={model.bands.train.map((b, i) => ({
              key: b.band,
              cells: {
                band: bandLabel(b.lower, b.upper),
                trainShare: i18n.pct(b.share),
                ootShare: i18n.pct(model.bands.oot[i]?.share),
                trainBad: i18n.pct(b.bad_rate, 2),
                ootBad: i18n.pct(model.bands.oot[i]?.bad_rate, 2),
              },
            }))}
          />
        }
      />

      <Panel title={t("models.scorecard")} description={t("models.scorecardDesc")}>
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
          {model.scorecard.map((card) => {
            const max = Math.max(...card.bins.map((b) => b.points));
            const min = Math.min(...card.bins.map((b) => b.points));
            return (
              <div key={card.name} className="flex flex-col gap-2 rounded-xl bg-background-primary-default p-3 shadow-card">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-body-semibold text-text-primary">{i18n.pick(card.label)}</span>
                  <span className="shrink-0 text-caption-1-medium text-text-tertiary tabular-nums">
                    {t("models.coefficient")} {i18n.num(card.coefficient, { maximumFractionDigits: 3 })}
                  </span>
                </div>
                <ul className="flex flex-col gap-1">
                  {card.bins.map((b) => {
                    const width = max === min ? 100 : 12 + ((b.points - min) / (max - min)) * 88;
                    return (
                      <li key={String(b.code)} className="grid grid-cols-[minmax(0,1fr)_96px_36px] items-center gap-2 text-body-2-regular">
                        <span className="truncate text-text-secondary">{binLabel(b, card.unit, i18n)}</span>
                        <span className="h-1.5 rounded-full bg-background-tertiary-default" aria-hidden>
                          <span className="block h-1.5 rounded-full" style={{ width: `${width}%`, background: "var(--viz-1)" }} />
                        </span>
                        <span className="text-end text-body-2-semibold text-text-primary tabular-nums">{b.points}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      </Panel>
    </>
  );
}
