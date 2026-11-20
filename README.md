# kivi-ui

[中文](#中文) · [English](#english)

---

## 中文

[![CI](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml)

**kivi-ui** 是一个开源的金融风控管理平台，覆盖「数据 → 指标 → 模型 → 策略 → 风控监控」全链路。分箱、WOE、IV、PSI 等统计计算由 [kivi](https://github.com/gchensy/kivi) 完成，界面基于 [BoardUI](https://github.com/BoardUI/boardui) 设计体系。

### 功能

- **账户**：登录、注册（默认需管理员审核）、退出、修改密码、个人资料；连续 5 次失败锁定 15 分钟
- **角色**：管理员、分析师；管理员可创建账户、激活注册、调整角色、停用、重置密码
- **审计日志**：登录、注册、账户变更以及数据与指标操作全程留痕
- **数据管理**：上传 CSV（自动识别分隔符、UTF-8/GBK 编码、字段类型、目标列、日期列与主键），按月统计样本量与坏样本率，字段画像与快速 IV，数据预览
- **指标筛选**：用同一种分箱方法批量计算所有特征的 IV，一键把有预测力的字段登记为指标
- **指标管理**：指标目录（分类、状态、口径、中英文名称）；分箱工作台支持等频、等距、卡方合并、决策树、单调 WOE、手工切点与类别分组，并支持特殊值单独成箱；保存多个分箱方案并指定默认方案；按月计算 PSI 稳定性
- **风控总览**：全部来自真实数据——近 30 天决策量与通过率（对比前 30 天）、在线模型 AUC/KS、最新分数 PSI、未解决预警；每日决策、在线策略的规则命中与回测效果、各监控的最新结果与趋势
- **模型管理**：评分卡训练向导（OOT 与测试集划分、在训练集上重拟合分箱、IV → VIF → 系数符号 → 显著性逐步筛选、PDO 刻度），后台任务队列训练；版本报告含各样本 AUC/KS/Gini、ROC、KS 曲线、分数分布与 PSI、系数与 p 值、VIF、变量稳定性、评分卡分值与筛选记录
- **评审与上线**：草稿 → 待审批 → 已批准 → 已上线 → 已下线，四眼原则（作者与提交人不能审批），每个模型只有一个在线版本，全程评审记录；批量打分生成新的数据集
- **策略管理**：规则编辑器（全部/任一条件组可嵌套，13 种运算符，可引用在线模型的分数与违约概率、名单，终止规则用于白名单）；策略版本沿用评审上线流程；在带标签的数据集上回测，给出决策分布、各决策坏账率、规则命中/独占/决定数、月度通过率，以及与另一版本的切换矩阵；单笔试算展示每个条件的实际值
- **名单管理**：黑名单、白名单、灰名单，按手机号、身份证号、设备号等维度；原值只保存 HMAC 摘要并脱敏展示，支持批量导入、有效期和精确查找（空格、短横线不影响匹配）
- **实时决策接口**：`POST /api/v1/decide/{策略编码}`，API 令牌鉴权（只保存哈希），请求号幂等重放，在线策略缓存在内存中、上线和名单变更即时生效；每次调用写入决策记录
- **决策记录**：按策略、决策、来源、命中规则、请求号筛选，查看请求数据（名单字段脱敏）与执行轨迹
- **监控配置**：五种检查——变量 PSI、分数 PSI、区分度（KS 相对基准期的变化）、通过率变化、规则命中率变化；基准期默认取模型训练月份；预警与告警两级阈值；每小时、每天、每周或仅手动运行，也可立即运行，保留运行记录
- **预警中心**：监控超过阈值自动生成预警，同一监控只保留一条未解决预警（再次超标时更新级别与次数）；认领后填写说明处理完成，指标恢复后自动关闭，全程留痕；侧栏显示未解决数量
- **稳定性监控**：按模型汇总监控结果——月度分数 PSI、月度 AUC/KS、入模变量 × 月份 PSI 热力图与相关预警
- **中英双语、明暗主题** 一键切换；所有图表都可切换为表格查看

演示数据为模拟的零售信贷申请样本（12 个月、约 2.4 万笔，最后三个月带有渠道与查询次数漂移），首次启动即有完整的分析结果、一个已上线的准入策略、近 30 天的决策记录，以及已运行的监控和预警。

### 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · psycopg 3 |
| 计算 | kivi 0.4（`bin_edges`、`cut`、`chimerge_edges`、`tree_edges`、`monotonic_edges`、`woe_table`、`psi_table`）· statsmodels（逻辑回归、p 值、VIF）· scikit-learn（ROC） |
| 数据库 | PostgreSQL 18 |
| 前端 | Next.js 16 · React 19 · Tailwind CSS v4 · React Aria · TanStack Query · Recharts · BoardUI |

### 快速开始

需要 Docker、[uv](https://docs.astral.sh/uv/)、Node.js 20+ 和 pnpm。

1. 启动数据库（Docker，监听 `127.0.0.1:5433`）：

   ```bash
   scripts/dev-db.sh start
   ```

2. 启动后端（`http://127.0.0.1:8000`，接口文档在 `/api/docs`）：

   ```bash
   cd backend
   cp .env.example .env
   uv sync
   uv run alembic upgrade head
   uv run kivi-ui seed-demo
   uv run uvicorn kivi_ui.main:app --reload
   ```

3. 启动前端（`http://localhost:3000`）：

   ```bash
   cd web
   pnpm install
   pnpm dev
   ```

`seed-demo` 会创建演示账户 `admin`（管理员）、`analyst`（分析师）和一个待审核的 `newcomer`，仅供本地演示使用。密码取 `backend/.env` 中的 `KIVI_DEMO_PASSWORD`；留空时会生成随机密码并在命令输出中显示一次。`KIVI_ENV=production` 时该命令拒绝运行。它还会导入两个演示数据集（模拟零售信贷样本、kivi 自带的银行营销样本），登记 12 个指标，训练一个已上线的申请评分卡 RETAIL_APP v1，创建手机号黑名单与白名单，准入策略 RETAIL_APPLY（v1 已上线、v2 草稿，均已回测）、约 2,500 条演示决策记录，以及五个监控（各运行一次，生成两条预警）。演示决策会随日期自动顺延，近 30 天始终有数据。

创建正式管理员：

```bash
cd backend && uv run kivi-ui create-admin --username alice --email alice@example.com
```

### 配置

后端读取 `KIVI_` 前缀的环境变量（见 `backend/.env.example`）：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `KIVI_DATABASE_URL` | PostgreSQL 连接串 | `postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi` |
| `KIVI_SECRET_KEY` | 会话签名密钥，生产环境必须设置（≥ 32 字符） | 开发用默认值 |
| `KIVI_COOKIE_SECURE` | 仅通过 HTTPS 发送会话 Cookie，生产环境必须为 `true` | `false` |
| `KIVI_SIGNUP_MODE` | `approval` 需审核 / `open` 直接开通 / `closed` 关闭注册 | `approval` |
| `KIVI_SESSION_HOURS` | 会话有效期（小时） | `8` |
| `KIVI_REQUIRE_FOUR_EYES` | 作者与提交人不能审批自己的模型版本 | `true` |
| `KIVI_RUN_WORKER` | 在 API 进程内运行后台任务与监控计划；设为 `false` 时用 `uv run kivi-ui worker` 单独运行 | `true` |
| `KIVI_TIMEZONE` | 监控运行计划（如「每天 06:00」）与总览按天统计所用的时区（IANA 名称） | `America/Los_Angeles` |
| `KIVI_LIST_KEY` | 名单摘要的 HMAC 密钥；建议单独设置，更换会话密钥时名单仍然有效 | 同 `KIVI_SECRET_KEY` |

前端通过 `KIVI_API_URL`（默认 `http://127.0.0.1:8000`）把 `/api/*` 反向代理到后端，浏览器与后端始终同源。

### 调用决策接口

管理员在「API 令牌」页面创建令牌（只显示一次），业务系统按策略编码调用：

```bash
curl -X POST http://localhost:3000/api/v1/decide/RETAIL_APPLY \
  -H "Authorization: Bearer kv_…" \
  -H "Content-Type: application/json" \
  -d '{"request_id": "APP-0001", "data": {"phone": "13800001234", "age": 35, "inquiries_6m": 2, "overdue_24m": 0, "channel": "app"}}'
```

返回决策（`pass` / `review` / `reject`）、原因码、命中规则、模型分与违约概率、缺失字段和耗时。同一个 `request_id` 再次调用会直接返回第一次的结果（`replayed: true`）。

### 测试

```bash
cd backend && uv run pytest        # 使用独立的 kivi_test 数据库
cd web && pnpm typecheck && pnpm build
```

### 路线图

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P1 | 账户、权限、审计、风控可视化 | ✅ |
| P2 | 数据集上传与画像、指标筛选、指标目录、分箱工作台与方案、指标稳定性 | ✅ |
| P3 | 评分卡开发向导、模型版本、评审上线、批量打分、后台任务队列 | ✅ |
| P4 | 策略规则、回测与版本对比、名单、实时决策接口、决策记录、API 令牌 | ✅ |
| P5 | 监控配置与计划运行、预警中心、风控总览与稳定性监控接入真实数据 | ✅ |

完整设计见 [docs/design.md](docs/design.md)。

---

## English

[![CI](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml)

**kivi-ui** is an open-source credit risk management platform covering data, indicators, models, strategies and monitoring. Binning, WOE, IV and PSI are computed with [kivi](https://github.com/gchensy/kivi); the interface is built on the [BoardUI](https://github.com/BoardUI/boardui) design system.

### Features

- **Accounts**: sign in, sign up (administrator approval by default), sign out, change password, profile; 15-minute lockout after 5 failed attempts
- **Roles**: administrator and analyst; administrators create accounts, approve sign-ups, change roles, disable accounts and reset passwords
- **Audit log** of every sign-in, sign-up, account change and data or indicator change
- **Data**: CSV upload with automatic delimiter, UTF-8/GBK encoding, column type, target, date and ID detection; monthly volume and bad rate; column profiles with quick IV; data preview
- **Screening**: bin every feature the same way, rank by IV and register the predictive ones as indicators in one click
- **Indicators**: a catalogue with categories, status, definitions and Chinese/English names; a binning workbench with quantile, equal-width, ChiMerge, decision-tree, monotonic-WOE, manual and category binning, plus special values in their own bins; several saved schemes per indicator with a default; monthly PSI stability
- **Risk overview**, all from live data: 30-day decisions and approval rate against the 30 days before, online model AUC/KS, the latest score PSI and unresolved alerts; daily decisions, rule hits and backtest effect of the online strategy, and the latest result and trend of every monitor
- **Models**: a scorecard training wizard (OOT and test splits, binning refitted on training rows, stepwise IV → VIF → coefficient sign → significance selection, PDO scaling) trained by a background job queue; version reports with AUC/KS/Gini per split, ROC, KS curve, score distribution and PSI, coefficients with p-values and VIF, variable stability, scorecard points and the selection log
- **Review and deployment**: draft → in review → approved → online → retired with four eyes (authors and submitters can't approve), one online version per model and a full review trail; batch scoring saves a new dataset
- **Strategies**: a rule editor (nested all/any groups, 13 operators, online model scores and default probabilities, watchlists, and terminal rules for whitelists); strategy versions follow the same review flow; backtests on a labelled dataset show the decision mix, bad rate per decision, hits/exclusive/decisive counts per rule, monthly approval rate and a swap matrix against another version; a test console shows the actual value behind every condition
- **Watchlists**: black, white and grey lists by phone, ID number, device and more; values are kept only as HMAC digests and shown masked, with bulk import, expiry and exact lookup (spaces and dashes don't matter)
- **Real-time decision API**: `POST /api/v1/decide/{strategy code}` with API tokens (stored hashed), idempotent replay by request ID and an in-memory cache of online strategies that lifecycle and watchlist changes refresh at once; every call is logged
- **Decision log**: filter by strategy, outcome, source, rule hit or request ID, and inspect the request (watchlist fields masked) and its trace
- **Monitors**: five checks (feature PSI, score PSI, discrimination as the KS change against the reference period, approval rate shift and rule hit rate shift); the reference defaults to the model's training months; warning and alert thresholds; hourly, daily, weekly or manual schedules plus run now, with a run history
- **Alert centre**: monitors raise alerts above their thresholds, one unresolved alert per monitor that later runs update (level, count); claim, resolve with a note, and alerts close themselves on recovery, with a full history; the sidebar shows the unresolved count
- **Stability**: one model's monitors together: monthly score PSI, monthly AUC/KS, a model feature × month PSI heatmap and related alerts
- **Chinese/English and light/dark** switching everywhere; every chart has a table view

The demo data is a simulated retail credit application sample (12 months, about 24,000 applications, with channel and inquiry drift in the last three months), so every page has real analysis, an online admission strategy, 30 days of decisions and monitors that have already run on first start.

### Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · psycopg 3 |
| Analytics | kivi 0.4 (`bin_edges`, `cut`, `chimerge_edges`, `tree_edges`, `monotonic_edges`, `woe_table`, `psi_table`) · statsmodels (logistic regression, p-values, VIF) · scikit-learn (ROC) |
| Database | PostgreSQL 18 |
| Frontend | Next.js 16 · React 19 · Tailwind CSS v4 · React Aria · TanStack Query · Recharts · BoardUI |

### Quick start

Requires Docker, [uv](https://docs.astral.sh/uv/), Node.js 20+ and pnpm.

1. Start PostgreSQL (Docker, on `127.0.0.1:5433`):

   ```bash
   scripts/dev-db.sh start
   ```

2. Start the API (`http://127.0.0.1:8000`, docs at `/api/docs`):

   ```bash
   cd backend
   cp .env.example .env
   uv sync
   uv run alembic upgrade head
   uv run kivi-ui seed-demo
   uv run uvicorn kivi_ui.main:app --reload
   ```

3. Start the web app (`http://localhost:3000`):

   ```bash
   cd web
   pnpm install
   pnpm dev
   ```

`seed-demo` creates the demo accounts `admin` (administrator), `analyst` (analyst) and a pending sign-up `newcomer`, for local demos only. Their password is `KIVI_DEMO_PASSWORD` in `backend/.env`; leave it empty and a random password is generated and printed once. The command refuses to run with `KIVI_ENV=production`. It also imports two demo datasets (the simulated retail credit sample and kivi's bank marketing sample), registers 12 indicators, trains the online application scorecard RETAIL_APP v1, and creates a phone blacklist and whitelist, the admission strategy RETAIL_APPLY (v1 online, v2 draft, both backtested), about 2,500 demo decisions, and five monitors (each run once, raising two alerts). Demo decisions move forward with the calendar, so the last 30 days always have data.

Create a real administrator:

```bash
cd backend && uv run kivi-ui create-admin --username alice --email alice@example.com
```

### Configuration

The API reads `KIVI_`-prefixed environment variables (see `backend/.env.example`):

| Variable | Meaning | Default |
| --- | --- | --- |
| `KIVI_DATABASE_URL` | PostgreSQL URL | `postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi` |
| `KIVI_SECRET_KEY` | Session signing key; required in production (32+ characters) | development value |
| `KIVI_COOKIE_SECURE` | Send the session cookie over HTTPS only; must be `true` in production | `false` |
| `KIVI_SIGNUP_MODE` | `approval`, `open` or `closed` | `approval` |
| `KIVI_SESSION_HOURS` | Session lifetime in hours | `8` |
| `KIVI_REQUIRE_FOUR_EYES` | Authors and submitters can't approve their own model versions | `true` |
| `KIVI_RUN_WORKER` | Run background jobs and monitor schedules inside the API process; with `false`, run `uv run kivi-ui worker` separately | `true` |
| `KIVI_TIMEZONE` | Time zone (IANA name) of monitor schedules ("daily at 06:00") and of the overview's daily buckets | `America/Los_Angeles` |
| `KIVI_LIST_KEY` | HMAC key for watchlist digests; set it separately so watchlists survive a session key rotation | `KIVI_SECRET_KEY` |

The web app proxies `/api/*` to `KIVI_API_URL` (default `http://127.0.0.1:8000`), so the browser always talks to one origin.

### Calling the decision API

An administrator creates a token on the API tokens page (it is shown once). Business systems then call a strategy by its code:

```bash
curl -X POST http://localhost:3000/api/v1/decide/RETAIL_APPLY \
  -H "Authorization: Bearer kv_…" \
  -H "Content-Type: application/json" \
  -d '{"request_id": "APP-0001", "data": {"phone": "13800001234", "age": 35, "inquiries_6m": 2, "overdue_24m": 0, "channel": "app"}}'
```

The response holds the decision (`pass`, `review` or `reject`), the reason code, the rules hit, model scores and default probabilities, missing fields and latency. Repeating a `request_id` returns the first answer (`replayed: true`).

### Tests

```bash
cd backend && uv run pytest        # uses a separate kivi_test database
cd web && pnpm typecheck && pnpm build
```

### Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| P1 | Accounts, roles, audit, risk visualisation | ✅ |
| P2 | Dataset upload and profiling, screening, indicator catalogue, binning workbench and schemes, indicator stability | ✅ |
| P3 | Scorecard wizard, model versions, review and deployment, batch scoring, background job queue | ✅ |
| P4 | Strategy rules, backtesting and version comparison, watchlists, real-time decision API, decision log, API tokens | ✅ |
| P5 | Monitors and schedules, alert centre, live data on the overview and stability pages | ✅ |

See [docs/design.md](docs/design.md) for the full design (in Chinese).

### License

MIT. BoardUI components are MIT licensed; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
