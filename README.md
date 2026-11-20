<div align="center">

<img src="docs/assets/logo.svg" width="84" alt="kivi-ui logo">

# kivi-ui

**The open-source credit risk platform: data → indicators → scorecards → strategies → monitoring**

Upload a sample, bin and screen its variables, train and approve a scorecard,<br>
put a rule strategy online behind a real-time API, and watch it drift: in one place, with an audit trail.

[![CI](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/gchensy/kivi-ui/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Pydantic%20v2-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-111111?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![PostgreSQL 18](https://img.shields.io/badge/PostgreSQL-18-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Powered by kivi](https://img.shields.io/pypi/v/kivi?label=powered%20by%20kivi&color=2b7fff)](https://github.com/gchensy/kivi)
[![License: MIT](https://img.shields.io/badge/license-MIT-0b7a70)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/gchensy/kivi-ui?style=social)](https://github.com/gchensy/kivi-ui)

**English** · [简体中文](README.zh-CN.md)

[Highlights](#-highlights) ·
[Gallery](#-gallery) ·
[Quick start](#-quick-start) ·
[Decision API](#-real-time-decisions) ·
[Architecture](#%EF%B8%8F-architecture) ·
[Roadmap](#%EF%B8%8F-roadmap)

</div>

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/screenshots/en/overview-dark.webp">
    <img src="docs/assets/screenshots/en/overview.webp" width="100%" alt="kivi-ui risk overview: 30-day decisions and approval rate, model AUC and KS, score PSI, unresolved alerts and daily decisions">
  </picture>
</p>

## ✨ Highlights

- 🗂️ **Data in, profiled in seconds.** Upload a CSV and kivi-ui works out the delimiter, UTF-8 or GBK encoding, column types, the target and the date column. You get monthly volume and bad rate, column profiles and a quick IV for every feature.
- 📏 **Indicators you can defend.** A binning workbench built on [kivi](https://github.com/gchensy/kivi): quantile, uniform, ChiMerge, decision tree, monotonic WOE, manual cut points and category groups, with special values in their own bins. Save several schemes per indicator and track monthly PSI.
- 🧮 **Scorecards without notebooks.** A training wizard with out-of-time and test splits, stepwise IV → VIF → coefficient sign → p-value selection and PDO scaling, run on a background job queue. Reports show AUC, KS and Gini per split, ROC and KS curves, deciles, coefficients, VIF and variable stability.
- 🛡️ **Governed releases.** Models and strategies move from draft to in review, approved, online and retired. Four-eyes approval applies, and each model or strategy has one online version. Every step lands in the audit log.
- ⚖️ **Strategies with evidence.** A rule editor over request fields, model scores and watchlists, with terminal whitelist rules. Backtests show the decision mix, bad rate per decision, hits and exclusive hits per rule, monthly approval and a swap matrix against the live version.
- ⚡ **Real-time decisions.** `POST /api/v1/decide/{code}` with hashed API tokens and idempotent request IDs. The decision log keeps every call with its trace, watchlist fields masked.
- 📡 **Monitoring that raises its hand.** Scheduled feature PSI, score PSI, KS, approval-rate and rule-hit checks. Alerts are claimed and resolved in an alert centre, close themselves when the metric recovers, and feed a live overview.
- 🌗 **Bilingual, light and dark.** Every page is available in English and Chinese, in light and dark themes, and every chart has a table view.

## 🧭 How it fits together

<p align="center">
  <img src="docs/assets/platform.svg" width="100%" alt="Data, indicators, scorecards, decisions and monitors in sequence; drift and alerts feed the next indicator scheme, model version and strategy version">
</p>

## 📸 Gallery

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/backtest.webp"><img src="docs/assets/screenshots/en/backtest.webp" alt="Strategy backtest with rule hits, monthly approval and a swap matrix"></a>
      <br><b>Backtest and compare</b>: rule hits, exclusive and decisive counts, bad rate of hits, monthly approval and the v1 → v2 swap matrix.
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/rules.webp"><img src="docs/assets/screenshots/en/rules.webp" alt="Rule editor with nested conditions on fields, model scores and watchlists"></a>
      <br><b>Rule editor</b>: nested all/any groups over request fields, <code>model:RETAIL_APP.score</code> and watchlists, with terminal rules.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/model.webp"><img src="docs/assets/screenshots/en/model.webp" alt="Scorecard version report with AUC, KS and Gini per split, ROC and KS curves"></a>
      <br><b>Scorecard report</b>: AUC, KS and Gini for training, test and out-of-time samples, with ROC and KS curves.
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/binning.webp"><img src="docs/assets/screenshots/en/binning.webp" alt="Binning workbench with WOE and bad rate per bin"></a>
      <br><b>Binning workbench</b>: WOE, bad rate and share per bin for every method, saved as reusable schemes.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/monitor.webp"><img src="docs/assets/screenshots/en/monitor.webp" alt="Feature PSI monitor with a feature by month heatmap"></a>
      <br><b>Monitors</b>: feature PSI by month against the training period, with run history and thresholds.
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/alerts.webp"><img src="docs/assets/screenshots/en/alerts.webp" alt="Alert centre with an alert claimed and its history"></a>
      <br><b>Alert centre</b>: one alert per monitor; claim it, resolve it with a note, or let recovery close it.
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/stability.webp"><img src="docs/assets/screenshots/en/stability.webp" alt="Stability page with monthly AUC and KS and a feature PSI heatmap"></a>
      <br><b>Stability</b>: monthly AUC and KS and a model feature × month PSI heatmap, lined up per model.
    </td>
    <td width="50%" valign="top">
      <a href="docs/assets/screenshots/en/decision.webp"><img src="docs/assets/screenshots/en/decision.webp" alt="Decision log entry with masked request data and a rule trace"></a>
      <br><b>Decision trace</b>: every API call with its masked request, model score and the rules it hit.
    </td>
  </tr>
</table>

## 🚀 Quick start

You need Docker, [uv](https://docs.astral.sh/uv/), Node.js 20+ and pnpm.

```bash
# 1. PostgreSQL 18 in Docker, on 127.0.0.1:5433
scripts/dev-db.sh start

# 2. The API on http://127.0.0.1:8000 (docs at /api/docs)
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run kivi-ui seed-demo          # demo accounts, data, model, strategy and monitors
uv run uvicorn kivi_ui.main:app --reload

# 3. The web app on http://localhost:3000
cd ../web
pnpm install
pnpm dev
```

`seed-demo` creates the accounts `admin` (administrator) and `analyst`, plus a pending sign-up `newcomer`. Their password is `KIVI_DEMO_PASSWORD` from `backend/.env`; leave it empty and a random one is generated and printed once. The command refuses to run with `KIVI_ENV=production`.

<details>
<summary><b>What the demo contains</b></summary>

<br>

- A simulated retail credit sample (12 months, about 24,000 applications, with channel and credit-inquiry drift in the last three months) and kivi's bank marketing sample.
- 12 published indicators and the online application scorecard **RETAIL_APP v1** (OOT AUC 0.731).
- Phone blacklist and whitelist, and the admission strategy **RETAIL_APPLY**: v1 online and v2 draft, both backtested.
- About 2,500 demo decisions over the last 30 days. They move forward with the calendar, so the overview never empties.
- Five monitors, each run once: the feature PSI monitor flags `inquiries_6m` (claimed by the analyst), and the rule monitor has an open warning.

</details>

To create a real administrator:

```bash
cd backend && uv run kivi-ui create-admin --username alice --email alice@example.com
```

## ⚡ Real-time decisions

An administrator creates an API token under **API tokens**. It is shown once and stored only as a hash. Business systems then call a strategy by its code:

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

Terminal rules (whitelists) decide first; otherwise the most severe hit wins (reject > review > pass) and every hit is reported. Repeating a `request_id` returns the first answer with `"replayed": true`.

## 🏗️ Architecture

```mermaid
flowchart LR
  user(["Analysts and admins"]) --> web["Web app<br/>Next.js 16 · React 19 · BoardUI"]
  web -- "/api/* (same origin)" --> api["API<br/>FastAPI · Pydantic v2"]
  systems(["Business systems"]) -- "POST /api/v1/decide/:code<br/>Bearer token" --> api
  api --> engine["Analytics<br/>kivi · statsmodels · scikit-learn"]
  api --> db[("PostgreSQL 18<br/>metadata · kivi_data samples")]
  worker["Worker<br/>training · scoring · monitor schedules"] --> db
  worker --> engine
```

| Layer | Technology |
| --- | --- |
| Backend | Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2 · Alembic · psycopg 3 |
| Analytics | [kivi](https://github.com/gchensy/kivi) 0.4 (binning, WOE, IV, PSI) · statsmodels (logistic regression, p-values, VIF) · scikit-learn (ROC) |
| Rules | A Pydantic rule language evaluated with vectorised pandas: one engine for backtests, the test console and live decisions |
| Jobs | A PostgreSQL job queue (`FOR UPDATE SKIP LOCKED`) in the API process or `kivi-ui worker`, with monitor schedules |
| Database | PostgreSQL 18; uploaded samples live as tables in the `kivi_data` schema |
| Frontend | Next.js 16 · React 19 · Tailwind CSS v4 · React Aria · TanStack Query · Recharts · [BoardUI](https://github.com/BoardUI/boardui) |

## ⚙️ Configuration

The API reads `KIVI_`-prefixed environment variables (see [`backend/.env.example`](backend/.env.example)):

| Variable | Meaning | Default |
| --- | --- | --- |
| `KIVI_DATABASE_URL` | PostgreSQL URL | `postgresql+psycopg://kivi:kivi@127.0.0.1:5433/kivi` |
| `KIVI_SECRET_KEY` | Session signing key; required in production (32+ characters) | development value |
| `KIVI_COOKIE_SECURE` | Send the session cookie over HTTPS only; must be `true` in production | `false` |
| `KIVI_SIGNUP_MODE` | `approval`, `open` or `closed` | `approval` |
| `KIVI_SESSION_HOURS` | Session lifetime in hours | `8` |
| `KIVI_REQUIRE_FOUR_EYES` | Authors and submitters can't approve their own versions | `true` |
| `KIVI_RUN_WORKER` | Run jobs and monitor schedules inside the API process; with `false`, run `uv run kivi-ui worker` | `true` |
| `KIVI_TIMEZONE` | Time zone (IANA name) of monitor schedules and the overview's daily buckets | `America/Los_Angeles` |
| `KIVI_LIST_KEY` | HMAC key for watchlist digests; set it separately so watchlists survive a session key rotation | `KIVI_SECRET_KEY` |
| `KIVI_DEMO_PASSWORD` | Password of the `seed-demo` accounts; empty means a random one, printed once | empty |

The web app proxies `/api/*` to `KIVI_API_URL` (default `http://127.0.0.1:8000`), so the browser always talks to one origin.

## 🗺️ Roadmap

- ✅ **P1** Accounts with approval sign-up, two roles, audit log, bilingual light and dark UI
- ✅ **P2** Dataset upload and profiling, IV screening, indicator catalogue, binning workbench and schemes, indicator stability
- ✅ **P3** Scorecard wizard on a background job queue, version reports, review and deployment, batch scoring
- ✅ **P4** Strategy rules, backtests and version comparison, watchlists, real-time decision API, decision log, API tokens
- ✅ **P5** Monitors and schedules, alert centre, live overview and stability pages

The full design, in Chinese, is in [docs/design.md](docs/design.md). Ideas and issues are welcome.

## 🤝 Contributing

```bash
scripts/dev-db.sh start                     # PostgreSQL, with a kivi_test database for the tests
cd backend
uv run pytest                               # API, rules, monitoring and analytics tests
uv run ruff check kivi_ui tests && uv run ruff format --check kivi_ui tests
uv run alembic check                        # models and migrations agree
cd ../web
pnpm typecheck && pnpm build
```

CI runs the same checks on every pull request.

## 📄 License

[MIT](LICENSE). BoardUI components are MIT licensed and kivi is MIT licensed; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

<div align="center">

<sub>If kivi-ui helps your risk team, a ⭐ helps others find it.</sub>

</div>
