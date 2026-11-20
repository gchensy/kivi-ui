"use client";

import {
  RiAddLine,
  RiArrowDownLine,
  RiArrowUpLine,
  RiCheckboxCircleFill,
  RiCloseCircleFill,
  RiDeleteBinLine,
  RiFolderAddLine,
} from "@remixicon/react";
import { useEffect, useId, useState } from "react";

import { Chip } from "@/components/base/badges/chip";
import { Button } from "@/components/base/buttons/button";
import { SegmentedControl, SegmentedControlItem } from "@/components/base/segmented-control/segmented-control";
import { Switch } from "@/components/base/switch/switch";
import { useI18n } from "@/lib/i18n/provider";
import type { Decision, FieldOptions, RuleCondition, RuleGroup, RuleOp, RuleSpec, StrategyDefinition, TraceNode, TraceRule } from "@/lib/types";
import { cx } from "@/utils/cx";

const OPS: RuleOp[] = ["eq", "ne", "gt", "ge", "lt", "le", "between", "in", "not_in", "is_null", "not_null", "in_list", "not_in_list"];
const DECISIONS: Decision[] = ["pass", "review", "reject"];
export const DECISION_CHIP: Record<Decision, "lime" | "yellow" | "rose"> = { pass: "lime", review: "yellow", reject: "rose" };
const FIELD = "h-8 min-w-0 rounded-lg bg-background-tertiary-default px-2 text-body-2-regular text-text-primary outline-none placeholder:text-text-placeholder focus-visible:ring-2 focus-visible:ring-border-focus-ring disabled:opacity-60";

const isGroup = (item: RuleCondition | RuleGroup): item is RuleGroup => "items" in item;

function numberOrText(text: string, numeric: boolean): unknown {
  const trimmed = text.trim();
  if (numeric && trimmed !== "" && Number.isFinite(Number(trimmed))) return Number(trimmed);
  return trimmed;
}

function defaultValue(op: RuleOp): unknown {
  if (op === "between") return [0, 1];
  if (op === "in" || op === "not_in") return [""];
  if (op === "is_null" || op === "not_null") return null;
  if (op === "in_list" || op === "not_in_list") return "";
  if (["gt", "ge", "lt", "le"].includes(op)) return 0;
  return "";
}

/** Text box that keeps what the user typed and reports parsed values. */
function ValueText({ value, onChange, numeric, placeholder, className }: { value: unknown; onChange: (v: unknown) => void; numeric: boolean; placeholder?: string; className?: string }) {
  const [text, setText] = useState(value === null || value === undefined ? "" : String(value));
  useEffect(() => {
    const parsed = numberOrText(text, numeric);
    if (parsed !== value && String(parsed) !== String(value ?? "")) setText(value === null || value === undefined ? "" : String(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);
  return (
    <input
      className={cx(FIELD, className)}
      value={text}
      placeholder={placeholder}
      inputMode={numeric ? "decimal" : undefined}
      onChange={(e) => {
        setText(e.target.value);
        onChange(numberOrText(e.target.value, numeric));
      }}
    />
  );
}

function ConditionRow({
  condition,
  onChange,
  onRemove,
  options,
  datalist,
}: {
  condition: RuleCondition;
  onChange: (c: RuleCondition) => void;
  onRemove: () => void;
  options: FieldOptions | undefined;
  datalist: string;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const known = options?.fields.find((f) => f.name === condition.field);
  const numeric = known ? known.dtype === "numeric" : condition.field.startsWith("model:");
  const op = condition.op;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <input
        className={cx(FIELD, "w-[220px] font-mono")}
        list={datalist}
        value={condition.field}
        placeholder={t("stg.field")}
        aria-label={t("stg.field")}
        onChange={(e) => onChange({ ...condition, field: e.target.value })}
      />
      <select
        className={cx(FIELD, "w-[120px]")}
        aria-label={t("stg.op")}
        value={op}
        onChange={(e) => {
          const next = e.target.value as RuleOp;
          onChange({ ...condition, op: next, value: defaultValue(next) });
        }}
      >
        {OPS.map((o) => (
          <option key={o} value={o}>{t(`stg.ops.${o}`)}</option>
        ))}
      </select>
      {op === "between" ? (
        <span className="flex items-center gap-1">
          {[0, 1].map((i) => (
            <ValueText
              key={i}
              className="w-[90px]"
              numeric
              value={(condition.value as number[] | undefined)?.[i] ?? ""}
              onChange={(v) => {
                const pair = [...((condition.value as number[]) ?? [0, 1])];
                pair[i] = typeof v === "number" ? v : 0;
                onChange({ ...condition, value: pair });
              }}
            />
          ))}
        </span>
      ) : op === "in" || op === "not_in" ? (
        <ValueText
          className="w-[220px]"
          numeric={false}
          placeholder={t("stg.valuesHint")}
          value={(condition.value as unknown[] | undefined)?.join(", ") ?? ""}
          onChange={(v) =>
            onChange({ ...condition, value: String(v).split(/[,，]/).map((x) => numberOrText(x, numeric)).filter((x) => x !== "") })
          }
        />
      ) : op === "in_list" || op === "not_in_list" ? (
        <select className={cx(FIELD, "w-[220px]")} aria-label={t("stg.pickList")} value={String(condition.value ?? "")} onChange={(e) => onChange({ ...condition, value: e.target.value })}>
          <option value="">{t("stg.pickList")}</option>
          {(options?.lists ?? []).map((l) => (
            <option key={l.code} value={l.code}>
              {l.code} · {i18n.locale === "en-US" && l.name_en ? l.name_en : l.name}
            </option>
          ))}
        </select>
      ) : op === "is_null" || op === "not_null" ? null : (
        <ValueText className="w-[140px]" numeric={numeric || ["gt", "ge", "lt", "le"].includes(op)} value={condition.value} onChange={(v) => onChange({ ...condition, value: v })} />
      )}
      <button type="button" aria-label={t("stg.remove")} onClick={onRemove} className="flex size-8 cursor-pointer items-center justify-center rounded-lg text-foreground-icon-tertiary hover:bg-background-secondary-hover hover:text-foreground-icon-primary">
        <RiCloseCircleFill className="size-4" aria-hidden />
      </button>
    </div>
  );
}

function GroupEditor({ group, onChange, onRemove, depth, options, datalist }: { group: RuleGroup; onChange: (g: RuleGroup) => void; onRemove?: () => void; depth: number; options: FieldOptions | undefined; datalist: string }) {
  const { t } = useI18n();
  const update = (index: number, item: RuleCondition | RuleGroup | null) => {
    const items = [...group.items];
    if (item === null) items.splice(index, 1);
    else items[index] = item;
    onChange({ ...group, items });
  };
  return (
    <div className={cx("flex flex-col gap-2", depth > 0 && "rounded-xl border border-dashed border-border-button-default p-2.5")}>
      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl aria-label="mode" selectedKeys={new Set([group.mode])} onSelectionChange={(keys) => onChange({ ...group, mode: ([...keys][0] as "all" | "any") ?? "all" })}>
          <SegmentedControlItem id="all">{t("stg.all")}</SegmentedControlItem>
          <SegmentedControlItem id="any">{t("stg.any")}</SegmentedControlItem>
        </SegmentedControl>
        <Button size="xs" variant="ghost" leadingIcon={RiAddLine} onClick={() => onChange({ ...group, items: [...group.items, { field: "", op: "eq", value: "" }] })}>
          {t("stg.addCondition")}
        </Button>
        {depth < 2 && (
          <Button size="xs" variant="ghost" leadingIcon={RiFolderAddLine} onClick={() => onChange({ ...group, items: [...group.items, { mode: "any", items: [{ field: "", op: "eq", value: "" }] }] })}>
            {t("stg.addGroup")}
          </Button>
        )}
        {onRemove && (
          <Button size="xs" variant="ghost" leadingIcon={RiDeleteBinLine} onClick={onRemove}>
            {t("stg.remove")}
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-1.5 border-s-2 border-separator-border ps-3">
        {group.items.map((item, i) =>
          isGroup(item) ? (
            <GroupEditor key={i} group={item} depth={depth + 1} options={options} datalist={datalist} onChange={(g) => update(i, g)} onRemove={() => update(i, null)} />
          ) : (
            <ConditionRow key={i} condition={item} options={options} datalist={datalist} onChange={(c) => update(i, c)} onRemove={() => update(i, null)} />
          ),
        )}
      </div>
    </div>
  );
}

/** A sentence for a condition: "age < 20", "phone on watchlist BL_PHONE". */
function conditionText(c: RuleCondition, t: (key: string) => string): string {
  const v = c.value;
  if (c.op === "is_null" || c.op === "not_null") return `${c.field} ${t(`stg.ops.${c.op}`)}`;
  if (c.op === "between" && Array.isArray(v)) return `${c.field} ${t("stg.ops.between")} ${v[0]} – ${v[1]}`;
  if (Array.isArray(v)) return `${c.field} ${t(`stg.ops.${c.op}`)} ${v.join(", ")}`;
  return `${c.field} ${t(`stg.ops.${c.op}`)} ${String(v)}`;
}

function GroupText({ group }: { group: RuleGroup }) {
  const { t } = useI18n();
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      {group.items.map((item, i) => (
        <span key={i} className="inline-flex items-center gap-1">
          {i > 0 && <span className="text-caption-1-semibold text-text-tertiary">{group.mode === "all" ? "AND" : "OR"}</span>}
          {isGroup(item) ? (
            <span className="inline-flex items-center gap-1 rounded-lg bg-background-tertiary-default px-1.5 py-0.5">
              ( <GroupText group={item} /> )
            </span>
          ) : (
            <code className="rounded-md bg-background-tertiary-default px-1.5 py-0.5 font-mono text-caption-1-medium text-text-primary">{conditionText(item, t)}</code>
          )}
        </span>
      ))}
    </span>
  );
}

export function RulesView({ definition }: { definition: StrategyDefinition }) {
  const i18n = useI18n();
  const { t } = i18n;
  return (
    <div className="flex flex-col gap-2">
      {definition.rules.map((rule, index) => (
        <div key={rule.code} className={cx("flex flex-col gap-1.5 rounded-xl bg-background-primary-default p-3 shadow-card", !rule.enabled && "opacity-50")}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-caption-1-semibold text-text-tertiary tabular-nums">#{index + 1}</span>
            <code className="font-mono text-caption-1-semibold text-text-secondary">{rule.code}</code>
            <span className="text-body-2-medium text-text-primary">{i18n.locale === "en-US" && rule.name_en ? rule.name_en : rule.name}</span>
            <Chip variant="subtle" color={DECISION_CHIP[rule.decision]}>{t(`stg.decisions.${rule.decision}`)}</Chip>
            {rule.terminal && <Chip variant="subtle" color="purple">{t("stg.terminal")}</Chip>}
            {rule.reason && <span className="font-mono text-caption-1-regular text-text-tertiary">{rule.reason}</span>}
          </div>
          <GroupText group={rule.when} />
        </div>
      ))}
      <p className="text-body-2-regular text-text-tertiary">
        {t("stg.defaultDecision")} → <Chip variant="subtle" color={DECISION_CHIP[definition.default_decision]}>{t(`stg.decisions.${definition.default_decision}`)}</Chip>
      </p>
    </div>
  );
}

export function RulesEditor({ definition, onChange, options }: { definition: StrategyDefinition; onChange: (d: StrategyDefinition) => void; options: FieldOptions | undefined }) {
  const { t } = useI18n();
  const datalist = useId();
  const setRule = (index: number, rule: RuleSpec | null) => {
    const rules = [...definition.rules];
    if (rule === null) rules.splice(index, 1);
    else rules[index] = rule;
    onChange({ ...definition, rules });
  };
  const move = (index: number, delta: number) => {
    const rules = [...definition.rules];
    const [rule] = rules.splice(index, 1);
    rules.splice(index + delta, 0, rule);
    onChange({ ...definition, rules });
  };
  const nextCode = () => {
    let n = definition.rules.length + 1;
    while (definition.rules.some((r) => r.code === `R${String(n).padStart(2, "0")}`)) n += 1;
    return `R${String(n).padStart(2, "0")}`;
  };
  return (
    <div className="flex flex-col gap-3">
      <datalist id={datalist}>
        {(options?.fields ?? []).map((f) => (
          <option key={f.name} value={f.name}>{f.label ?? ""}</option>
        ))}
      </datalist>
      {definition.rules.map((rule, index) => (
        <div key={index} className={cx("flex flex-col gap-3 rounded-xl bg-background-primary-default p-3 shadow-card", !rule.enabled && "opacity-70")}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-caption-1-semibold text-text-tertiary tabular-nums">#{index + 1}</span>
            <input className={cx(FIELD, "w-[72px] font-mono")} aria-label={t("stg.ruleCode")} value={rule.code} onChange={(e) => setRule(index, { ...rule, code: e.target.value })} />
            <input className={cx(FIELD, "w-[200px]")} aria-label={t("stg.ruleName")} placeholder={t("stg.ruleName")} value={rule.name} onChange={(e) => setRule(index, { ...rule, name: e.target.value })} />
            <input className={cx(FIELD, "w-[180px]")} aria-label={t("stg.ruleNameEn")} placeholder={t("stg.ruleNameEn")} value={rule.name_en ?? ""} onChange={(e) => setRule(index, { ...rule, name_en: e.target.value || null })} />
            <select className={cx(FIELD, "w-[110px]")} aria-label={t("dec.decision")} value={rule.decision} onChange={(e) => setRule(index, { ...rule, decision: e.target.value as Decision })}>
              {DECISIONS.map((d) => (
                <option key={d} value={d}>{t(`stg.decisions.${d}`)}</option>
              ))}
            </select>
            <input className={cx(FIELD, "w-[120px] font-mono")} aria-label={t("stg.reason")} placeholder={t("stg.reason")} value={rule.reason} onChange={(e) => setRule(index, { ...rule, reason: e.target.value })} />
            <span className="ms-auto flex items-center gap-3">
              <span title={t("stg.terminalHint")}>
                <Switch size="sm" isSelected={rule.terminal} onChange={(on) => setRule(index, { ...rule, terminal: on })}>
                  {t("stg.terminal")}
                </Switch>
              </span>
              <Switch size="sm" isSelected={rule.enabled} onChange={(on) => setRule(index, { ...rule, enabled: on })}>
                {t("stg.enabled")}
              </Switch>
              <span className="flex items-center">
                <Button size="xs" variant="ghost" iconOnly leadingIcon={RiArrowUpLine} aria-label={t("stg.moveUp")} disabled={index === 0} onClick={() => move(index, -1)} />
                <Button size="xs" variant="ghost" iconOnly leadingIcon={RiArrowDownLine} aria-label={t("stg.moveDown")} disabled={index === definition.rules.length - 1} onClick={() => move(index, 1)} />
                <Button size="xs" variant="ghost" iconOnly leadingIcon={RiDeleteBinLine} aria-label={t("stg.remove")} onClick={() => setRule(index, null)} />
              </span>
            </span>
          </div>
          <GroupEditor group={rule.when} depth={0} options={options} datalist={datalist} onChange={(when) => setRule(index, { ...rule, when })} />
        </div>
      ))}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button
          variant="secondary"
          leadingIcon={RiAddLine}
          onClick={() =>
            onChange({
              ...definition,
              rules: [...definition.rules, { code: nextCode(), name: "", name_en: null, enabled: true, decision: "reject", terminal: false, reason: "", when: { mode: "all", items: [{ field: "", op: "eq", value: "" }] } }],
            })
          }
        >
          {t("stg.addRule")}
        </Button>
        <label className="flex items-center gap-2 text-body-2-medium text-text-secondary">
          {t("stg.defaultDecision")}
          <select className={cx(FIELD, "w-[120px]")} value={definition.default_decision} onChange={(e) => onChange({ ...definition, default_decision: e.target.value as Decision })}>
            {DECISIONS.map((d) => (
              <option key={d} value={d}>{t(`stg.decisions.${d}`)}</option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}

function TraceLeaf({ node }: { node: TraceNode }) {
  const { t } = useI18n();
  if (node.items) {
    return (
      <div className="flex flex-col gap-1 border-s-2 border-separator-border ps-2.5">
        <span className="text-caption-1-semibold text-text-tertiary">{node.mode === "all" ? "AND" : "OR"}</span>
        {node.items.map((child, i) => (
          <TraceLeaf key={i} node={child} />
        ))}
      </div>
    );
  }
  const Icon = node.result ? RiCheckboxCircleFill : RiCloseCircleFill;
  return (
    <div className="flex flex-wrap items-center gap-2 text-body-2-regular">
      <Icon className="size-4 shrink-0" style={{ color: node.result ? "var(--viz-critical)" : "var(--viz-neutral)" }} aria-label={node.result ? t("stg.hit") : t("stg.miss")} />
      <code className="font-mono text-caption-1-medium text-text-primary">
        {conditionText({ field: node.field ?? "", op: node.op ?? "eq", value: node.value }, t)}
      </code>
      <span className="text-caption-1-regular text-text-tertiary">
        {t("stg.actual")}: <span className="font-mono text-text-secondary">{node.actual === null || node.actual === undefined ? "∅" : String(node.actual)}</span>
      </span>
    </div>
  );
}

/** Rule-by-rule execution trace; hits are marked, misses recede. */
export function TraceView({ trace, emptyHint }: { trace: TraceRule[]; emptyHint?: string }) {
  const i18n = useI18n();
  const { t } = i18n;
  return (
    <ol className="flex flex-col gap-2">
      {trace.map((rule) => (
        <li key={rule.code} className={cx("flex flex-col gap-1.5 rounded-xl p-2.5", rule.hit ? "bg-background-primary-default shadow-card" : "opacity-70")}>
          <div className="flex flex-wrap items-center gap-2">
            {rule.hit ? (
              <RiCheckboxCircleFill className="size-4" style={{ color: `var(--viz-${rule.decision === "pass" ? "good" : rule.decision === "review" ? "warning" : "critical"})` }} aria-hidden />
            ) : (
              <RiCloseCircleFill className="size-4 text-foreground-icon-quaternary" aria-hidden />
            )}
            <code className="font-mono text-caption-1-semibold text-text-secondary">{rule.code}</code>
            <span className="text-body-2-medium text-text-primary">{i18n.locale === "en-US" && rule.name_en ? rule.name_en : rule.name}</span>
            <Chip variant="subtle" color={rule.hit ? DECISION_CHIP[rule.decision] : "neutral"}>{rule.hit ? t("stg.hit") : t("stg.miss")}</Chip>
            {rule.terminal && <Chip variant="subtle" color="purple">{t("stg.terminal")}</Chip>}
          </div>
          {rule.when ? <TraceLeaf node={rule.when} /> : emptyHint && rule.hit ? <p className="text-caption-1-regular text-text-tertiary">{emptyHint}</p> : null}
        </li>
      ))}
    </ol>
  );
}
