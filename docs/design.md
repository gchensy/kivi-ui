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
| 计算 | **kivi**（PyPI 依赖 `kivi>=0.4.0`，由 uv 装进 `backend/.venv`，不引用本地路径）+ scikit-learn | kivi 0.4 提供 `bin_edges`、`cut`（特殊值分组）、`chimerge_edges`、`tree_edges`、`monotonic_edges`、`woe_table`、`psi_table`；逻辑回归与 ROC 暂用 scikit-learn，kivi 提供评分卡建模接口后切换。 |
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

### 3.2 风控总览（P1 先用演示数据出完整可视化，P5 接入真实数据 ✅）
- P5 起全部来自真实数据（`GET /overview`），P1 的模拟快照（`analytics_snapshots`）已移除。
- KPI 卡片：近 30 天决策量与通过率（对比前 30 天，按 `KIVI_TIMEZONE` 的自然日）、在线模型 AUC/KS（OOT 对比训练集）、最新分数 PSI（来自该模型的分数 PSI 监控）、未解决预警数。
- 图表卡：每日决策；预警列表；流量最大的在线策略近 30 天规则命中与独占命中（来自决策记录的 `hit_rules`）；该策略在线版本的回测坏账率；各启用监控的最新结果与趋势小图。
- 模型取该策略引用的在线模型，没有则取最近上线的模型。

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
- **评分卡开发向导**（3 步，后台任务执行；P3 实现：样本划分 → 候选指标 → 筛选规则与刻度）：
  1. 选数据集、目标、样本划分；
  2. 选候选指标（展示 IV / 趋势 / 缺失率，可沿用指标的已保存分箱方案）；
  3. 共线性筛选（`VIFAnalysis.select(threshold=…)`）；
  4. 训练：`BinningTable.fit` → `transform(output="score")` → `LogisticScore.fit`。
- **版本详情**：入模变量 + 系数 + p 值；训练/测试/OOT 的 AUC、KS（`BinaryEvaluation`）；ROC 曲线；分数段 Lift、累计 KS、PSI（`LogisticScore.lift_compare`）；完整分箱编码表。
- **评分口径**：P1 采用传统 PDO 刻度（600 分对应好坏比 20:1，PDO 50，分高风险低），同时输出违约概率；kivi 新版提供变量分（0–100）后可作为第二种口径。
- 模型产物：分箱切点 / WOE 表 + 系数，整体存 JSONB（kivi 新版后改用 `BinningTable.save` 的 JSON），不依赖 pickle，可审阅、可 diff。
- 批量打分：对任一数据集打分并下载结果。
- 生命周期：草稿 → 待审批 → 已批准 → 已上线 → 已下线；每个模型同时只有一个在线版本。

### 3.6 策略管理（P4）
- **策略**：编码、名称、场景（准入 / 反欺诈 / 授信额度 / 定价 / 贷中 / 催收 / 其他）、负责人，下挂多个版本。
- **策略版本 = 有序规则集 + 默认决策**，规则用结构化 JSON 条件（Pydantic 校验、`extra="forbid"`，不用 `eval`）：
  ```json
  {
    "code": "R05", "name": "评分 < 520", "name_en": "Score below 520", "enabled": true,
    "decision": "reject", "terminal": false, "reason": "LOW_SCORE",
    "when": {"mode": "all", "items": [
      {"field": "model:RETAIL_APP.score", "op": "lt", "value": 520},
      {"mode": "any", "items": [
        {"field": "age", "op": "lt", "value": 22},
        {"field": "phone", "op": "in_list", "value": "BL_PHONE"}
      ]}
    ]}
  }
  ```
  - 运算符：`eq ne gt ge lt le in not_in between is_null not_null in_list not_in_list`；条件组至少一项（空的「全部满足」组会命中所有样本，因此不允许）。
  - 输入字段：请求入参、模型输出（`model:<模型编码>.score|prob`，编码自动转大写，调用该模型的在线版本）、名单命中（名单编码自动转大写）。
  - 决策合并：先看终止规则（如白名单），命中即定；否则取最严重结果（reject > review > pass），同级取排序靠前的规则；无命中用默认决策。所有命中规则都会记录。空值参与比较一律为假。
  - 「分数段决策表」规则类型暂未实现，可用多条区间规则表达。
- **规则编辑器**：规则卡片（编码、中英文名称、决策、原因码、终止、启用、上下移动），条件行由字段（带数据集字段、模型输出提示）、运算符、取值组成，支持「全部 / 任一」两层嵌套。
- **回测**：选带标签的数据集运行策略版本 → 通过 / 人工审核 / 拒绝率、各决策坏账率、每条规则的命中数与命中率、独占数（只被这条规则拦下）、决定数（最终由这条规则定案）与命中样本坏账率、月度通过率；可选另一版本对比，给出 3×3 切换矩阵（行：对比版本决策，列：本版本决策，含每格坏账率）。规则引擎只有一套向量化（pandas）实现，单笔决策是一行的数据框，因此回测与实时接口语义一致。
- **试算**：输入一条 JSON 请求，返回决策、模型分、缺失字段与逐条件执行轨迹（含实际值），不写决策记录。
- 生命周期同模型（四眼原则、每个策略一个在线版本）；上线前检查：至少一条规则、引用的名单存在、引用的模型有在线版本。

### 3.7 风控中心（P4–P5）
- **实时决策接口**（P4）：`POST /api/v1/decide/{strategy_code}`，使用 API 令牌（`Authorization: Bearer kv_…`，库中只存 SHA-256）鉴权，返回决策、原因码、命中规则、模型分与违约概率、缺失字段、耗时、请求号。
  - 同一 `request_id` 重放第一次的结果（`replayed: true`）；用在另一策略上返回 409 `request_id_conflict`；并发重复请求以先写入者为准并按重放返回。
  - 在线策略连同模型与名单摘要在进程内缓存 30 秒；上线 / 下线、名单条目增删、模型上线 / 下线会立即清空本进程缓存，多进程部署时其他进程最迟 30 秒后生效。
  - 下线被在线策略引用的模型、删除被在线策略引用的名单都会被拒绝（`model_in_use` / `list_in_use`）。
- **决策记录**（P4）：分页查询，按策略、决策、来源、命中规则、请求号前缀筛选，查看请求数据与单笔执行轨迹；名单字段在请求数据与轨迹中都只保存脱敏值。
- **名单管理**（P4）：黑 / 白 / 灰名单，维度（手机号 / 身份证号 / 设备号 / IP / 企业代码 / 账号 / 其他），批量导入、有效期、原因、精确查找。值先规范化（去掉空格与短横线、转大写，整数形式的浮点数去掉 `.0`）再做 HMAC-SHA256（密钥 `KIVI_LIST_KEY`，默认同会话密钥）并脱敏展示（如 `138****1234`），原值不落库；移除条目需确认，因为原值无法再查看。
- **API 令牌**（P4）：管理员创建（可设有效期，明文只显示一次）、查看最近使用时间、吊销。
- **监控**（P5）：
  | 检查 | 对象 | 计算 | 默认阈值（预警 / 告警） |
  | --- | --- | --- | --- |
  | `indicator_psi` 变量 PSI | 模型入模变量（跟随在线版本），或指定指标的默认分箱方案 | 每月相对基准期的 PSI（`psi_table`），取最大值 | 0.10 / 0.25 |
  | `score_psi` 分数 PSI | 在线模型 | 在数据集上重新打分，按训练期十等分切点分组后逐月 PSI | 0.10 / 0.25 |
  | `model_ks` 区分度 | 在线模型（需目标列） | 最新有标签月份的 KS 相对基准期 KS 的下降比例 | 10% / 20% |
  | `approval_rate` 通过率变化 | 策略 | 最近 N 天（默认 7）通过率减去此前 M 天（默认 30）的基线 | ±5pp / ±10pp |
  | `rule_hit_rate` 规则命中率变化 | 策略在线版本的启用规则 | 每条规则窗口命中率减基线，取变化最大者 | ±5pp / ±10pp |
  - 数据集检查按日期列分月，基准期默认取模型训练月份（数据集即训练集时），否则取前一半月份，也可指定起止月份；头条值取最新月份。决策检查少于最少决策数（默认 30）时本次运行记为失败（`too_few_requests`），不改变预警。
  - 计划：每小时 / 每天 / 每周的本地时间（`KIVI_TIMEZONE`，默认 America/Los_Angeles，与部署机器的本地时区一致），或仅手动。worker 每 30 秒检查一次到期监控（`FOR UPDATE SKIP LOCKED` 领取并先推进 `next_run_at`，多进程不会重复运行）；「立即运行」同步执行并返回结果。
  - 每次运行写入 `monitor_runs`（头条值、级别、逐月或逐日序列、失败原因码）。
  - 指定指标的变量 PSI 监控保存所选指标编码的快照；指标之后被删除时，运行结果在「未检查」中列出（原因：指标已删除），编辑监控时自动去掉已删除的指标。
- **预警中心**（P5）：
  - 每个监控同时只有一条未解决预警（部分唯一索引）。预警 / 告警级别的运行会新建预警，或更新已有预警的级别、数值与出现次数（记录升级 / 降级事件）；正常运行自动关闭（`recovered`）；失败运行不改变预警。
  - 状态：待认领 → 处理中（认领人 = 操作者）→ 已解决（需填写说明）；之后再次超标会生成新预警。全程事件写入 `alerts.events` 并记审计日志。侧栏显示未解决数量。
- **稳定性监控页**（P5）：按模型汇总分数 PSI、区分度、入模变量 PSI 三类监控的最新运行，按月份对齐。

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

monitors           id, name, kind(indicator_psi|score_psi|model_ks|approval_rate|rule_hit_rate),
                   model_id, strategy_id, dataset_id, params jsonb, thresholds jsonb {warn, alert},
                   schedule jsonb {freq, hour, minute, weekday}, enabled, next_run_at,
                   last_run_at, last_level, last_value, owner_id
monitor_runs       id, monitor_id, trigger(schedule|manual|seed), status(done|failed), level(normal|warn|alert|error),
                   value, detail jsonb (序列、最差项、失败原因码), error, seconds, created_at
alerts             id, monitor_id, run_id, status(open|acknowledged|resolved), level, peak_level, value, threshold,
                   detail jsonb, occurrences, first_seen_at, last_seen_at, assignee_id, acknowledged_at,
                   resolved_by, resolved_at, resolution(manual|recovered), note, events jsonb
                   -- 部分唯一索引：每个 monitor 至多一条 status <> 'resolved'

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
| 策略 | `GET/POST strategies` · `GET strategies/fields` · `GET/PATCH/DELETE strategies/{id}` · `POST strategies/{id}/versions` · `GET/PUT/DELETE strategy-versions/{id}` · `POST strategy-versions/{id}/backtest` · `POST strategy-versions/{id}/evaluate`（试算）· `POST strategy-versions/{id}/{submit\|approve\|reject\|online\|retire}` |
| 决策 | `POST decide/{strategy_code}`（API Token）· `GET decisions` · `GET decisions/{request_id}` |
| 名单 | `GET/POST risk-lists` · `GET/PATCH/DELETE risk-lists/{id}` · `GET/POST risk-lists/{id}/items`（POST 为批量导入）· `DELETE risk-lists/{id}/items/{item_id}` · `POST risk-lists/{id}/check` |
| 监控 | `GET/POST monitors` · `GET/PATCH/DELETE monitors/{id}`（详情含最新运行与最近 30 次运行）· `POST monitors/{id}/run`（同步）· `GET monitor-runs/{id}` · `GET alerts`（`status=active\|open\|acknowledged\|resolved`、`level`、`monitor_id`）· `GET alerts/{id}` · `POST alerts/{id}/acknowledge` · `POST alerts/{id}/resolve` |
| 其他 | `GET overview` · `GET stability?model_id=` · `GET audit-logs` · `GET jobs/{id}` · `GET kivi/methods`（可用分箱方法） |

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
/decisions                决策记录          /lists  /lists/[id]    名单管理
/monitors  /monitors/[id] 监控配置        /alerts                预警中心
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
├── docker-compose.yml          # 开发用 PostgreSQL 18（后续加入 backend / worker / web）
├── scripts/dev-db.sh           # docker compose 启停数据库（127.0.0.1:5433）
├── backend/
│   ├── pyproject.toml          # uv；依赖 kivi>=0.3.0（PyPI），装入 backend/.venv
│   ├── alembic/
│   ├── kivi_ui/
│   │   ├── main.py             # FastAPI 应用、路由注册、异常处理、CSRF 头校验
│   │   ├── cli.py              # create-admin / seed-demo / build-analytics
│   │   ├── config.py · db.py · security.py · deps.py · audit.py · errors.py
│   │   ├── models.py           # SQLAlchemy ORM
│   │   ├── schemas.py          # Pydantic 请求/响应
│   │   ├── routes/             # auth · users · audit_logs · analytics
│   │   └── analytics/          # sample（模拟样本）· scorecard（kivi 分箱/WOE/PSI + 评分卡）· service
│   │   # 后续：worker.py（任务队列）、rule_engine、backtest、monitoring
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

- **开发**：`scripts/dev-db.sh start`（Docker 运行 PostgreSQL 18）；`uv run alembic upgrade head && uv run kivi-ui seed-demo`；`uv run uvicorn kivi_ui.main:app --reload`；`pnpm dev`。
- **演示数据**：P1 模拟 12 个月约 2.4 万笔零售信贷申请（最后三个月合作渠道占比与征信查询次数上升），用 kivi 分箱、WOE、IV、PSI 训练评分卡、模拟 7 条准入规则与决策，并生成预警；结果存为分析快照。P2 起再加入 kivi 自带的 bank 样本。
- **部署**：`docker compose up`（postgres:18、backend、worker、web）。
- **测试**：后端 pytest（认证/权限/四眼原则、规则引擎两条执行路径一致性、kivi 封装结果与直接调用一致）；前端 `tsc --noEmit`；端到端在浏览器中走通登录 → 指标分析 → 建模 → 策略回测。

---

## 11. 分期交付

| 期 | 内容 | 可验收结果 |
| --- | --- | --- |
| **P1 骨架、账户与可视化** ✅ | 仓库、Postgres、迁移、登录/注册/退出/改密、用户管理、审计、BoardUI 应用框架；风控总览用 kivi 在演示样本上实算：KPI、指标 IV 排行、WOE 与坏率图、ROC/KS、分数分布、月度 PSI、模拟决策趋势 | 能注册 → 管理员激活 → 登录 → 看到完整的风控总览图表 |
| **P2 数据与指标** ✅ | 数据集上传/预览/画像、指标目录、分箱工作台（7 种方法 + 特殊值）、多方案与默认方案、按月 PSI、批量筛选与一键登记 | 上传 bank 数据，看到 age 的 WOE/IV 图表并保存分箱方案 |
| **P3 模型** ✅ | 后台任务队列、评分卡向导、版本详情（AUC/KS/ROC/Lift）、审批与上线、批量打分 | 训练评分卡并走完提交—审批—上线 |
| **P4 策略与决策** ✅ | 规则 DSL 与编辑器、回测与版本对比、名单、决策 API、决策记录、API Token | 用 curl 调决策接口得到命中规则与模型分 |
| **P5 监控与总览** ✅ | 监控配置与调度、预警中心、风控总览真实数据 | 改动样本触发 PSI 预警并在总览出现 |

每期结束都能独立运行，并在浏览器里实际走通后再进入下一期。

---

## 12. 已确认事项

1. 注册需管理员激活（`SIGNUP_MODE=approval`），激活后为分析师。
2. 角色只保留管理员、分析师两种。
3. 评分：P1 采用 PDO 刻度（600 / 20:1 / 50），因为 PyPI 上的 kivi 0.3.0 尚无变量分功能；kivi 新版发布后增加 kivi 0–100 分口径。
4. 前端用 Next.js，与 BoardUI 一致。
5. kivi 以 PyPI 包形式（现为 `kivi>=0.4.0`）装入后端 `.venv`，不引用本地路径。
6. 按 P1→P5 逐期交付；初期以好看、可交互的可视化为首要目标。
7. 代码托管在 GitHub `gchensy/kivi-ui`。
8. 开源协议 MIT；界面支持中英双语与明暗主题切换。
9. P2 的上传、画像与分箱均为同步请求（单次上限 20 MB / 50 万行）；后台任务队列推迟到 P3，用于模型训练等耗时操作。分箱规则以 kivi-ui 自己的 JSON（切点、特殊值、类别映射）存储在 `binning_schemes.rule`。
10. P3 的逻辑回归、p 值与 VIF 使用 statsmodels（kivi 0.4 不含建模接口）；分箱在训练集上用各指标默认方案的参数重新拟合；四眼原则同时约束作者与提交人；角色权限仅保留管理员（审批、上线、下线）与分析师（开发、提交）。
11. P4 的规则引擎为 kivi-ui 自研（kivi 不含规则执行）：一套 pandas 向量化实现同时服务回测、试算与实时接口；策略生命周期与模型共用 `routes/lifecycle.py`（先校验角色，再校验状态，最后校验四眼原则）。名单只存 HMAC 摘要；决策记录的请求数据与轨迹对名单字段脱敏。文本取值与数值列比较时，回测按列的存储类型比较，实时接口按请求里的 JSON 类型比较，数值字段应传数字。
12. P5 不引入 cron 表达式与新依赖：计划只支持每小时 / 每天 / 每周 / 手动，时间按 `KIVI_TIMEZONE` 解释，用 `zoneinfo` 换算并在夏令时切换时保持本地时间；调度由现有 worker 的定时回调完成，「立即运行」同步执行。区分度监控在库里存 KS 的相对下降（正数表示变差），界面显示为相对基准期的变化（下降 10% 显示为 −10%）。P1 的模拟分析快照与 `build-analytics` 命令已删除，风控总览与稳定性页改用真实数据。
13. 收尾修复：`seed-demo` 不再依赖仓库里的示例密码（未设置 `KIVI_DEMO_PASSWORD` 时生成随机密码并只打印一次），且在 `KIVI_ENV=production` 下拒绝运行；worker 每小时把演示决策（`source = 'demo'`）按整天顺延到今天，真实决策不受影响（部分索引 `ix_decision_logs_demo`）；规则无法执行的错误（名单不存在、模型未上线等）在回测、试算与实时接口统一返回 422。
