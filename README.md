# kivi-ui

[中文](#中文) · [English](#english)

---

## 中文

[![CI](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml)

**kivi-ui** 是一个开源的金融风控管理平台，覆盖「数据 → 指标 → 模型 → 策略 → 风控监控」全链路。分箱、WOE、IV、PSI 等统计计算由 [kivi](https://github.com/gchensy/kivi) 完成，界面基于 [BoardUI](https://github.com/BoardUI/boardui) 设计体系。

### 功能（P1）

- **账户**：登录、注册（默认需管理员审核）、退出、修改密码、个人资料；连续 5 次失败锁定 15 分钟
- **角色**：管理员、分析师；管理员可创建账户、激活注册、调整角色、停用、重置密码
- **审计日志**：登录、注册与账户变更全程留痕
- **风控总览**：近 30 天申请量、通过率、模型 AUC/KS、分数 PSI、预警；每日决策、规则命中、策略效果、月度进件
- **指标分析**：IV 排行，单指标分箱的 WOE、坏账率、样本占比
- **模型表现**：训练集与跨时间验证（OOT）的 ROC、KS 曲线、分数分布、十等分效果表、评分卡分值
- **稳定性监控**：月度分数 PSI、月度 AUC/KS、指标 × 月份 PSI 热力图，超阈值自动生成预警
- **中英双语、明暗主题** 一键切换；所有图表都可切换为表格查看

演示数据为模拟的零售信贷申请样本（12 个月、约 2.4 万笔，最后三个月带有渠道与查询次数漂移），首次启动即有完整的分析结果。

### 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · psycopg 3 |
| 计算 | kivi（`bin_edges` / `woe_table` / `psi_table`）· scikit-learn（逻辑回归、ROC） |
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

`seed-demo` 会创建演示账户 `admin`（管理员）、`analyst`（分析师）和一个待审核的 `newcomer`，密码为 `backend/.env` 中的 `KIVI_DEMO_PASSWORD`，仅供本地演示使用。

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

前端通过 `KIVI_API_URL`（默认 `http://127.0.0.1:8000`）把 `/api/*` 反向代理到后端，浏览器与后端始终同源。

### 测试

```bash
cd backend && uv run pytest        # 使用独立的 kivi_test 数据库
cd web && pnpm typecheck && pnpm build
```

### 路线图

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P1 | 账户、权限、审计、风控可视化 | ✅ |
| P2 | 数据集上传与画像、指标目录、分箱方案管理 | 计划中 |
| P3 | 评分卡开发向导、模型版本与审批上线 | 计划中 |
| P4 | 策略规则、回测、名单、实时决策接口 | 计划中 |
| P5 | 监控任务调度、预警处理 | 计划中 |

完整设计见 [docs/design.md](docs/design.md)。

---

## English

[![CI](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml)

**kivi-ui** is an open-source credit risk management platform covering data, indicators, models, strategies and monitoring. Binning, WOE, IV and PSI are computed with [kivi](https://github.com/gchensy/kivi); the interface is built on the [BoardUI](https://github.com/BoardUI/boardui) design system.

### Features (P1)

- **Accounts**: sign in, sign up (administrator approval by default), sign out, change password, profile; 15-minute lockout after 5 failed attempts
- **Roles**: administrator and analyst; administrators create accounts, approve sign-ups, change roles, disable accounts and reset passwords
- **Audit log** of every sign-in, sign-up and account change
- **Risk overview**: 30-day applications, approval rate, model AUC/KS, score PSI and alerts; daily decisions, rule hits, strategy effect and monthly intake
- **Indicators**: information value ranking and per-bin WOE, bad rate and share
- **Model performance**: ROC, KS curve, score distribution, decile gains and scorecard points for training and out-of-time samples
- **Stability**: monthly score PSI, monthly AUC/KS and an indicator × month PSI heatmap, with alerts above thresholds
- **Chinese/English and light/dark** switching everywhere; every chart has a table view

The demo data is a simulated retail credit application sample (12 months, about 24,000 applications, with channel and inquiry drift in the last three months), so every page has real analysis on first start.

### Stack

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · psycopg 3 |
| Analytics | kivi (`bin_edges` / `woe_table` / `psi_table`) · scikit-learn (logistic regression, ROC) |
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

`seed-demo` creates the demo accounts `admin` (administrator), `analyst` (analyst) and a pending sign-up `newcomer`. Their password is `KIVI_DEMO_PASSWORD` in `backend/.env`, for local demos only.

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

The web app proxies `/api/*` to `KIVI_API_URL` (default `http://127.0.0.1:8000`), so the browser always talks to one origin.

### Tests

```bash
cd backend && uv run pytest        # uses a separate kivi_test database
cd web && pnpm typecheck && pnpm build
```

### Roadmap

| Phase | Scope | Status |
| --- | --- | --- |
| P1 | Accounts, roles, audit, risk visualisation | ✅ |
| P2 | Dataset upload and profiling, indicator catalogue, binning schemes | Planned |
| P3 | Scorecard wizard, model versions, approval and deployment | Planned |
| P4 | Strategy rules, backtesting, watchlists, real-time decision API | Planned |
| P5 | Scheduled monitors and alert handling | Planned |

See [docs/design.md](docs/design.md) for the full design (in Chinese).

### License

MIT. BoardUI components are MIT licensed; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
