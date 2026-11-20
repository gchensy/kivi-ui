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
