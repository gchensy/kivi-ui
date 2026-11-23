<div align="center">

<img src="docs/assets/logo.svg" width="84" alt="kivi-ui 标志">

# kivi-ui

**开源的金融风控平台：数据 → 指标 → 评分卡 → 策略 → 监控**

上传样本、分箱与筛选变量、训练并审批评分卡，<br>
把规则策略通过实时接口上线，再持续监控漂移：一处完成，全程留痕。

[![CI](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Pydantic%20v2-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-111111?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![PostgreSQL 18](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Powered by kivi](https://img.shields.io/pypi/v/kivi?label=powered%20by%20kivi&color=2b7fff)](https://github.com/gchensy/kivi)
[![License: MIT](https://img.shields.io/badge/license-MIT-0b7a70)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/gchensy/kivi-ui?style=social)](https://github.com/gchensy/kivi-ui)

[English](README.md) · **简体中文**

[亮点](#-亮点) ·
[界面一览](#-界面一览) ·
[快速开始](#-快速开始) ·
[决策接口](#-实时决策接口) ·
[架构](#%EF%B8%8F-架构) ·
[路线图](#%EF%B8%8F-路线图)

</div>

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshots/zh/overview-dark.webp">
    <img src="docs/assets/screenshots/zh/overview.webp" width="100%" alt="kivi-ui 风控总览：近 30 天决策量与通过率、模型 AUC 与 KS、分数 PSI、未解决预警与每日决策">
  </picture>
</p>

## ✨ 亮点

- 🗂️ **数据进来，几秒出画像。** 上传 CSV，自动识别分隔符、UTF-8 或 GBK 编码、字段类型、目标列和日期列；按月统计样本量与坏样本率，给出字段画像和每个特征的快速 IV。
- 📏 **指标经得起推敲。** 基于 [kivi](https://github.com/gchensy/kivi) 的分箱工作台：等频、等距、卡方合并、决策树、单调 WOE、手工切点与类别分组，特殊值单独成箱；每个指标可保存多个方案，并按月跟踪 PSI。
- 🧮 **不写代码也能开发评分卡。** 训练向导支持跨时间验证与测试集划分、IV → VIF → 系数符号 → 显著性逐步筛选和 PDO 刻度，由后台任务队列执行；版本报告含各样本 AUC/KS/Gini、ROC 与 KS 曲线、十等分、系数、VIF 和变量稳定性。
- 🛡️ **上线有治理。** 模型与策略都走 草稿 → 待审批 → 已批准 → 已上线 → 已下线，四眼原则审批，每个模型或策略只有一个在线版本，每一步写入审计日志。
- ⚖️ **策略用数据说话。** 规则编辑器可组合请求字段、模型分与名单，并支持终止规则（白名单）；回测给出决策分布、各决策坏账率、每条规则的命中与独占命中、月度通过率，以及与在线版本的切换矩阵。
- ⚡ **实时决策。** `POST /api/v1/decide/{策略编码}`，API 令牌只存哈希，请求号幂等重放；决策记录保留每次调用的执行轨迹，名单字段脱敏。
- 📡 **监控会主动报警。** 计划运行变量 PSI、分数 PSI、KS、通过率与规则命中率检查；预警在预警中心认领和处理，指标恢复后自动关闭，并汇总到实时风控总览。
- 🌗 **中英双语，明暗主题。** 所有页面支持中英文与明暗主题切换，每张图表都能切换为表格查看。

## 🧭 整体流程

<p align="center">
  <img src="docs/assets/platform.zh-CN.svg" width="100%" alt="数据、指标、评分卡、策略与决策、监控预警依次衔接；漂移与预警驱动下一个分箱方案、模型版本和策略版本">
</p>

## 📸 界面一览

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/backtest.webp"><img src="docs/assets/screenshots/zh/backtest.webp" alt="策略回测：规则命中、月度通过率与切换矩阵"></a>
      <br><b>回测与版本对比</b>：规则命中、独占与决定数、命中样本坏账率、月度通过率，以及 v1 → v2 切换矩阵。
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/rules.webp"><img src="docs/assets/screenshots/zh/rules.webp" alt="规则编辑器：基于字段、模型分与名单的嵌套条件"></a>
      <br><b>规则编辑器</b>：全部 / 任一条件组可嵌套，引用请求字段、<code>model:RETAIL_APP.score</code> 与名单，支持终止规则。
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/model.webp"><img src="docs/assets/screenshots/zh/model.webp" alt="评分卡版本报告：各样本 AUC、KS、Gini 与 ROC、KS 曲线"></a>
      <br><b>评分卡报告</b>：训练集、测试集与跨时间验证的 AUC、KS、Gini，以及 ROC 与 KS 曲线。
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/binning.webp"><img src="docs/assets/screenshots/zh/binning.webp" alt="分箱工作台：每箱 WOE 与坏账率"></a>
      <br><b>分箱工作台</b>：每种方法下每箱的 WOE、坏账率与占比，可保存为复用的分箱方案。
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/monitor.webp"><img src="docs/assets/screenshots/zh/monitor.webp" alt="变量 PSI 监控：变量 × 月份热力图"></a>
      <br><b>监控配置</b>：相对训练期逐月计算变量 PSI，附运行记录与阈值。
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/alerts.webp"><img src="docs/assets/screenshots/zh/alerts.webp" alt="预警中心：已认领的预警及其处理记录"></a>
      <br><b>预警中心</b>：每个监控一条预警；认领、填写说明后处理完成，或在指标恢复后自动关闭。
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/stability.webp"><img src="docs/assets/screenshots/zh/stability.webp" alt="稳定性监控：月度 AUC、KS 与入模变量 PSI 热力图"></a>
      <br><b>稳定性监控</b>：按模型汇总月度 AUC、KS 与入模变量 × 月份 PSI 热力图。
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/zh/decision.webp"><img src="docs/assets/screenshots/zh/decision.webp" alt="决策详情：脱敏的请求数据与规则执行轨迹"></a>
      <br><b>决策轨迹</b>：每次接口调用的脱敏请求、模型分与命中规则。
    </td>
  </tr>
</table>

## 🚀 快速开始

需要 Docker、[uv](https://docs.astral.sh/uv/)、Node.js 20+ 和 pnpm。

```bash
# 1. 用 Docker 启动 PostgreSQL 18，监听 127.0.0.1:5433
scripts/dev-db.sh start

# 2. 启动后端 http://127.0.0.1:8000（接口文档在 /api/docs）
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run kivi-ui seed-demo          # 演示账户、数据、模型、策略与监控
uv run uvicorn kivi_ui.main:app --reload

# 3. 启动前端 http://localhost:3000
cd ../web
pnpm install
pnpm dev
```

`seed-demo` 会创建演示账户 `admin`（管理员）、`analyst`（分析师）和一个待审核的 `newcomer`。密码取 `backend/.env` 中的 `KIVI_DEMO_PASSWORD`；留空时会生成随机密码并在命令输出中显示一次。`KIVI_ENV=production` 时该命令拒绝运行。

<details>
<summary><b>演示数据包含什么</b></summary>

<br>

- 模拟的零售信贷申请样本（12 个月、约 2.4 万笔，最后三个月合作渠道占比与征信查询次数上升）和 kivi 自带的银行营销样本。
- 12 个已发布指标，以及已上线的申请评分卡 **RETAIL_APP v1**（跨时间验证 AUC 0.731）。
- 手机号黑名单与白名单，准入策略 **RETAIL_APPLY**：v1 已上线、v2 草稿，均已回测。
- 近 30 天约 2,500 条演示决策，会随日期自动顺延，风控总览始终有数据。
- 五个监控，各运行一次：变量 PSI 监控发现 `inquiries_6m` 偏移（已由分析师认领），规则命中率监控有一条待认领的预警。

</details>

创建正式管理员：

```bash
cd backend && uv run kivi-ui create-admin --username alice --email alice@example.com
```

## ⚡ 实时决策接口

管理员在「API 令牌」页面创建令牌（只显示一次，库中只存哈希），业务系统按策略编码调用：

```bash
curl -X POST http://localhost:3000/api/v1/decide/RETAIL_APPLY \
  -H "Authorization: Bearer kv_…" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "APP-20261120-0001",
    "data": {
      "phone": "13800001234", "age": 29, "monthly_income": 6500, "debt_ratio": 0.58,
      "credit_utilization": 0.81, "inquiries_6m": 4, "overdue_24m": 1, "employment_years": 2,
      "loan_amount": 50000, "loan_term": "24", "housing": "rent", "education": "college", "channel": "partner"
    }
  }'
```

```json
{
  "request_id": "APP-20261120-0001",
  "decision": "reject",
  "reason": "LOW_SCORE",
  "rules": [
    { "code": "R05", "name": "评分 < 520", "name_en": "Score below 520", "decision": "reject" },
    { "code": "R07", "name": "合作渠道且评分 < 590", "name_en": "Partner channel, score < 590", "decision": "review" }
  ],
  "scores": { "RETAIL_APP": { "score": 512, "probability": 0.144555 } },
  "strategy": { "code": "RETAIL_APPLY", "version": 1 },
  "missing_fields": [],
  "latency_ms": 16.82,
  "replayed": false
}
```

终止规则（白名单）优先决定；否则取最严重的命中结果（拒绝 > 人工审核 > 通过），所有命中规则都会返回。同一个 `request_id` 再次调用会直接返回第一次的结果（`"replayed": true`）。

## 🏗️ 架构

```mermaid
flowchart LR
  user(["分析师与管理员"]) --> web["前端<br/>Next.js 16 · React 19 · BoardUI"]
  web -- "/api/*（同源）" --> api["后端 API<br/>FastAPI · Pydantic v2"]
  systems(["业务系统"]) -- "POST /api/v1/decide/:code<br/>Bearer 令牌" --> api
  api --> engine["计算<br/>kivi · statsmodels · scikit-learn"]
  api --> db[("PostgreSQL 18<br/>元数据 · kivi_data 样本")]
  worker["后台 worker<br/>训练 · 打分 · 监控计划"] --> db
  worker --> engine
```

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · psycopg 3 |
| 计算 | [kivi](https://github.com/gchensy/kivi) 0.4（分箱、WOE、IV、PSI）· statsmodels（逻辑回归、p 值、VIF）· scikit-learn（ROC） |
| 规则 | Pydantic 定义的规则语言，pandas 向量化执行：回测、试算与实时接口共用一个引擎 |
| 任务 | PostgreSQL 任务队列（`FOR UPDATE SKIP LOCKED`），运行在 API 进程或 `kivi-ui worker` 中，并负责监控计划 |
| 数据库 | PostgreSQL 18；上传的样本以物理表存放在 `kivi_data` schema |
| 前端 | Next.js 16 · React 19 · Tailwind CSS v4 · React Aria · TanStack Query · Recharts · [BoardUI](https://github.com/BoardUI/boardui) |

## ⚙️ 配置

后端读取 `KIVI_` 前缀的环境变量（见 [`backend/.env.example`](backend/.env.example)）：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `KIVI_DATABASE_URL` | PostgreSQL 连接串 | `postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi` |
| `KIVI_SECRET_KEY` | 会话签名密钥，生产环境必须设置（≥ 32 字符） | 开发用默认值 |
| `KIVI_COOKIE_SECURE` | 仅通过 HTTPS 发送会话 Cookie，生产环境必须为 `true` | `false` |
| `KIVI_SIGNUP_MODE` | `approval` 需审核 / `open` 直接开通 / `closed` 关闭注册 | `approval` |
| `KIVI_SESSION_HOURS` | 会话有效期（小时） | `8` |
| `KIVI_REQUIRE_FOUR_EYES` | 作者与提交人不能审批自己的版本 | `true` |
| `KIVI_RUN_WORKER` | 在 API 进程内运行后台任务与监控计划；设为 `false` 时用 `uv run kivi-ui worker` 单独运行 | `true` |
| `KIVI_TIMEZONE` | 监控运行计划与总览按天统计所用的时区（IANA 名称） | `America/Los_Angeles` |
| `KIVI_LIST_KEY` | 名单摘要的 HMAC 密钥；建议单独设置，更换会话密钥时名单仍然有效 | 同 `KIVI_SECRET_KEY` |
| `KIVI_DEMO_PASSWORD` | `seed-demo` 演示账户的密码；留空时生成随机密码并显示一次 | 空 |

前端通过 `KIVI_API_URL`（默认 `http://127.0.0.1:8000`）把 `/api/*` 反向代理到后端，浏览器与后端始终同源。

## 🗺️ 路线图

- ✅ **P1** 账户与注册审核、两种角色、审计日志、中英双语与明暗主题
- ✅ **P2** 数据集上传与画像、IV 筛选、指标目录、分箱工作台与方案、指标稳定性
- ✅ **P3** 后台任务队列上的评分卡向导、版本报告、审批上线、批量打分
- ✅ **P4** 策略规则、回测与版本对比、名单、实时决策接口、决策记录、API 令牌
- ✅ **P5** 监控配置与计划运行、预警中心、风控总览与稳定性监控接入真实数据

完整设计见 [docs/design.md](docs/design.md)。欢迎提出想法和问题。

## 🤝 参与开发

```bash
scripts/dev-db.sh start                     # PostgreSQL，含测试用的 kivi_test 数据库
cd backend
uv run pytest                               # 接口、规则、监控与分析测试
uv run ruff check kivi_ui tests && uv run ruff format --check kivi_ui tests
uv run alembic check                        # 模型与迁移一致
cd ../web
pnpm typecheck && pnpm build
```

每个 Pull Request 都会在 CI 中运行同样的检查。

重拍 README 截图：先用演示数据启动后端与前端，再运行 `node scripts/screenshots.mjs`（需要 Chrome；传入 `overview,alerts` 等名称可只重拍这几张）。

## 📄 许可证

[MIT](LICENSE)。BoardUI 组件与 kivi 均采用 MIT 许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

<div align="center">

<sub>如果 kivi-ui 对你的风控团队有帮助，点一个 ⭐ 能让更多人看到它。</sub>

</div>
