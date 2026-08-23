"""
Payment Initiate Consumer.

Consumes payment-execution jobs from the Redis queue:
  sk:queue:payment_initiate

Gateway is the only internet-reachable service, so its customer-facing
POST /api/v1/payments/{down-payment,installment/*/pay,refund/*} endpoints
(apps/gateway/src/api/v1/payments.py, admin_orders.py) create the
PaymentTransaction row, lpush a job here, and — outside local/dev, where a
DEV ONLY branch auto-confirms so the flow is testable without live gateway
credentials — return to the customer without ever calling a real payment
gateway. Nothing consumed this queue: docs/audits/gateway_microservice_audit.md
documents "PAYMENT_INITIATE -> Payment Orchestrator" as the intended handoff,
but no such consumer existed. In production this meant down payments,
installment payments, and refund requests never reached JazzCash/SafePay/
Raast at all — the same missing-consumer pattern already fixed for
PAYMENT_WEBHOOK (GAP-09) by payment_webhook_consumer.py, here for the queue
one step upstream of it.

This worker drives the actual gateway call for jobs Gateway already validated
and persisted, then updates the SAME PaymentTransaction row Gateway created
(matched by payment_id) rather than creating a second, disconnected one.

Handled event types:
  - payment.initiate_requested   (down payment)
  - payment.installment_requested
  - payment.refund_requested     (customer- or admin-initiated)

Unrecognized event types (e.g. loan.restructure_requested, a separate,
unimplemented admin feature — see docs/PRODUCTION_GAPS_REPORT.md GW-GAP-05)
are logged and dropped rather than guessed at.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from decimal import Decimal

from sqlalchemy import select

from sk_shared.constants import QueueName
from sk_shared.events import build_event_envelope, event_channel
from sk_shared.models.order import Order
from sk_shared.models.payment import Installment, PaymentTransaction
from sk_shared.redis_client import get_redis_client

from src.adapters.factory import GatewayAdapterFactory
from src.config import settings
from src.core.database import SessionLocal
from src.core.logging import setup_logging
from src.orchestration.refund_orchestrator import RefundOrchestrator
from src.services.routing_engine import GatewayRoutingEngine
from src.services.vcn import VcnService

logger = logging.getLogger(__name__)

DLQ_KEY = "sk:queue:dlq:payment_initiate"

# Gateways that use async redirect flows (webhook confirms payment later)
# rather than confirming synchronously in the initiate call.
_ASYNC_GATEWAYS = {"safepay", "raast"}


class PaymentInitiateConsumer:
    def __init__(self, redis=None, concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running = True
        self._redis = redis

    def stop(self) -> None:
        logger.info("Payment initiate consumer received shutdown signal")
        self._running = False

    async def run(self) -> None:
        if self._redis is None:
            self._redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
            close_redis = True
        else:
            close_redis = False

        logger.info(
            "Payment initiate consumer started",
            extra={"concurrency": self._semaphore._value},
        )

        try:
            while self._running:
                job = await self._redis.redis.brpop(QueueName.PAYMENT_INITIATE, timeout=5)
                if job is None:
                    continue

                raw_payload = job[1]
                asyncio.create_task(self._process(raw_payload))
        finally:
            if close_redis:
                await self._redis.close()
            logger.info("Payment initiate consumer stopped cleanly")

    async def _process(self, raw_payload: bytes) -> None:
        async with self._semaphore:
            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("Unparseable payment initiate job", extra={"error": str(exc)})
                return

            event = payload.get("event", "unknown")
            retry_count = payload.get("_retry_count", 0)

            try:
                async with SessionLocal() as db:
                    await self._handle(db, payload)
                logger.info("Payment initiate job completed", extra={"event": event})
            except Exception as exc:
                logger.error(
                    "Payment initiate job failed",
                    extra={"event": event, "error": str(exc), "retry_count": retry_count},
                )
                if retry_count < settings.DLQ_MAX_RETRIES:
                    payload["_retry_count"] = retry_count + 1
                    backoff_delay = 5 * (2 ** retry_count)
                    logger.info(
                        "Payment initiate job waiting for backoff",
                        extra={"event": event, "retry_count": retry_count + 1, "delay_sec": backoff_delay},
                    )
                    await asyncio.sleep(backoff_delay)
                    await self._redis.redis.lpush(QueueName.PAYMENT_INITIATE, json.dumps(payload))
                    logger.info("Payment initiate job re-queued after backoff", extra={"event": event})
                else:
                    await self._redis.redis.lpush(DLQ_KEY, raw_payload)
                    logger.error(
                        "Payment initiate job sent to DLQ — max retries exceeded",
                        extra={"event": event, "dlq": DLQ_KEY},
                    )

    async def _handle(self, db, payload: dict) -> None:
        event = payload.get("event")
        if event == "payment.initiate_requested":
            await self._handle_down_payment(db, payload)
        elif event == "payment.installment_requested":
            await self._handle_installment(db, payload)
        elif event == "payment.refund_requested":
            await self._handle_refund(db, payload)
        else:
            logger.warning("Unknown payment initiate event — dropping", extra={"event": event})

    async def _select_and_call(self, order_id: int, amount_pkr: Decimal, preferred_gateway: str | None):
        """Select a gateway and call its adapter. Returns (gateway_name, result_dict)."""
        routing = GatewayRoutingEngine(self._redis)
        selected_gateway = await routing.select_gateway(preferred=preferred_gateway)
        adapter = GatewayAdapterFactory.get(selected_gateway, settings)

        try:
            result = await adapter.initiate_payment(
                order_id=order_id,
                amount_pkr=amount_pkr,
                callback_url=f"{settings.GATEWAY_PUBLIC_URL}/api/v1/webhooks/payment/{selected_gateway}",
            )
            await routing.record_success(selected_gateway)
            return selected_gateway, result
        except Exception:
            await routing.record_failure(selected_gateway)
            raise

    async def _handle_down_payment(self, db, payload: dict) -> None:
        payment_id = payload.get("payment_id")
        order_id = payload.get("order_id")
        amount_pkr = Decimal(str(payload.get("amount", "0")))

        txn = await db.get(PaymentTransaction, payment_id)
        if txn is None or txn.status != "initiated":
            logger.info(
                "Down payment transaction missing or already processed — skipping",
                extra={"payment_id": payment_id},
            )
            return

        try:
            selected_gateway, result = await self._select_and_call(
                order_id, amount_pkr, payload.get("gateway")
            )
        except Exception as exc:
            txn.status = "failed"
            txn.failure_message = str(exc)[:500]
            await db.commit()
            logger.error("Down payment gateway call failed", extra={"payment_id": payment_id, "error": str(exc)})
            return

        txn.gateway = selected_gateway
        txn.gateway_txn_id = result.get("gateway_txn_id")
        txn.gateway_response = result

        if selected_gateway in _ASYNC_GATEWAYS:
            txn.status = "pending"
            await db.commit()
            return

        # confirm_down_payment() looks up this same PaymentTransaction row by
        # status IN (initiated, pending) to queue the outbox event that tells
        # Gateway to advance Order.status past CONTRACTS_SIGNED — it must run
        # while txn is still "initiated", or that lookup finds nothing and
        # Gateway is never notified even though the charge succeeded.
        service = VcnService(db, self._redis)
        await service.confirm_down_payment(
            order_id=order_id, amount_pkr=amount_pkr, gateway_txn_id=txn.gateway_txn_id or ""
        )
        txn.status = "success"
        order = await db.scalar(select(Order).where(Order.id == order_id))
        await service.queue_issue(
            order_id=order_id,
            amount_pkr=Decimal(str(order.total_amount)) if order else amount_pkr,
            merchant_domain=None,
        )
        await db.commit()

    async def _handle_installment(self, db, payload: dict) -> None:
        payment_id = payload.get("payment_id")
        installment_id = payload.get("installment_id")
        amount_pkr = Decimal(str(payload.get("amount", "0")))

        txn = await db.get(PaymentTransaction, payment_id)
        if txn is None or txn.status != "initiated":
            logger.info(
                "Installment transaction missing or already processed — skipping",
                extra={"payment_id": payment_id},
            )
            return

        installment = await db.get(Installment, installment_id)
        if installment is None:
            txn.status = "failed"
            txn.failure_message = "INSTALLMENT_NOT_FOUND"
            await db.commit()
            return

        try:
            selected_gateway, result = await self._select_and_call(
                installment.loan_id, amount_pkr, payload.get("gateway")
            )
        except Exception as exc:
            txn.status = "failed"
            txn.failure_message = str(exc)[:500]
            await db.commit()
            logger.error("Installment gateway call failed", extra={"payment_id": payment_id, "error": str(exc)})
            return

        txn.gateway = selected_gateway
        txn.gateway_txn_id = result.get("gateway_txn_id")
        txn.gateway_response = result

        if selected_gateway in _ASYNC_GATEWAYS:
            txn.status = "pending"
            await db.commit()
            return

        txn.status = "success"
        await db.commit()

        # BV-04: do NOT set installment.status directly — Ledger Service owns
        # installment state transitions. Emit the event it listens for.
        envelope = build_event_envelope(
            event="payment.installment_paid",
            source_service="payment-orchestrator",
            payload={
                "installment_id": installment.id,
                "loan_id": installment.loan_id,
                "user_id": installment.user_id,
                "amount_pkr": str(amount_pkr),
                "gateway_txn_id": txn.gateway_txn_id,
            },
        )
        await self._redis.publish(event_channel("payment.installment_paid"), envelope.to_json())

    async def _handle_refund(self, db, payload: dict) -> None:
        order_id = payload.get("order_id")
        user_id = payload.get("user_id")
        amount_pkr = Decimal(str(payload.get("amount", "0")))
        reason = payload.get("reason", "refund_requested")

        original_txn = await db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.order_id == order_id,
                PaymentTransaction.status == "success",
                PaymentTransaction.amount > 0,
            ).order_by(PaymentTransaction.id.asc()).limit(1)
        )
        if original_txn is None:
            logger.warning(
                "Refund requested but no successful payment found for order — dropping",
                extra={"order_id": order_id},
            )
            return

        orchestrator = RefundOrchestrator(db)
        await orchestrator.initiate_refund(
            payment_workflow_id=0,
            order_id=order_id,
            user_id=user_id or original_txn.user_id,
            amount_pkr=amount_pkr,
            reason=reason,
            refund_reference=f"refund_{order_id}_{uuid.uuid4().hex[:12]}",
            gateway=original_txn.gateway,
            gateway_txn_id=original_txn.gateway_txn_id or "",
        )
        await db.commit()


def main() -> None:
    setup_logging("payment-initiate-consumer", settings.LOG_LEVEL)
    worker = PaymentInitiateConsumer(concurrency=settings.PAYMENT_INITIATE_WORKER_CONCURRENCY)

    loop = asyncio.get_event_loop()

    def _handle_signal(*_):
        worker.stop()

    import signal
    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    loop.run_until_complete(worker.run())


if __name__ == "__main__":
    main()
