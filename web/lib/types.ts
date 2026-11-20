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

export interface Alert {
  id: string;
  kind: "feature_psi" | "score_psi" | "ks_drop" | "approval_shift";
  level: Level;
  value: number;
  subject?: string;
  subject_label?: Bilingual;
  threshold?: number;
  month?: string;
  train?: number;
  oot?: number;
  current?: number;
  previous?: number;
}

export interface DailyDecision {
  date: string;
  pass: number;
  review: number;
  reject: number;
  total: number;
  approval_rate: number | null;
}

export interface Analytics {
  meta: {
    generated_at: string;
    as_of: string;
    engine: string;
    sample: {
      rows: number;
      bad_rate: number;
      months: string[];
      train_rows: number;
      oot_rows: number;
      train_months: [string, string];
      oot_months: [string, string];
      features: number;
    };
  };
  kpis: {
    applications_30d: number;
    applications_prev_30d: number;
    approval_rate_30d: number;
    approval_rate_prev_30d: number;
    review_rate_30d: number;
    reject_rate_30d: number;
    auc_oot: number;
    auc_train: number;
    ks_oot: number;
    ks_train: number;
    score_psi_latest: number;
    score_psi_oot: number;
    alerts: { alert: number; warn: number };
  };
  decisions: {
    daily: DailyDecision[];
    rules: { code: string; label: Bilingual; decision: Decision; hits: number; hit_rate: number; exclusive: number }[];
    effect: Record<Decision, number>;
    current: DailyDecision;
    previous: DailyDecision;
  };
  indicators: Indicator[];
  model: {
    code: string;
    name: Bilingual;
    version: string;
    features: string[];
    intercept: number;
    scale: { base_score: number; base_odds: number; pdo: number };
    scorecard: {
      name: string;
      label: Bilingual;
      unit: Unit;
      kind: "numeric" | "category";
      coefficient: number;
      bins: ScorecardBin[];
    }[];
    roc: { train: Roc; oot: Roc };
    bands: { train: Band[]; oot: Band[] };
    gains: Gain[];
    score_stats: { min: number; max: number; mean: number };
  };
  stability: {
    thresholds: { warn: number; alert: number };
    monthly: Monthly[];
    feature_psi: { name: string; label: Bilingual; values: (number | null)[] }[];
  };
  alerts: Alert[];
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
  source: "upload" | "demo";
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
