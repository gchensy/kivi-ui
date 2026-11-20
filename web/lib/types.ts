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
