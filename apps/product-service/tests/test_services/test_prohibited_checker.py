
import pytest
from sqlalchemy import select, func

from sk_shared.models.product import ProhibitedCategory, ProhibitedItemLog
from src.services.prohibited_checker import ProhibitedCheckerService


@pytest.mark.asyncio
async def test_prohibited_keyword_in_description_detected(db_session):
    db_session.add(ProhibitedCategory(category_name="Alcohol", keywords=["alcohol"]))
    await db_session.commit()

    svc = ProhibitedCheckerService()
    res = await svc.check_text(
        db=db_session,
        text="Premium box",
        description="contains alcohol essence",
        brand="",
        raw_url="https://example.com/1",
        canonical_url="https://example.com/1",
    )
    assert res.is_prohibited is True
    assert res.confidence == 1.0


@pytest.mark.asyncio
async def test_log_created_on_detection(db_session):
    db_session.add(ProhibitedCategory(category_name="Tobacco", keywords=["cigarette"]))
    await db_session.commit()

    svc = ProhibitedCheckerService()
    await svc.check_text(
        db=db_session,
        text="Cigarette box",
        raw_url="https://example.com/2",
        canonical_url="https://example.com/2",
    )
    count = await db_session.scalar(select(func.count(ProhibitedItemLog.id)))
    assert count >= 1
