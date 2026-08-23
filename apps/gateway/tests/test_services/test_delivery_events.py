from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from sk_shared.constants import OrderState
from sk_shared.models.order import Order, OrderStatusHistory
from sk_shared.models.payment import Installment, Loan
from sk_shared.models.product import Merchant, Product

from src.services.delivery_events import apply_delivery_confirmed_envelope, apply_delivery_status_envelope
from tests.conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


async def _seed_order(user_id: int, status: str, label: str = "delivery") -> Order:
    async with TestingSessionLocal() as session:
        merchant = Merchant(name=f"{label} Merchant", normalized_name=f"{label}-merchant", domain=f"{label}.example.com")
        session.add(merchant)
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            name=f"{label} Product",
            url=f"https://{label}.example.com/p/1",
            currency="PKR",
            cost_price=5000,
            sale_price=5200,
            in_stock=True,
        )
        session.add(product)
        await session.flush()

        order = Order(
            user_id=user_id,
            product_id=product.id,
            status=status,
            total_amount=5200,
            down_payment_amount=1300,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def _seed_loan_with_installments(order: Order, *, installment_count: int = 3, share_with: list[Order] | None = None) -> Loan:
    """Seed a Loan whose installment due_dates are anchored to a stale
    "contract-signing" date far from `now`, mirroring the pre-P0-04 behavior
    (ContractSignerService.sign_murabaha sets due_date = signing_time +
    30*n days) so tests can assert delivery confirmation actually reschedules
    them, not merely that they happen to already be close to `now`.
    """
    async with TestingSessionLocal() as session:
        stale_signing_time = datetime.now(timezone.utc) - timedelta(days=200)
        loan = Loan(
            order_id=order.id,
            user_id=order.user_id,
            loan_number=f"L-TEST-{order.id}",
            principal_amount=3900,
            profit_amount=100,
            total_repayable=3900,
            down_payment_amount=1300,
            balance_financed=3900,
            profit_rate_pct=2.5,
            plan_type="murabaha",
            installment_count=installment_count,
            installment_amount=1300,
            total_paid=0.0,
            total_outstanding=3900,
            late_fee_total=0.0,
            status="active",
        )
        session.add(loan)
        await session.flush()

        for n in range(1, installment_count + 1):
            session.add(Installment(
                loan_id=loan.id,
                user_id=order.user_id,
                installment_number=n,
                is_down_payment=False,
                principal_portion=1300,
                profit_portion=33.3,
                total_amount=1300,
                due_date=(stale_signing_time + timedelta(days=30 * n)).date(),
                status="pending",
                paid_amount=0.0,
                days_overdue=0,
                late_fee_amount=0.0,
                late_fee_waived=False,
                retry_count=0,
            ))

        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        db_order.loan_id = loan.id
        for sibling in (share_with or []):
            sibling_row = await session.scalar(select(Order).where(Order.id == sibling.id))
            sibling_row.loan_id = loan.id

        await session.commit()
        await session.refresh(loan)
        return loan


def _make_envelope(event: str, order_id: int, new_status: str | None = None) -> dict:
    payload = {"order_id": order_id}
    if new_status is not None:
        payload["new_status"] = new_status
    return {"event": event, "payload": payload}


async def test_apply_delivery_status_envelope_transitions_to_in_transit(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.DELIVERY_PENDING)
    envelope = _make_envelope("delivery.status_changed", order.id, "in_transit")

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_status_envelope(session, envelope)
        assert changed is True

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        assert db_order.status == OrderState.IN_TRANSIT
        history = (await session.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id))).all()
        assert len(history) == 1
        assert history[0].to_status == OrderState.IN_TRANSIT


async def test_apply_delivery_confirmed_envelope_transitions_to_delivered(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.IN_TRANSIT)
    envelope = _make_envelope("delivery.confirmed", order.id)

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_confirmed_envelope(session, envelope)
        assert changed is True

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        assert db_order.status == OrderState.DELIVERED


async def test_apply_delivery_confirmed_envelope_reschedules_pending_installments(test_user):
    """P0-04: installment due dates must anchor to delivery confirmation, not
    the stale contract-signing date — otherwise a customer starts owing
    installments for goods they haven't received yet, and the schedule never
    reflects when the item actually arrived.
    """
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.IN_TRANSIT)
    loan = await _seed_loan_with_installments(order, installment_count=3)
    envelope = _make_envelope("delivery.confirmed", order.id)

    before = datetime.now(timezone.utc).date()
    async with TestingSessionLocal() as session:
        changed = await apply_delivery_confirmed_envelope(session, envelope)
        assert changed is True
    after = datetime.now(timezone.utc).date()

    async with TestingSessionLocal() as session:
        installments = (
            await session.scalars(
                select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number)
            )
        ).all()
        assert len(installments) == 3
        for inst in installments:
            expected_earliest = before + timedelta(days=30 * inst.installment_number)
            expected_latest = after + timedelta(days=30 * inst.installment_number)
            assert expected_earliest <= inst.due_date <= expected_latest, (
                f"installment {inst.installment_number} due_date {inst.due_date} was not "
                f"rescheduled relative to delivery confirmation time"
            )


async def test_apply_delivery_confirmed_envelope_reschedules_shared_cart_loan(test_user):
    """Cart orders share one Loan whose Loan.order_id only points at the
    primary sibling — confirming delivery on a NON-primary sibling order must
    still find and reschedule the shared installments via Order.loan_id.
    """
    user, _token = test_user
    primary_order = await _seed_order(user.id, OrderState.IN_TRANSIT, label="cart-primary")
    sibling_order = await _seed_order(user.id, OrderState.IN_TRANSIT, label="cart-sibling")
    loan = await _seed_loan_with_installments(
        primary_order, installment_count=2, share_with=[sibling_order]
    )

    envelope = _make_envelope("delivery.confirmed", sibling_order.id)
    before = datetime.now(timezone.utc).date()
    async with TestingSessionLocal() as session:
        changed = await apply_delivery_confirmed_envelope(session, envelope)
        assert changed is True

    async with TestingSessionLocal() as session:
        installments = (
            await session.scalars(
                select(Installment).where(Installment.loan_id == loan.id).order_by(Installment.installment_number)
            )
        ).all()
        assert len(installments) == 2
        assert installments[0].due_date >= before + timedelta(days=29)


async def test_apply_delivery_status_envelope_ignores_unknown_status(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.DELIVERY_PENDING)
    envelope = _make_envelope("delivery.status_changed", order.id, "returned")

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_status_envelope(session, envelope)
        assert changed is False

    async with TestingSessionLocal() as session:
        db_order = await session.scalar(select(Order).where(Order.id == order.id))
        assert db_order.status == OrderState.DELIVERY_PENDING


async def test_apply_delivery_status_envelope_idempotent(test_user):
    user, _token = test_user
    order = await _seed_order(user.id, OrderState.IN_TRANSIT)
    envelope = _make_envelope("delivery.status_changed", order.id, "in_transit")

    async with TestingSessionLocal() as session:
        changed = await apply_delivery_status_envelope(session, envelope)
        assert changed is False

    async with TestingSessionLocal() as session:
        history = (await session.scalars(select(OrderStatusHistory).where(OrderStatusHistory.order_id == order.id))).all()
        assert len(history) == 0
