/** Response shapes of the kivi-ui API (mirrors backend/kivi_ui/schemas.py and analytics). */

import type { Bilingual } from "./i18n/provider";

export type Role = "admin" | "analyst";
export type UserStatus = "pending" | "active" | "disabled";

export interface User {
  id: string;
  username: string;
  email: string;
  display_name: string;
  role: Role;
  status: UserStatus;
  locale: string;
  last_login_at: string | null;
  created_at: string;
}

export interface UserPage {
  items: User[];
  total: number;
  counts: Record<UserStatus, number>;
}

export interface AuditLog {
  id: number;
  actor: { id: string; username: string; display_name: string } | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  detail: Record<string, unknown>;
  ip: string | null;
  created_at: string;
}

export interface AuditPage {
  items: AuditLog[];
  total: number;
}

// ---- Analytics -------------------------------------------------------------------------------

export type IvLevel = "useless" | "weak" | "medium" | "strong" | "suspicious";
export type Trend = "increasing" | "decreasing" | "peak" | "valley" | "irregular" | "flat" | "unordered";
export type Unit = "count" | "ratio" | "cny" | "years" | null;
export type Level = "alert" | "warn";
export type Decision = "pass" | "review" | "reject";

export interface Bin {
  code: number | string;
  count: number;
  share: number;
  bad: number;
  good: number;
  bad_rate: number | null;
  woe: number;
  iv: number;
  missing?: boolean;
  lower?: number | null;
  upper?: number | null;
  label?: Bilingual;
}

export interface Indicator {
  name: string;
  label: Bilingual;
  kind: "numeric" | "category";
  unit: Unit;
  iv: number;
  level: IvLevel;
  trend: Trend;
  missing_rate: number;
  bins: Bin[];
  selected: boolean;
}

export interface Roc {
  auc: number;
  ks: number;
  gini: number;
  curve: { fpr: number; tpr: number }[];
}

export interface Band {
  band: number;
  lower: number | null;
  upper: number | null;
  count: number;
  share: number;
  bad: number;
  bad_rate: number | null;
}

export interface Gain {
  decile: number;
  min_score: number;
  max_score: number;
  count: number;
  bad: number;
  bad_rate: number;
  cum_bad_pct: number;
  cum_good_pct: number;
  ks: number;
  lift: number;
}

export interface ScorecardBin {
  code: number | string;
  lower?: number | null;
  upper?: number | null;
  missing?: boolean;
  label?: Bilingual;
  woe: number;
  points: number;
}

export interface Monthly {
  month: string;
  in_reference: boolean;
  applications: number;
  bad_rate: number;
  mean_score: number;
  score_psi: number;
  auc: number | null;
  ks: number | null;
  approval_rate: number;
}

export interface DailyDecision {
  date: string;
  pass: number;
  review: number;
  reject: number;
  total: number;
  approval_rate: number | null;
}

export interface RuleHit {
  code: string;
  label: Bilingual;
  decision: Decision;
  hits: number;
  hit_rate: number | null;
  exclusive: number;
}

// ---- P2: datasets and indicators ------------------------------------------------------------

export interface Person {
  id: string;
  username: string;
  display_name: string;
}

export type ColumnRole = "feature" | "target" | "id" | "date" | "ignore";
export type ColumnType = "numeric" | "category" | "datetime" | "text";

export interface DatasetColumn {
  position: number;
  name: string;
  column_name: string;
  dtype: ColumnType;
  role: ColumnRole;
  missing_rate: number;
  unique_count: number;
  iv: number | null;
  stats: {
    min?: number | string;
    max?: number | string;
    mean?: number;
    std?: number;
    p50?: number;
    top?: { value: string; share: number }[];
  };
}

export interface Dataset {
  id: string;
  name: string;
  description: string;
  source: "upload" | "demo" | "score";
  file_name: string | null;
  row_count: number;
  column_count: number;
  target_column: string | null;
  target_event: string | null;
  date_column: string | null;
  id_column: string | null;
  bad_rate: number | null;
  profile: { monthly?: { month: string; rows: number; bad_rate: number | null }[]; date_range?: [string, string] | null };
  owner: Person | null;
  created_at: string;
  updated_at: string;
}

export interface DatasetDetail extends Dataset {
  columns: DatasetColumn[];
  indicator_count: number;
}

export interface Preview {
  columns: string[];
  rows: (string | number | null)[][];
  total: number;
}

export type BinMethod = "quantile" | "uniform" | "chimerge" | "tree" | "monotonic" | "manual" | "category";

export interface BinSpec {
  method: BinMethod;
  bins: number;
  cuts: number[];
  special: number[];
  min_bin_share: number;
  direction: "auto" | "increasing" | "decreasing";
  alpha?: number | null;
}

export interface ScreeningRow {
  column: string;
  name: string;
  dtype: ColumnType;
  iv: number | null;
  level: IvLevel | null;
  trend: Trend | null;
  bins: number;
  missing_rate: number;
  note: string | null;
  indicator_id: string | null;
}

export interface RuleBin {
  code: string;
  kind: "interval" | "special" | "missing" | "category" | "other";
  lower?: number | null;
  upper?: number | null;
  value?: number | string;
  count: number;
  share: number;
  bad: number;
  good: number;
  bad_rate: number | null;
  woe: number;
  iv: number;
}

export interface BinningResult {
  bins: RuleBin[];
  iv: number;
  level: IvLevel;
  trend: Trend;
  missing_rate: number;
  rows: number;
  bad_rate: number;
  rule: Record<string, unknown>;
  notes: string[];
}

export interface Scheme {
  id: string;
  name: string;
  method: BinMethod;
  spec: BinSpec;
  rule: Record<string, unknown>;
  bins: RuleBin[];
  iv: number;
  trend: Trend;
  missing_rate: number;
  dataset_id: string | null;
  author: Person | null;
  created_at: string;
}

export type IndicatorCategory = "basic" | "application" | "credit" | "transaction" | "behavior" | "derived" | "other";
export type IndicatorStatus = "draft" | "published" | "retired";

export interface IndicatorItem {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  category: IndicatorCategory;
  description: string;
  kind: "numeric" | "category";
  unit: Unit;
  status: IndicatorStatus;
  column_name: string;
  dataset: { id: string; name: string; target_column: string | null; date_column: string | null; row_count: number } | null;
  default_scheme: { id: string; name: string; method: BinMethod; iv: number; trend: Trend; created_at: string } | null;
  owner: Person | null;
  created_at: string;
  updated_at: string;
}

export interface IndicatorDetail extends IndicatorItem {
  schemes: Scheme[];
}

export interface IndicatorPage {
  items: IndicatorItem[];
  total: number;
  counts: Partial<Record<IndicatorCategory, number>>;
}

export interface Stability {
  scheme_id: string;
  reference: [string, string];
  months: { month: string; rows: number; psi: number | null; bad_rate: number | null; in_reference: boolean; shares: Record<string, number> }[];
  bins: { code: string; kind: RuleBin["kind"]; lower?: number | null; upper?: number | null; value?: number | string }[];
}

// ---- P3: models ------------------------------------------------------------------------------

export type Scene = "application" | "behavior" | "collection" | "fraud" | "other";
export type VersionStatus = "training" | "failed" | "draft" | "in_review" | "approved" | "online" | "retired";
export type Split = "train" | "test" | "oot";

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  progress: number;
  error: string | null;
  result: Record<string, unknown>;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface VersionSummary {
  id: string;
  model_id: string;
  version: number;
  status: VersionStatus;
  dataset: { id: string; name: string; target_column: string | null; date_column: string | null; row_count: number } | null;
  feature_count: number;
  auc_train: number | null;
  auc_test: number | null;
  auc_oot: number | null;
  ks_train: number | null;
  ks_test: number | null;
  ks_oot: number | null;
  error: string | null;
  job_id: string | null;
  author: Person | null;
  created_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  online_at: string | null;
  retired_at: string | null;
}

export interface TrainConfig {
  oot_months: number;
  test_ratio: number;
  seed: number;
  iv_min: number;
  vif_max: number;
  p_max: number;
  require_positive: boolean;
  max_features: number;
  base_score: number;
  base_odds: number;
  pdo: number;
}

export interface ModelFeature {
  indicator_id: string;
  code: string;
  name: string;
  name_en: string | null;
  column: string;
  kind: "numeric" | "category";
  unit: Unit;
  coefficient: number;
  std_err: number;
  p_value: number;
  vif: number;
  iv: number;
  trend: Trend;
  psi: Partial<Record<Split, number>>;
  spec: BinSpec;
  bins: (RuleBin & { points: number })[];
}

export interface SplitEvaluation {
  rows: number;
  bad: number;
  bad_rate: number;
  period?: [string, string] | null;
  roc?: Roc;
  bands: Band[];
  psi?: number;
}

export interface TrainResult {
  features: ModelFeature[];
  intercept: number;
  scale: { base_score: number; base_odds: number; pdo: number; factor: number; offset: number };
  evaluation: Partial<Record<Split, SplitEvaluation>>;
  focus: Split;
  gains: Gain[];
  score_stats: { min: number; max: number; mean: number };
  band_cuts: number[];
  selection: {
    candidates: { code: string; name?: string; name_en?: string | null; iv: number | null; selected: boolean; reason: string | null; value?: number | null }[];
    steps: { rule: "iv" | "max_features" | "vif" | "sign" | "pvalue"; feature: string; value: number | null }[];
  };
  fit: { pseudo_r2: number; log_likelihood: number; aic: number; rows: number };
  notes: string[];
}

export interface VersionDetail extends VersionSummary {
  model: { id: string; code: string; name: string; name_en: string | null; scene: Scene };
  config: { indicator_ids: string[]; train: TrainConfig };
  result: TrainResult | Record<string, never>;
  notes: string;
  submitter: Person | null;
  approver: Person | null;
  reviews: { action: string; actor: Person | null; comment: string; created_at: string }[];
}

export interface RiskModel {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  scene: Scene;
  description: string;
  owner: Person | null;
  created_at: string;
  updated_at: string;
  version_count: number;
  online: VersionSummary | null;
  latest: VersionSummary | null;
}

export interface ModelDetail extends RiskModel {
  versions: VersionSummary[];
}

// ---- P4: strategies, watchlists, tokens, decisions --------------------------------------------

export type RuleOp = "eq" | "ne" | "gt" | "ge" | "lt" | "le" | "in" | "not_in" | "between" | "is_null" | "not_null" | "in_list" | "not_in_list";
export type StrategyScene = "admission" | "fraud" | "limit" | "pricing" | "behavior" | "collection" | "other";

export interface RuleCondition {
  field: string;
  op: RuleOp;
  value: unknown;
}

export interface RuleGroup {
  mode: "all" | "any";
  items: (RuleCondition | RuleGroup)[];
}

export interface RuleSpec {
  code: string;
  name: string;
  name_en?: string | null;
  enabled: boolean;
  decision: Decision;
  terminal: boolean;
  reason: string;
  when: RuleGroup;
}

export interface StrategyDefinition {
  default_decision: Decision;
  rules: RuleSpec[];
}

export interface BacktestRule {
  code: string;
  enabled: boolean;
  hits: number;
  hit_rate: number;
  exclusive: number;
  decisive: number;
  bad_rate: number | null;
}

export interface BacktestSummary {
  rows: number;
  missing_fields: string[];
  pass: number;
  review: number;
  reject: number;
  pass_rate: number;
  review_rate: number;
  reject_rate: number;
  bad_rate?: number | null;
  bad_rate_by_decision?: Record<Decision, number | null>;
  rules: BacktestRule[];
  monthly?: { month: string; rows: number; pass_rate: number; reject_rate: number; pass_bad_rate?: number | null }[];
}

export interface Backtest {
  dataset?: { id: string; name: string };
  summary?: BacktestSummary;
  ran_at?: string;
  seconds?: number;
  compare?: {
    version_id: string;
    version: number;
    summary: BacktestSummary;
    swap: { from: Decision; to: Decision; rows: number; bad_rate: number | null }[];
  };
}

export interface StrategyVersionSummary {
  id: string;
  strategy_id: string;
  version: number;
  status: VersionStatus;
  notes: string;
  author: Person | null;
  created_at: string;
  updated_at: string;
  submitted_at: string | null;
  approved_at: string | null;
  online_at: string | null;
  retired_at: string | null;
  rule_count: number;
  pass_rate: number | null;
}

export interface StrategyVersionDetail extends StrategyVersionSummary {
  strategy: { id: string; code: string; name: string; name_en: string | null; scene: StrategyScene };
  definition: StrategyDefinition;
  backtest: Backtest;
  submitter: Person | null;
  approver: Person | null;
  reviews: { action: string; actor: Person | null; comment: string; created_at: string }[];
}

export interface StrategyItem {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  scene: StrategyScene;
  description: string;
  owner: Person | null;
  created_at: string;
  updated_at: string;
  version_count: number;
  online: StrategyVersionSummary | null;
  latest: StrategyVersionSummary | null;
}

export interface StrategyDetail extends StrategyItem {
  versions: StrategyVersionSummary[];
}

export interface FieldOptions {
  fields: { name: string; label: string | null; dtype: string | null; source: "column" | "indicator" | "model" }[];
  models: { code: string; name: string; name_en: string | null; version: number }[];
  lists: { code: string; name: string; name_en: string | null; kind: ListKind; dimension: string }[];
}

export interface TraceNode {
  field?: string;
  op?: RuleOp;
  value?: unknown;
  actual?: unknown;
  mode?: "all" | "any";
  items?: TraceNode[];
  result: boolean;
}

export interface TraceRule {
  code: string;
  name: string;
  name_en: string | null;
  decision: Decision;
  terminal: boolean;
  hit: boolean;
  when: TraceNode | null;
}

export interface DecisionResult {
  request_id: string;
  decision: Decision;
  reason: string;
  rules: { code: string; name: string; name_en: string | null; decision: Decision }[];
  scores: Record<string, { score: number; probability: number }>;
  strategy: { code: string; version: number };
  missing_fields: string[];
  latency_ms: number;
  trace?: TraceRule[];
}

export type ListKind = "black" | "white" | "gray";

export interface RiskList {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
  kind: ListKind;
  dimension: string;
  description: string;
  owner: Person | null;
  created_at: string;
  updated_at: string;
  item_count: number;
  active_count: number;
}

export interface ListItem {
  id: number;
  value_masked: string;
  reason: string;
  expires_at: string | null;
  author: Person | null;
  created_at: string;
}

export interface ApiToken {
  id: string;
  name: string;
  prefix: string;
  owner: Person | null;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  token?: string;
}

export interface DecisionRow {
  request_id: string;
  strategy_code: string;
  version: number;
  decision: Decision;
  reason: string;
  hit_rules: string[];
  scores: Record<string, { score: number; probability: number }>;
  latency_ms: number;
  source: "api" | "console" | "demo";
  created_at: string;
}

export interface DecisionDetail extends DecisionRow {
  trace: TraceRule[];
  input: Record<string, unknown>;
}

// ---- P5: monitors, alerts, overview ----------------------------------------------------------

export type MonitorKind = "indicator_psi" | "score_psi" | "model_ks" | "approval_rate" | "rule_hit_rate";
export type MonitorLevel = "normal" | "warn" | "alert" | "error";
export type AlertStatus = "open" | "acknowledged" | "resolved";
export type Freq = "hourly" | "daily" | "weekly" | "manual";

export interface Schedule {
  freq: Freq;
  hour: number;
  minute: number;
  weekday: number;
}

export interface CodeRef {
  id: string;
  code: string;
  name: string;
  name_en: string | null;
}

export interface SeriesPoint {
  period: string;
  value: number | null;
  rows?: number;
  in_reference?: boolean;
  auc?: number | null;
  ks?: number | null;
  labelled?: number;
  bad_rate?: number | null;
  mean_score?: number | null;
  pass?: number;
  review?: number;
  reject?: number;
}

export interface Worst {
  code: string;
  name: string;
  name_en: string | null;
  value: number | null;
  decision?: Decision;
}

export interface WindowCounts {
  pass: number;
  review: number;
  reject: number;
  total: number;
  rate: number | null;
}

export interface RunFacts {
  code?: string;
  period?: string;
  reference?: [string, string];
  series?: SeriesPoint[];
  model?: { code: string; version: number };
  strategy?: { code: string; version?: number };
  worst?: Worst;
  indicators?: { code: string; name: string; name_en: string | null; values: (number | null)[]; latest: number | null }[];
  skipped?: { code: string; name: string; name_en: string | null; reason: "missing_column" | "no_scheme" }[];
  reference_metrics?: { auc: number | null; ks: number | null; labelled: number };
  auc?: number | null;
  ks?: number | null;
  window_days?: number;
  baseline_days?: number;
  current?: WindowCounts;
  baseline?: WindowCounts;
  current_total?: number;
  baseline_total?: number;
  rules?: { code: string; name: string; name_en: string | null; decision: Decision; current: number; baseline: number; shift: number }[];
  [key: string]: unknown;
}

export interface MonitorRun {
  id: number;
  trigger: "schedule" | "manual" | "seed";
  status: "done" | "failed";
  level: MonitorLevel;
  value: number | null;
  error: string | null;
  code?: string | null;
  seconds: number;
  created_at: string;
}

export interface MonitorRunDetail extends MonitorRun {
  detail: RunFacts;
}

export interface MonitorParams {
  indicator_ids?: string[];
  reference?: { start: string; end: string };
  window_days?: number;
  baseline_days?: number;
  min_requests?: number;
}

export interface MonitorItem {
  id: string;
  name: string;
  kind: MonitorKind;
  model: CodeRef | null;
  strategy: CodeRef | null;
  dataset: { id: string; name: string } | null;
  params: MonitorParams;
  thresholds: { warn: number; alert: number };
  schedule: Schedule;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  last_level: MonitorLevel | null;
  last_value: number | null;
  owner: Person | null;
  created_at: string;
  updated_at: string;
  trend: (number | null)[];
  alert: { id: number; status: AlertStatus; level: MonitorLevel } | null;
}

export interface MonitorDetail extends MonitorItem {
  latest: MonitorRunDetail | null;
  runs: MonitorRun[];
}

export interface AlertEvent {
  action: "opened" | "escalated" | "eased" | "acknowledged" | "resolved" | "recovered";
  at: string;
  level?: MonitorLevel;
  value?: number | null;
  note?: string;
  actor?: { id: string; display_name: string };
}

export interface AlertItem {
  id: number;
  monitor: { id: string; name: string; kind: MonitorKind; model: CodeRef | null; strategy: CodeRef | null; thresholds: { warn: number; alert: number } };
  run_id: number | null;
  status: AlertStatus;
  level: MonitorLevel;
  peak_level: MonitorLevel;
  value: number | null;
  threshold: number | null;
  detail: RunFacts;
  occurrences: number;
  first_seen_at: string;
  last_seen_at: string;
  assignee: Person | null;
  acknowledged_at: string | null;
  resolver: Person | null;
  resolved_at: string | null;
  resolution: "manual" | "recovered" | null;
  note: string;
  events: AlertEvent[];
}

export type AlertCounts = Record<AlertStatus | "warn" | "alert", number>;

export interface AlertPage {
  items: AlertItem[];
  total: number;
  counts: AlertCounts;
}

type Counts = Omit<DailyDecision, "date">;

export interface Overview {
  as_of: string;
  generated_at: string;
  timezone: string;
  decisions: { current: Counts; previous: Counts; daily: DailyDecision[]; sources: Record<string, number> };
  strategy: {
    id: string;
    code: string;
    name: Bilingual;
    version: number;
    version_id: string;
    decisions: Counts;
    rules: RuleHit[];
    effect: Record<Decision, number | null> | null;
    effect_dataset: string | null;
  } | null;
  model: {
    id: string;
    code: string;
    name: Bilingual;
    version: number;
    version_id: string;
    focus: Split;
    auc_train: number | null;
    ks_train: number | null;
    auc_focus: number | null;
    ks_focus: number | null;
  } | null;
  score_psi: { monitor_id: string; value: number | null; level: MonitorLevel; period: string | null; thresholds: { warn: number; alert: number }; ran_at: string } | null;
  alerts: { counts: AlertCounts; items: AlertItem[] };
  monitors: MonitorItem[];
}

export interface StabilityMonth {
  month: string;
  score_psi: number | null;
  auc: number | null;
  ks: number | null;
  rows: number | null;
  bad_rate: number | null;
  in_reference: boolean;
}

export interface StabilityView {
  models: { id: string; code: string; name: Bilingual }[];
  model: { id: string; code: string; name: Bilingual } | null;
  thresholds?: { warn: number; alert: number };
  ks_thresholds?: { warn: number; alert: number };
  reference?: [string, string] | null;
  reference_metrics?: { auc: number | null; ks: number | null; labelled: number } | null;
  months?: string[];
  monthly?: StabilityMonth[];
  feature_psi?: { name: string; label: Bilingual; values: (number | null)[] }[];
  monitors?: Partial<Record<MonitorKind, { id: string; name: string; level: MonitorLevel | null; value: number | null; ran_at: string | null }>>;
  alerts?: AlertItem[];
}
