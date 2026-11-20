# kivi-ui 设计方案（v0.1 草案）

> 金融风控的「数据 → 指标 → 模型 → 策略 → 风控监控」一体化管理平台。
> 计算内核复用 [kivi](https://github.com/gchensy/kivi)（PyPI 包 `kivi`，分箱 / WOE / IV / PSI / 评分卡 / VIF），
> 前端视觉采用 [BoardUI](https://github.com/BoardUI/boardui)（MIT），后端 Python + Pydantic，数据库 PostgreSQL。

---

## 1. 目标与范围

| 目标 | 说明 |
| --- | --- |
| 一条链路管到底 | 样本数据接入 → 指标沉淀与分析 → 评分卡建模 → 策略配置与回测 → 实时决策 → 监控预警，每一步的产物都可追溯到上一步。 |
| 复用 kivi，不重写算法 | 平台只做「编排 + 存储 + 展示 + 治理」，所有统计计算调用 kivi 的公开 API，分箱规则、编码表用 kivi 自带的 `to_dict` / `save` JSON 格式持久化。 |
| 金融级治理 | 角色权限、版本化、提交—审批分离（四眼原则）、上线唯一版本、全量审计日志。 |
| 简单可运行 | 只依赖 PostgreSQL（任务队列也落在 Postgres），一条命令起开发环境，首次启动自带演示数据。 |

**不在 v1 范围内**：多租户、SSO/LDAP、外部数据库直连（只留接口）、流式特征计算、复杂可视化决策流画布。

---

## 2. 总体架构

```
            浏览器
              │  https（同源，Cookie 会话）
┌─────────────▼──────────────┐
│  web/  Next.js 16 + React 19│  BoardUI 源码组件 · Tailwind v4 · React Aria
│  TanStack Query · Recharts  │  /api/* 由 Next rewrites 反代到后端
└─────────────┬──────────────┘
              │ REST / JSON（OpenAPI → 前端 TS 类型自动生成）
┌─────────────▼──────────────────────────────────────────┐
│  backend/  FastAPI + Pydantic v2                         │
│  ┌────────┐ ┌──────────┐ ┌─────────┐ ┌───────────────┐  │
│  │ api/v1 │→│ services │→│ kivi    │ │ rule_engine   │  │
│  │ 路由    │ │ 业务逻辑  │ │ 计算内核 │ │ 策略/决策执行 │  │
│  └────────┘ └────┬─────┘ └─────────┘ └───────────────┘  │
│                  │ SQLAlchemy 2.0 + psycopg 3            │
│  worker.py ── 后台任务（分析/训练/回测/监控），Postgres 队列 │
└──────────────────┬─────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────┐
│ PostgreSQL 18                        │
│  schema public   平台元数据（用户/指标/模型/策略/日志…）│
│  schema kivi_data 样本数据表（上传的数据集落成物理表）  │
└─────────────────────────────────────┘
```

### 技术选型

| 层 | 选择 | 理由 |
| --- | --- | --- |
| Web 框架 | **FastAPI** | 原生基于 Pydantic v2，请求/响应模型即 OpenAPI 文档，前端可直接生成类型。 |
| 数据校验 | **Pydantic v2** + pydantic-settings | 所有入参、出参、配置、策略 DSL、规则 JSON 均用 Pydantic 模型定义和校验。 |
| ORM / 迁移 | SQLAlchemy 2.0（同步）+ Alembic | kivi / pandas 是同步计算，同步 ORM 更简单；耗时计算放 worker。 |
| 驱动 | psycopg 3 | Postgres 官方推荐驱动。 |
| 密码 / 会话 | argon2id（`argon2-cffi`）+ JWT（`PyJWT`），httpOnly Cookie | 无需额外会话存储。 |
| 计算 | **kivi**（PyPI 依赖 `kivi[analysis]>=0.3.0`，由 uv 装进 `backend/.venv`，不引用本地路径） | 分箱、WOE、IV、PSI、评分卡、VIF、ROC/KS、Lift 全部复用。 |
| 后台任务 | Postgres 任务表 + `SELECT … FOR UPDATE SKIP LOCKED` | 不引入 Redis/Celery，部署只要 Postgres。 |
| 前端 | Next.js 16（App Router）+ BoardUI 源码组件 | 与 BoardUI 原生工程一致，组件直接拷贝进项目可改。 |
| 数据请求 | TanStack Query + `openapi-typescript` 生成类型 | 后端 Pydantic schema 为唯一真相源。 |
| 图表 | Recharts（BoardUI 自带） | WOE 柱 + 坏率折线、PSI 柱、ROC、决策趋势。 |
| 包管理 | 后端 `uv`，前端 `pnpm` | 本机均已安装。 |

---

## 3. 功能模块

侧边栏一级导航（中文界面，`DirectionProvider locale="zh-CN"`）：

```
风控总览  ·  数据管理  ·  指标管理  ·  模型管理  ·  策略管理  ·  风控中心  ·  系统管理
```

### 3.1 账户与登录（P1）
- 登录（用户名或邮箱 + 密码）、注册、退出、修改密码、个人资料。
- 注册模式可配置 `SIGNUP_MODE = approval | open | closed`，**默认 approval**：自助注册后为「待激活」，管理员激活后以「分析师」身份登录。
- 管理员后台：创建账户、分配角色、禁用/启用、重置密码。
- 首个管理员通过命令行创建：`uv run kivi-ui create-admin`；演示环境自动生成。

### 3.2 风控总览（P1 先用演示数据出完整可视化，P5 接入真实数据）
- KPI 卡片（BoardUI Stat Cards）：今日决策量、通过率、拒绝率、人工审核率、在线模型数、未处理预警数。
- 图表卡：近 30 天决策量 & 通过率趋势；在线模型分数 PSI 走势；最新预警列表；待我审批列表。

### 3.3 数据管理（P2）
- **数据集**：上传 CSV / Parquet（BoardUI File Upload）→ 落库到 `kivi_data.ds_<id>`；或登记平台库内已有表 / 只读 SQL 视图。
- 字段角色标注：特征 / 目标（0/1）/ 主键 / 观察日期 / 样本划分列 / 忽略。
- 数据预览（BoardUI Data Grid，虚拟滚动）。
- **数据画像**：行数、坏样本率、逐列缺失率、唯一值、分布统计、单变量 AUC/KS —— 调用 `kivi.analysis.UnivariateAnalysis.summarize`。
- 样本划分：按日期切 训练 / 测试 / OOT，或按划分列。
- 外部数据源连接（基于 `kivi.sql.Database`，凭证加密存储）作为后续扩展，v1 只预留表结构。

### 3.4 指标管理（P2）
- **指标目录**：编码、中文名、分类（基础属性 / 征信 / 交易流水 / 行为 / 衍生）、数据类型、口径说明、来源（数据集.字段）、负责人、标签、状态（草稿 / 已发布 / 已下线）、版本。
- 一键「从数据集导入字段为指标」。
- **指标分析**（核心页面）：
  - 选择数据集 + 分箱方法（kivi `Binner.methods()`：quantile、uniform、tree、chi2、ks、mdlp、pava、optimal、iv_search、category、category_risk …）+ 箱数 + 单调约束 + 特殊值。
  - 输出分箱表（区间、样本数、坏样本、坏率、WOE、IV、分数、趋势）——`kivi.binning.bin_report`。
  - 图：WOE 柱 + 坏率折线；IV / KS / AUC / 缺失率卡片。
  - 支持手工调整切点（`method="manual"`）后重算，分析结果保存为一条「分箱方案」，规则以 `BinRule.to_dict()` 存 JSONB，可被模型直接引用。
- **稳定性**：选定参考样本与对比样本（或按月切片），用已保存的分箱规则计算 PSI —— `kivi.evaluate.psi_table`。
- **批量筛选**：对数据集所有特征批量分箱，按 IV、趋势、缺失率排序筛选 —— `BinningTable(trends=…, errors="collect")`。
- 衍生指标（窗口聚合，参考 `kivi.enterprise.EnterpriseIndicators` 的 3/6/9/12 月窗口）列为后续扩展。

### 3.5 模型管理（P3）
- **模型注册表**：模型编码、名称、类型（kivi 评分卡 / 逻辑回归 / 外部模型）、业务场景、负责人。每个模型下多个**版本**。
- **评分卡开发向导**（4 步，后台任务执行）：
  1. 选数据集、目标、样本划分；
  2. 选候选指标（展示 IV / 趋势 / 缺失率，可沿用指标的已保存分箱方案）；
  3. 共线性筛选（`VIFAnalysis.select(threshold=…)`）；
  4. 训练：`BinningTable.fit` → `transform(output="score")` → `LogisticScore.fit`。
- **版本详情**：入模变量 + 系数 + p 值；训练/测试/OOT 的 AUC、KS（`BinaryEvaluation`）；ROC 曲线；分数段 Lift、累计 KS、PSI（`LogisticScore.lift_compare`）；完整分箱编码表。
- **评分口径**：沿用 kivi —— 每个变量按 WOE 映射为 0–100 分（分高风险低），模型分 = 按归一化系数加权的变量分（0–100）；同时输出违约概率 `predict`。
- 模型产物：`BinningTable.save` 的 JSON + 系数，整体存 JSONB，不依赖 pickle，可审阅、可 diff。
- 批量打分：对任一数据集打分并下载结果。
- 生命周期：草稿 → 待审批 → 已批准 → 已上线 → 已下线；每个模型同时只有一个在线版本。

### 3.6 策略管理（P4）
- **策略**：编码、名称、场景（准入 / 反欺诈 / 授信额度 / 定价 / 贷中 / 催收）、负责人，下挂多个版本。
- **策略版本 = 有序规则集**，规则用结构化 JSON 条件（Pydantic 校验，不用 `eval`）：
  ```json
  {
    "code": "R003", "name": "低分且年轻客群拒绝", "priority": 30, "enabled": true,
    "when": {"all": [
      {"field": "model:SC_RETAIL.score", "op": "<", "value": 45},
      {"any": [
        {"field": "age", "op": "<", "value": 22},
        {"field": "phone", "op": "in_list", "value": "BL_PHONE"}
      ]}
    ]},
    "then": {"decision": "reject", "reason": "LOW_SCORE_YOUNG"}
  }
  ```
  - 运算符：`= != > >= < <= in not_in between is_null not_null in_list not_in_list`。
  - 输入字段：请求入参、指标、模型分（`model:<模型编码>.score|prob`，自动调用该模型的在线版本）、名单命中。
  - 决策合并：执行全部启用规则，取最严重结果（reject > review > pass），无命中则用默认决策；记录全部命中规则。
  - 额外支持「分数段决策表」规则类型：分数区间 → 决策 / 额度系数。
- **规则编辑器**：BoardUI Select / Input / Switch Card 组成的条件行，支持 AND/OR 分组嵌套、拖动排序、启停。
- **回测**：选数据集运行策略版本 → 通过率、拒绝率、每条规则命中率与独占命中率、通过客群坏率 vs 拒绝客群坏率；两个版本并排对比。规则引擎有向量化（pandas）与单条两种执行路径，共用同一套语义测试。
- 生命周期同模型；发布后的在线版本供决策接口使用。

### 3.7 风控中心（P4–P5）
- **实时决策接口**：`POST /api/v1/decide/{strategy_code}`，使用 API Token（服务账号）鉴权，返回决策、命中规则、模型分、耗时、决策流水号；在线策略与模型在进程内缓存。
- **决策记录**：分页查询、按决策/规则/时间筛选、查看单笔执行轨迹。
- **名单管理**：黑 / 白 / 灰名单，维度（身份证 / 手机号 / 设备 / IP / 企业统一社会信用代码），批量导入、有效期、原因。敏感值存 HMAC 摘要 + 脱敏展示（如 `138****1234`），原值不落库。
- **监控**：
  | 对象 | 指标 | 计算 | 默认阈值（预警 / 告警） |
  | --- | --- | --- | --- |
  | 指标 | PSI | 已保存分箱规则 + `psi_table` | 0.10 / 0.25 |
  | 模型 | 分数 PSI、AUC、KS | `lift_compare`、`BinaryEvaluation` | PSI 0.10 / 0.25；KS 下降 10% / 20% |
  | 策略 | 通过率、规则命中率 | 决策记录按窗口聚合 | 相对基线偏移 ±5pp / ±10pp |
  - 按 cron 由 worker 定时执行，也可手动运行；超阈值生成**预警**，进入预警中心（BoardUI Notification Center），可认领 / 处理 / 关闭。

### 3.8 系统管理（P1 起）
- 用户与角色、API Token、审计日志（谁在何时对什么对象做了什么，含前后差异）、系统参数（注册模式、阈值默认值）。

---

## 4. 账户、权限与安全

### 4.1 角色（两种固定角色）

| 功能 | admin 管理员 | analyst 分析师 |
| --- | --- | --- |
| 数据集、指标：查看、新建、分析 | ✓ | ✓ |
| 模型、策略：开发、回测、提交审批 | ✓ | ✓ |
| 模型、策略：审批、上线、下线 | ✓ | ✗ |
| 名单维护、监控配置、预警处理 | ✓ | ✓ |
| 用户管理、API Token、系统参数、审计日志 | ✓ | ✗ |

**四眼原则**：版本提交人不能审批自己的版本（开关 `REQUIRE_FOUR_EYES`，默认开启；只有一个管理员时可关闭）。

### 4.2 会话与安全措施
- 登录成功签发 JWT（8 小时，`sub` / `role` / `ver`），写入 `httpOnly; Secure; SameSite=Lax` Cookie；用户被禁用或改密后 `token_version` 自增，旧令牌失效。
- 前后端同源（Next rewrites），不开放跨域；所有写请求额外校验 `X-Requested-With` 头，配合 SameSite 防 CSRF。
- 密码 argon2id 哈希，长度 ≥ 8 且含字母与数字；连续 5 次失败锁定 15 分钟。
- API Token 仅存 SHA-256 摘要，明文只在创建时显示一次。
- 所有写操作写审计日志；名单敏感值 HMAC 存储。

---

## 5. 数据模型（schema `public`）

```
users              id uuid PK, username UQ, email UQ, display_name, password_hash,
                   role(admin|analyst), status(pending|active|disabled),
                   token_version, failed_logins, locked_until, last_login_at, created_at, updated_at
api_tokens         id, name, token_hash UQ, owner_id→users, scopes[], last_used_at, expires_at, revoked_at
audit_logs         id bigserial, actor_id, action, entity_type, entity_id, diff jsonb, ip, created_at

datasets           id, name, description, storage(upload|table|query), table_name, sql,
                   row_count, target_column, date_column, id_column, split jsonb,
                   owner_id, created_at, updated_at
dataset_columns    id, dataset_id→datasets, name, dtype, role(feature|target|id|date|split|ignore), stats jsonb
dataset_profiles   id, dataset_id, summary jsonb, created_by, created_at          -- UnivariateAnalysis 结果

indicators         id, code UQ, name, category, dtype, definition, source_dataset_id, source_column,
                   tags[], status(draft|published|retired), version, owner_id, created_at, updated_at
binning_schemes    id, indicator_id, dataset_id, method, params jsonb, rule jsonb (BinRule.to_dict),
                   bin_table jsonb, iv, ks, auc, missing_rate, trend, is_default, created_by, created_at
psi_results        id, indicator_id, scheme_id, reference jsonb, current jsonb, psi, table jsonb, created_at

models             id, code UQ, name, kind(scorecard|logistic|external), scene, description, owner_id, created_at
model_versions     id, model_id, version, status(draft|in_review|approved|online|retired),
                   dataset_id, target, split jsonb, features jsonb, encoder jsonb (BinningTable JSON),
                   coefficients jsonb, metrics jsonb (train/test/oot AUC KS + lift 表), notes,
                   created_by, submitted_at, approved_by, approved_at, online_at, retired_at
                   -- 部分唯一索引：每个 model 至多一个 status='online'

strategies         id, code UQ, name, scene, description, default_decision, owner_id, created_at
strategy_versions  id, strategy_id, version, status(同上), rules jsonb, model_refs jsonb, list_refs jsonb,
                   backtest jsonb, created_by, submitted_at, approved_by, approved_at, online_at
approvals          id, entity_type(model_version|strategy_version), entity_id, action(submit|approve|reject|online|retire),
                   actor_id, comment, created_at

risk_lists         id, code UQ, name, kind(black|white|gray), dimension(id_no|phone|device|ip|company), description
risk_list_items    id, list_id, value_hash, value_masked, reason, expires_at, created_by, created_at
                   -- UQ(list_id, value_hash)
decision_logs      id bigserial, request_id UQ, strategy_version_id, decision, hit_rules jsonb, scores jsonb,
                   input jsonb (敏感字段脱敏), latency_ms, created_at       -- 后续按月分区

monitors           id, name, target_type(indicator|model|strategy), target_id, metric, params jsonb,
                   thresholds jsonb, schedule (cron), enabled, next_run_at, created_by
monitor_runs       id, monitor_id, value, level(normal|warn|alert), detail jsonb, run_at
alerts             id, monitor_run_id, level, title, status(open|acknowledged|resolved),
                   assignee_id, resolved_by, resolved_at, note, created_at

jobs               id, kind(profile|binning|batch_binning|train|score|backtest|monitor), status(queued|running|done|failed),
                   params jsonb, result jsonb, error, progress, created_by, created_at, started_at, finished_at
```

样本数据放在 schema `kivi_data`（`ds_<uuid>` 物理表），与元数据隔离；后续可给该 schema 单独配只读角色。

---

## 6. API 设计（前缀 `/api/v1`，全部由 Pydantic 定义）

| 模块 | 端点 |
| --- | --- |
| 认证 | `POST auth/login` · `POST auth/signup` · `POST auth/logout` · `GET auth/me` · `PATCH auth/me` · `POST auth/password` |
| 用户 | `GET/POST users` · `PATCH users/{id}`（角色/状态）· `POST users/{id}/reset-password` · `GET/POST/DELETE api-tokens` |
| 数据 | `GET/POST datasets`（multipart 上传）· `GET/PATCH/DELETE datasets/{id}` · `GET datasets/{id}/preview` · `POST datasets/{id}/profile` · `PUT datasets/{id}/columns` |
| 指标 | `GET/POST indicators` · `POST indicators/import` · `GET/PATCH/DELETE indicators/{id}` · `POST indicators/{id}/binning` · `GET indicators/{id}/schemes` · `POST indicators/{id}/psi` · `POST indicators/batch-binning` |
| 模型 | `GET/POST models` · `GET/PATCH models/{id}` · `POST models/{id}/versions`（训练任务）· `GET model-versions/{id}` · `POST model-versions/{id}/{submit\|approve\|reject\|online\|retire}` · `POST model-versions/{id}/score` |
| 策略 | `GET/POST strategies` · `GET/PATCH strategies/{id}` · `POST strategies/{id}/versions` · `PUT strategy-versions/{id}/rules` · `POST strategy-versions/{id}/backtest` · `POST strategy-versions/{id}/{submit\|approve\|reject\|online\|retire}` |
| 决策 | `POST decide/{strategy_code}`（API Token）· `GET decisions` · `GET decisions/{request_id}` |
| 名单 | `GET/POST risk-lists` · `GET/POST/DELETE risk-lists/{id}/items` · `POST risk-lists/{id}/import` · `POST risk-lists/{id}/check` |
| 监控 | `GET/POST monitors` · `PATCH/DELETE monitors/{id}` · `POST monitors/{id}/run` · `GET monitors/{id}/runs` · `GET alerts` · `PATCH alerts/{id}` |
| 其他 | `GET dashboard/summary` · `GET audit-logs` · `GET jobs/{id}` · `GET kivi/methods`（可用分箱方法） |

列表接口统一 `?page=&size=&q=&sort=`，返回 `{items, total}`；错误统一 `{code, message, detail}`。耗时操作返回 `202 + job_id`，前端轮询 `jobs/{id}`。

---

## 7. 前端设计（BoardUI）

### 7.1 组件映射
| 平台界面 | BoardUI 组件 |
| --- | --- |
| 登录 / 注册 | `auth-card`（去掉第三方登录，仅账号密码）、`input`、`button` |
| 应用框架 | `dashboard-sidebar`（浮动侧栏）、`dashboard-user-menu`、`app-shell`、`breadcrumb`、`theme-toggle`（明暗主题）、`notification-bell`（预警） |
| 列表页 | `data-table`（TanStack，排序/选择/分页）、`chip` / `status-dot`（状态）、`badge`、`pagination` |
| 数据预览 | `data-grid`（虚拟滚动） |
| 上传 | `file-upload` |
| 表单 | `select`、`input`、`textarea`、`segmented-control`、`switch-card`、`radio-card`、`slider`、`date-range-picker` |
| 指标 / 模型分析 | `tabs`、`stat-cards`、图表卡（以 `revenue-chart-card` / `orders-chart-card` 为模板改为 WOE、PSI、ROC、Lift 图） |
| 规则编辑 | `select` + `input` 条件行、`tree-view`（规则分组树）、`switch`（启停） |
| 预警中心 | `notification-center` |
| 个人设置 | `settings-modal`（资料 / 修改密码 / 外观） |

遵循 BoardUI `AGENTS.md`：只用语义色 token 和组合字体类，`cx()` 合并类名，图标用 `@remixicon/react`。BoardUI 源码按 MIT 许可拷入 `web/components/`，保留版权声明。

### 7.2 路由
```
/login  /signup
/                         风控总览
/data/datasets            数据集列表        /data/datasets/[id]    预览 · 字段 · 画像
/indicators               指标目录          /indicators/[id]       口径 · 分箱分析 · 稳定性 · 被引用
/indicators/screening     批量分箱筛选
/models                   模型列表          /models/new            评分卡向导
/models/[id]              版本列表          /models/[id]/v/[ver]   指标 · 系数 · 效果 · 审批记录
/strategies               策略列表          /strategies/[id]/v/[ver] 规则编辑 · 回测 · 审批记录
/risk/decisions           决策记录          /risk/lists            名单管理
/risk/monitors            监控配置          /risk/alerts           预警中心
/admin/users  /admin/tokens  /admin/audit
```
未登录访问任何页面重定向 `/login`（Next middleware 检查 Cookie + 客户端 `auth/me`）；按角色隐藏无权限入口，后端为最终鉴权。

---

## 8. 关键流程

**评分卡从开发到上线**
```
上传数据集 → 标注目标/日期 → 画像 → 导入字段为指标 → 指标分箱/IV 筛选
→ 评分卡向导（VIF → BinningTable → LogisticScore）→ 版本(草稿)
→ 提交审批 → 管理员审阅效果与分箱 → 批准 → 上线（旧在线版本自动下线）
→ 自动创建该模型的分数 PSI 监控
```

**策略发布与决策**
```
新建策略版本 → 编辑规则（引用在线模型分、名单）→ 选数据集回测 / 与在线版本对比
→ 提交 → 审批 → 上线 → 业务系统携 API Token 调 /decide/{code}
→ 决策记录落库 → 监控通过率/命中率 → 超阈值生成预警
```

---

## 9. 仓库结构

```
kivi-ui/
├── README.md
├── docs/design.md
├── docker-compose.yml          # postgres + backend + worker + web
├── scripts/dev-db.sh           # 用本机 PG18 在 .pgdata/ 起项目私有实例（端口 5433，无需 sudo）
├── backend/
│   ├── pyproject.toml          # uv；依赖 kivi[analysis]>=0.3.0（PyPI），装入 backend/.venv
│   ├── alembic/
│   ├── app/
│   │   ├── main.py             # FastAPI 应用、路由注册、异常处理
│   │   ├── cli.py              # create-admin / seed-demo
│   │   ├── worker.py           # 任务队列消费 + 监控调度
│   │   ├── core/               # config(pydantic-settings) · security · deps(当前用户/角色)
│   │   ├── db/                 # engine · session · base
│   │   ├── models/             # SQLAlchemy ORM
│   │   ├── schemas/            # Pydantic 请求/响应、规则 DSL
│   │   ├── api/v1/             # 各模块路由
│   │   └── services/           # analysis(kivi 封装) · scorecard · rule_engine · backtest · monitoring · audit
│   └── tests/                  # pytest，独立测试库
└── web/
    ├── package.json            # Next 16 · React 19 · Tailwind 4 · react-aria-components · TanStack · recharts
    ├── app/(auth)/…  app/(app)/…
    ├── components/base|application|foundations/   # BoardUI 源码
    ├── components/kivi/        # 平台自有组件（WOE 图、规则编辑器…）
    ├── lib/api.ts  lib/api-types.ts(生成)
    └── styles/                 # BoardUI theme / typography / globals
```

---

## 10. 开发与部署

- **开发**：`scripts/dev-db.sh` 用本机已安装的 PostgreSQL 18 在项目目录初始化私有实例（不改系统服务）；`uv run alembic upgrade head && uv run kivi-ui seed-demo`；`uv run uvicorn app.main:app --reload`；`uv run kivi-ui worker`；`pnpm dev`。
- **演示数据**：用 kivi 内置 `Dataset.bank_data()` 和 `EnterpriseSample.simulate()` 生成两个数据集、一批指标与分箱方案、一个已上线的评分卡、一条准入策略、近 30 天模拟决策记录和几条预警，首次打开即有完整链路可看。
- **部署**：`docker compose up`（postgres:18、backend、worker、web）。
- **测试**：后端 pytest（认证/权限/四眼原则、规则引擎两条执行路径一致性、kivi 封装结果与直接调用一致）；前端 `tsc --noEmit`；端到端在浏览器中走通登录 → 指标分析 → 建模 → 策略回测。

---

## 11. 分期交付

| 期 | 内容 | 可验收结果 |
| --- | --- | --- |
| **P1 骨架、账户与可视化** | 仓库、Postgres、迁移、登录/注册/退出/改密、用户管理、审计、BoardUI 应用框架；风控总览用 kivi 在演示样本上实算：KPI、指标 IV 排行、WOE 与坏率图、ROC/KS、分数分布、月度 PSI、模拟决策趋势 | 能注册 → 管理员激活 → 登录 → 看到完整的风控总览图表 |
| **P2 数据与指标** | 数据集上传/预览/画像、指标目录、单指标分箱分析、PSI、批量筛选、任务队列 | 上传 bank 数据，看到 age 的 WOE/IV 图表并保存分箱方案 |
| **P3 模型** | 评分卡向导、版本详情（AUC/KS/ROC/Lift）、审批与上线、批量打分 | 训练评分卡并走完提交—审批—上线 |
| **P4 策略与决策** | 规则 DSL 与编辑器、回测与版本对比、名单、决策 API、决策记录、API Token | 用 curl 调决策接口得到命中规则与模型分 |
| **P5 监控与总览** | 监控配置与调度、预警中心、风控总览真实数据 | 改动样本触发 PSI 预警并在总览出现 |

每期结束都能独立运行，并在浏览器里实际走通后再进入下一期。

---

## 12. 已确认事项

1. 注册需管理员激活（`SIGNUP_MODE=approval`），激活后为分析师。
2. 角色只保留管理员、分析师两种。
3. 评分沿用 kivi 0–100 分口径（分高风险低），PDO 刻度作为可选展示。
4. 前端用 Next.js，与 BoardUI 一致。
5. kivi 以 PyPI 包形式装入后端 `.venv`，不引用本地路径。
6. 按 P1→P5 逐期交付；初期以好看、可交互的可视化为首要目标。
7. 代码托管在 GitHub `gchensy/kivi-ui`。
