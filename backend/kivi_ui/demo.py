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
