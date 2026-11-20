"""Demonstration content: two datasets and a published indicator catalogue."""

from datetime import date

from kivi.datasets import Dataset as KiviDatasets
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics.sample import FEATURES, simulate
from .models import Dataset, Indicator, User
from .routes.datasets import create_dataset
from .routes.indicators import find_column, new_indicator

RETAIL = "零售信贷申请样本（模拟）"
BANK = "银行营销样本（kivi）"

CATEGORY = {
    "overdue_24m": "credit",
    "inquiries_6m": "credit",
    "credit_utilization": "credit",
    "debt_ratio": "credit",
    "monthly_income": "basic",
    "employment_years": "basic",
    "age": "basic",
    "housing": "basic",
    "education": "basic",
    "loan_amount": "application",
    "loan_term": "application",
    "channel": "application",
}
DESCRIPTION = {
    "overdue_24m": "申请时征信报告中近 24 个月的逾期次数。",
    "inquiries_6m": "申请前 6 个月内机构查询征信的次数，反映近期多头借贷。",
    "credit_utilization": "信用卡已用额度 / 授信总额度。",
    "debt_ratio": "月还款总额 / 月收入。",
    "monthly_income": "申请人自报月收入（元），可为空。",
    "employment_years": "当前单位工作年限，可为空。",
    "age": "申请时的周岁年龄。",
    "loan_amount": "本次申请金额（元）。",
    "channel": "进件渠道：自营 APP、线下门店或合作渠道。",
    "housing": "住房情况。",
    "education": "最高学历。",
    "loan_term": "申请期限（期）。",
}


def seed_datasets(db: Session, owner: User | None, as_of: date | None = None) -> list[str]:
    """Create the demo datasets and indicators if they are missing. Returns what was created."""
    created = []
    if not db.scalar(select(Dataset.id).where(Dataset.name == RETAIL)):
        frame = simulate(as_of or date.today()).drop(columns=["month", "month_index"])
        retail = create_dataset(
            db,
            frame,
            name=RETAIL,
            owner=owner,
            source="demo",
            file_name=None,
            dtypes={f.name: f.kind for f in FEATURES},
            description="kivi-ui 模拟的 12 个月零售信贷申请，最后三个月合作渠道占比与征信查询次数上升。"
            " Simulated retail credit applications with drift in the last three months.",
        )
        created.append(RETAIL)
        db.flush()
        for feature in FEATURES:
            if db.scalar(select(Indicator.id).where(Indicator.code == feature.name)):
                continue
            new_indicator(
                db,
                retail,
                find_column(retail, feature.name),
                code=feature.name,
                name=feature.zh,
                name_en=feature.en,
                category=CATEGORY[feature.name],
                description=DESCRIPTION[feature.name],
                unit=feature.unit if feature.unit in ("count", "ratio", "cny", "years") else None,
                status="published",
                owner=owner,
            )
        created.append(f"{len(FEATURES)} indicators")
    if not db.scalar(select(Dataset.id).where(Dataset.name == BANK)):
        create_dataset(
            db,
            KiviDatasets.bank_data(),
            name=BANK,
            owner=owner,
            source="demo",
            description="kivi 自带的 UCI Bank Marketing 样本（4,521 行），目标为是否认购定期存款。"
            " UCI Bank Marketing sample bundled with kivi; the target is a term deposit subscription.",
        )
        created.append(BANK)
    db.commit()
    return created


MODEL_CODE = "RETAIL_APP"


def seed_model(db: Session, admin: User | None, analyst: User | None) -> list[str]:
    """Train the demo application scorecard and take v1 through review to production."""
    from datetime import UTC, datetime

    from . import model_jobs
    from .analytics.training import TrainConfig
    from .models import Job, ModelReview, ModelVersion, RiskModel

    if db.scalar(select(RiskModel.id).where(RiskModel.code == MODEL_CODE)):
        return []
    retail = db.scalar(select(Dataset).where(Dataset.name == RETAIL))
    if retail is None:
        return []
    indicators = db.scalars(select(Indicator).where(Indicator.dataset_id == retail.id)).unique().all()
    author = analyst or admin
    model = RiskModel(
        code=MODEL_CODE,
        name="零售信贷申请评分卡",
        name_en="Retail application scorecard",
        scene="application",
        description="基于零售信贷申请样本的 A 卡：kivi 分箱 + WOE 逻辑回归，PDO 刻度（600 分 / 20:1 / 50）。",
        owner_id=author.id if author else None,
    )
    db.add(model)
    db.flush()
    version = ModelVersion(
        model_id=model.id,
        version=1,
        status="training",
        dataset_id=retail.id,
        created_by=author.id if author else None,
        config={"indicator_ids": [str(i.id) for i in indicators], "train": TrainConfig().model_dump()},
        notes="演示模型：全部 12 个候选指标，最后 3 个月为跨时间验证。",
    )
    db.add(version)
    db.flush()
    job = Job(
        kind="train_model",
        status="running",
        params={"version_id": str(version.id)},
        created_by=version.created_by,
    )
    db.add(job)
    db.flush()
    version.job_id = job.id
    job.result = model_jobs.train_model(db, job)
    job.status, job.progress, job.finished_at = "done", 1.0, datetime.now(UTC)
    now = datetime.now(UTC)
    steps = [
        ("submit", author, "首版评分卡，提交审批。"),
        ("approve", admin, "效果与稳定性符合要求，同意上线。"),
        ("online", admin, ""),
    ]
    for action, actor, comment in steps:
        db.add(
            ModelReview(
                version_id=version.id, action=action, actor_id=actor.id if actor else None, comment=comment
            )
        )
    version.submitted_by, version.submitted_at = (author.id if author else None), now
    version.approved_by, version.approved_at = (admin.id if admin else None), now
    version.status, version.online_at = "online", now
    db.commit()
    return [f"model {MODEL_CODE} v1 online (OOT AUC {version.auc_oot})"]


# ---- P4: watchlists, the admission strategy and its decision history ------------------------

STRATEGY_CODE = "RETAIL_APPLY"
BLACKLIST, WHITELIST = "BL_PHONE", "WL_PHONE"


def _cond(field: str, op: str, value=None) -> dict:
    return {"field": field, "op": op, "value": value}


def _rule(code, name, name_en, decision, items, mode="all", terminal=False, reason=""):
    return {
        "code": code,
        "name": name,
        "name_en": name_en,
        "decision": decision,
        "terminal": terminal,
        "enabled": True,
        "reason": reason or code,
        "when": {"mode": mode, "items": items},
    }


def admission_rules(cutoff: int = 520, extra: bool = False) -> dict:
    score = f"model:{MODEL_CODE}.score"
    rules = [
        _rule(
            "W01",
            "VIP 白名单直通",
            "VIP whitelist pass",
            "pass",
            [_cond("phone", "in_list", WHITELIST)],
            terminal=True,
            reason="WHITELIST",
        ),
        _rule(
            "R01",
            "电话命中黑名单",
            "Phone on blacklist",
            "reject",
            [_cond("phone", "in_list", BLACKLIST)],
            reason="BLACKLIST",
        ),
        _rule(
            "R02",
            "年龄不在 20–60 岁",
            "Age outside 20–60",
            "reject",
            [_cond("age", "lt", 20), _cond("age", "gt", 60)],
            mode="any",
            reason="AGE",
        ),
        _rule(
            "R03",
            "近24月逾期 ≥ 3 次",
            "3+ delinquencies (24m)",
            "reject",
            [_cond("overdue_24m", "ge", 3)],
            reason="DELINQUENCY",
        ),
        _rule(
            "R04",
            "近6月查询 ≥ 9 次",
            "9+ inquiries (6m)",
            "reject",
            [_cond("inquiries_6m", "ge", 9)],
            reason="INQUIRIES",
        ),
        _rule(
            "R05",
            f"评分 < {cutoff}",
            f"Score below {cutoff}",
            "reject",
            [_cond(score, "lt", cutoff)],
            reason="LOW_SCORE",
        ),
        _rule(
            "R06",
            f"评分 {cutoff}–560 人工审核",
            f"Score {cutoff}–560 to review",
            "review",
            [_cond(score, "ge", cutoff), _cond(score, "lt", 560)],
            reason="GREY_SCORE",
        ),
        _rule(
            "R07",
            "合作渠道且评分 < 590",
            "Partner channel, score < 590",
            "review",
            [_cond("channel", "eq", "partner"), _cond(score, "lt", 590)],
            reason="PARTNER",
        ),
    ]
    if extra:
        rules.append(
            _rule(
                "R08",
                "负债收入比 > 0.85 人工审核",
                "Debt-to-income > 0.85 to review",
                "review",
                [_cond("debt_ratio", "gt", 0.85)],
                reason="DTI",
            )
        )
    return {"default_decision": "pass", "rules": rules}


def seed_strategy(db: Session, admin: User | None, analyst: User | None) -> list[str]:
    """Watchlists from the retail sample, RETAIL_APPLY v1 online and v2 in draft, 30 days of decisions."""
    import numpy as np
    import pandas as pd

    from .models import DecisionLog, RiskList, Strategy, StrategyReview, StrategyVersion
    from .routes.lists import add_items  # noqa: F401  (same hashing as the API)
    from .rules import runtime
    from .rules.dsl import Definition
    from .rules.engine import evaluate, mask_text, normalise_value, summarise, swap

    if db.scalar(select(Strategy.id).where(Strategy.code == STRATEGY_CODE)):
        return []
    retail = db.scalar(select(Dataset).where(Dataset.name == RETAIL))
    if retail is None or "phone" not in {c.column_name for c in retail.columns}:
        return []
    from .data import store

    frame = store.read_columns(db, retail, [c.column_name for c in retail.columns])
    rng = np.random.default_rng(11)
    bad = frame[frame.target == 1]
    good = frame[frame.target == 0]
    black = list(bad.phone.sample(80, random_state=1)) + list(good.phone.sample(10, random_state=2))
    white = list(good.sort_values("credit_utilization").phone.head(25))
    digest = runtime.hasher()
    created = []
    owner = admin.id if admin else None
    for code, name, name_en, kind, values, reason in (
        (BLACKLIST, "电话黑名单", "Phone blacklist", "black", black, "历史欺诈或恶意逾期"),
        (WHITELIST, "VIP 客户白名单", "VIP whitelist", "white", white, "存量优质客户"),
    ):
        lst = RiskList(
            code=code,
            name=name,
            name_en=name_en,
            kind=kind,
            dimension="phone",
            owner_id=owner,
            description=f"演示名单，来自零售样本。 Demo list drawn from the retail sample ({len(values)}).",
        )
        db.add(lst)
        db.flush()
        from .models import RiskListItem

        for value in values:
            text = normalise_value(value)
            db.add(
                RiskListItem(
                    list_id=lst.id,
                    value_hash=digest(text),
                    value_masked=mask_text(text),
                    reason=reason,
                    created_by=owner,
                )
            )
        created.append(f"watchlist {code} ({len(values)})")
    db.flush()

    author = analyst or admin
    strategy = Strategy(
        code=STRATEGY_CODE,
        name="零售信贷申请准入策略",
        name_en="Retail admission strategy",
        scene="admission",
        owner_id=author.id if author else None,
        description="名单 + 硬规则 + 评分卡分数段的准入策略，引用在线模型 RETAIL_APP。",
    )
    db.add(strategy)
    db.flush()
    v1 = StrategyVersion(
        strategy_id=strategy.id,
        version=1,
        definition=admission_rules(),
        created_by=author.id if author else None,
        notes="首版准入策略。",
    )
    v2 = StrategyVersion(
        strategy_id=strategy.id,
        version=2,
        definition=admission_rules(530, extra=True),
        created_by=author.id if author else None,
        notes="候选版本：拒绝线提高到 530，负债收入比过高转人工审核。",
    )
    db.add_all([v1, v2])
    db.flush()
    now = pd.Timestamp.now(tz="UTC")
    for action, actor, comment in (
        ("submit", author, "提交审批。"),
        ("approve", admin, "回测通过率与坏账率符合预期。"),
        ("online", admin, ""),
    ):
        db.add(
            StrategyReview(
                version_id=v1.id, action=action, actor_id=actor.id if actor else None, comment=comment
            )
        )
    v1.submitted_by, v1.submitted_at = (author.id if author else None), now
    v1.approved_by, v1.approved_at = (admin.id if admin else None), now
    v1.status, v1.online_at = "online", now

    # Backtests on the retail sample, v2 compared with v1.
    frame_y = store.labels(retail, frame)
    months = pd.to_datetime(frame.applied_on).dt.to_period("M").astype("string")
    d1, d2 = Definition.model_validate(v1.definition), Definition.model_validate(v2.definition)
    r1 = evaluate(d1, frame, runtime.context_for(db, d1))
    r2 = evaluate(d2, frame, runtime.context_for(db, d2))
    ran = now.isoformat(timespec="seconds")
    ref = {"id": str(retail.id), "name": retail.name}
    v1.backtest = {"dataset": ref, "summary": summarise(d1, r1, frame_y, months), "ran_at": ran}
    v2.backtest = {
        "dataset": ref,
        "summary": summarise(d2, r2, frame_y, months),
        "ran_at": ran,
        "compare": {
            "version_id": str(v1.id),
            "version": 1,
            "summary": v1.backtest["summary"],
            "swap": swap(r1.decision, r2.decision, frame_y.astype(int)),
        },
    }
    created.append(f"strategy {STRATEGY_CODE} v1 online, v2 draft")

    # Decisions for the last 30 days of applications, as if they came through the API.
    recent = frame.applied_on >= (frame.applied_on.max() - pd.Timedelta(days=29))
    rules = {r.code: r for r in d1.rules}
    logs = []
    for idx in frame.index[recent]:
        row = frame.loc[idx]
        hit = [c for c in r1.hits.columns if bool(r1.hits.at[idx, c])]
        deciding = r1.deciding_rule.at[idx]
        at = pd.Timestamp(row.applied_on).tz_localize("Asia/Shanghai") + pd.Timedelta(
            hours=int(rng.integers(8, 22)), minutes=int(rng.integers(0, 60))
        )
        if at > now:  # today's applications arrive before now, never later today
            at = now - pd.Timedelta(minutes=int(rng.integers(1, 180)))
        logs.append(
            DecisionLog(
                request_id=f"demo-{row.application_id}",
                strategy_id=strategy.id,
                version_id=v1.id,
                strategy_code=STRATEGY_CODE,
                version=1,
                decision=r1.decision.at[idx],
                reason=(rules[deciding].reason or deciding) if deciding else "",
                hit_rules=hit,
                scores={
                    MODEL_CODE: {
                        "score": int(r1.outputs.at[idx, f"model:{MODEL_CODE}.score"]),
                        "probability": round(float(r1.outputs.at[idx, f"model:{MODEL_CODE}.prob"]), 6),
                    }
                },
                trace=[
                    {
                        "code": r.code,
                        "name": r.name,
                        "name_en": r.name_en,
                        "decision": r.decision,
                        "terminal": r.terminal,
                        "hit": r.code in hit,
                        "when": None,
                    }
                    for r in d1.rules
                ],
                input={
                    k: (
                        mask_text(str(row[k]))
                        if k == "phone"
                        else (
                            None
                            if pd.isna(row[k])
                            else (row[k].item() if hasattr(row[k], "item") else str(row[k]))
                        )
                    )
                    for k in (
                        "phone",
                        "age",
                        "monthly_income",
                        "debt_ratio",
                        "credit_utilization",
                        "inquiries_6m",
                        "overdue_24m",
                        "employment_years",
                        "loan_amount",
                        "loan_term",
                        "housing",
                        "education",
                        "channel",
                    )
                },
                latency_ms=round(float(rng.gamma(4, 1.6)), 2),
                source="demo",
                created_at=at.to_pydatetime(),
            )
        )
    db.add_all(logs)
    created.append(f"{len(logs)} demo decisions")
    db.commit()
    runtime.invalidate()
    return created


def seed_monitors(db: Session, admin: User | None, analyst: User | None) -> list[str]:
    """Monitors on RETAIL_APP and RETAIL_APPLY, each run once so alerts and charts have data."""
    from datetime import UTC, datetime

    from .models import Alert, Monitor, RiskModel, Strategy
    from .monitoring.checks import DEFAULT_THRESHOLDS
    from .monitoring.schedule import next_run
    from .monitoring.service import _event, run_monitor

    model = db.scalar(select(RiskModel).where(RiskModel.code == MODEL_CODE))
    strategy = db.scalar(select(Strategy).where(Strategy.code == STRATEGY_CODE))
    retail = db.scalar(select(Dataset).where(Dataset.name == RETAIL))
    if model is None or strategy is None or retail is None:
        return []
    if db.scalar(select(Monitor.id).where(Monitor.model_id == model.id)):
        return []
    owner = (analyst or admin).id if (analyst or admin) else None
    specs = [
        ("RETAIL_APP 分数稳定性", "score_psi", {"freq": "daily", "hour": 6, "minute": 0}),
        ("RETAIL_APP 区分能力", "model_ks", {"freq": "daily", "hour": 6, "minute": 10}),
        ("RETAIL_APP 入模变量稳定性", "indicator_psi", {"freq": "daily", "hour": 6, "minute": 20}),
        ("RETAIL_APPLY 通过率", "approval_rate", {"freq": "hourly", "minute": 5}),
        ("RETAIL_APPLY 规则命中率", "rule_hit_rate", {"freq": "daily", "hour": 7, "minute": 0}),
    ]
    created = []
    for name, kind, schedule in specs:
        on_strategy = kind in ("approval_rate", "rule_hit_rate")
        monitor = Monitor(
            name=name,
            kind=kind,
            model_id=None if on_strategy else model.id,
            strategy_id=strategy.id if on_strategy else None,
            dataset_id=None if on_strategy else retail.id,
            params={"window_days": 7, "baseline_days": 30, "min_requests": 30} if on_strategy else {},
            # The rule monitor watches 3pp moves, stricter than the 5pp default.
            thresholds={"warn": 0.03, "alert": 0.08} if kind == "rule_hit_rate" else DEFAULT_THRESHOLDS[kind],
            schedule={"weekday": 0, **schedule},
            enabled=True,
            next_run_at=next_run({"weekday": 0, **schedule}),
            owner_id=owner,
        )
        db.add(monitor)
        db.commit()
        run = run_monitor(db, monitor, "seed")
        created.append(f"monitor {name}: {run.level}")
    # One alert already claimed by the analyst, to show the hand-over.
    claimed = db.scalar(
        select(Alert)
        .join(Monitor, Monitor.id == Alert.monitor_id)
        .where(Monitor.kind == "indicator_psi", Monitor.model_id == model.id, Alert.status == "open")
    )
    if claimed is not None and analyst is not None:
        note = "合作渠道近三个月进件占比上升，已联系渠道运营核实。"
        claimed.status, claimed.assignee_id, claimed.acknowledged_at = (
            "acknowledged",
            analyst.id,
            datetime.now(UTC),
        )
        claimed.note = note
        claimed.events = [*claimed.events, _event("acknowledged", analyst, note=note)]
        db.commit()
    return created


def refresh(db: Session) -> None:
    """Remove demo datasets, indicators, model, strategy, lists and decisions so they can be re-seeded."""
    from .data import store
    from .db import get_engine
    from .models import DecisionLog, RiskList, RiskModel, Strategy

    db.execute(DecisionLog.__table__.delete().where(DecisionLog.strategy_code == STRATEGY_CODE))
    for cls, code in ((Strategy, STRATEGY_CODE), (RiskModel, MODEL_CODE)):
        obj = db.scalar(select(cls).where(cls.code == code))
        if obj is not None:
            db.delete(obj)
    for code in (BLACKLIST, WHITELIST):
        obj = db.scalar(select(RiskList).where(RiskList.code == code))
        if obj is not None:
            db.delete(obj)
    demo = list(db.scalars(select(Dataset).where(Dataset.source == "demo")).unique())
    for indicator in db.scalars(
        select(Indicator).where(Indicator.dataset_id.in_([d.id for d in demo]))
    ).unique():
        indicator.default_scheme_id = None
        db.flush()
        db.delete(indicator)
    tables = [d.table_name for d in demo]
    for dataset in demo:
        db.delete(dataset)
    db.commit()
    for table in tables:
        store.drop_table(get_engine(), table)
