"""
Payment Webhook Consumer.

Consumes normalized vendor-webhook jobs from the Redis queue:
  sk:queue:payment_webhook

Gateway is the only internet-reachable service (see
infra/k8s/base/network-policies/13-payment-orchestrator.yaml). Its
POST /api/v1/webhooks/payment/{jazzcash,safepay,stripe} endpoints verify the
vendor's HMAC signature, dedupe, and lpush a normalized envelope here instead
of processing the payment themselves — this worker is the other half of that
handoff, documented in docs/audits/gateway_microservice_audit.md as
"Webhooks (any provider) -> Redis PAYMENT_WEBHOOK queue -> Payment
Orchestrator" but never actually built (GAP-09).

Payment Orchestrator's own /api/v1/webhooks.py endpoints (direct
JazzCash/SafePay/Stripe HTTP webhooks with their own signature schemes) stay
in place for direct-integration/local testing, but are not reachable from
outside the cluster today. This worker reuses the exact same downstream
processing (VcnService.confirm_down_payment + queue_issue,
VcnOrchestrator.handle_stripe_event) so both paths behave identically.

Signature verification already happened at Gateway before the job was
enqueued — this worker trusts the internal queue and does not re-verify.

Features mirror VcnIssueWorker: concurrency via asyncio.Semaphore, graceful
shutdown, DLQ after DLQ_MAX_RETRIES failures, exponential backoff re-queue.
"""
from __future__ import annotations

import asyncio
import json
import logging
from decimal import Decimal

from sk_shared.constants import QueueName
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.core.database import SessionLocal
from src.core.logging import setup_logging
from src.services.jazzcash import JazzCashClient
from src.services.safepay import SafepayClient
from src.services.vcn import VcnService

logger = logging.getLogger(__name__)

DLQ_KEY = "sk:queue:dlq:payment_webhook"

_SAFEPAY_SUCCESS_STATUSES = {"PAID", "paid", "success"}


class PaymentWebhookConsumer:
    def __init__(self, redis=None, concurrency: int = 4) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._running = True
        self._redis = redis

    def stop(self) -> None:
        logger.info("Payment webhook consumer received shutdown signal")
        self._running = False

    async def run(self) -> None:
        if self._redis is None:
            self._redis = get_redis_client(settings.REDIS_URL, db=settings.REDIS_DB)
            close_redis = True
        else:
            close_redis = False

        logger.info(
            "Payment webhook consumer started",
            extra={"concurrency": self._semaphore._value},
        )

        try:
            while self._running:
                job = await self._redis.redis.brpop(QueueName.PAYMENT_WEBHOOK, timeout=5)
                if job is None:
                    continue

                raw_payload = job[1]
                asyncio.create_task(self._process(raw_payload))
        finally:
            if close_redis:
                await self._redis.close()
            logger.info("Payment webhook consumer stopped cleanly")

    async def _process(self, raw_payload: bytes) -> None:
        async with self._semaphore:
            try:
                payload = json.loads(raw_payload.decode("utf-8"))
            except json.JSONDecodeError as exc:
                logger.error("Unparseable payment webhook job", extra={"error": str(exc)})
                return

            gateway = payload.get("gateway", "unknown")
            retry_count = payload.get("_retry_count", 0)

            try:
                async with SessionLocal() as db:
                    await self._handle(db, payload)
                logger.info("Payment webhook job completed", extra={"gateway": gateway})
            except Exception as exc:
                logger.error(
                    "Payment webhook job failed",
                    extra={"gateway": gateway, "error": str(exc), "retry_count": retry_count},
                )
                if retry_count < settings.DLQ_MAX_RETRIES:
                    payload["_retry_count"] = retry_count + 1
                    backoff_delay = 5 * (2 ** retry_count)
                    logger.info(
                        "Payment webhook job waiting for backoff",
                        extra={"gateway": gateway, "retry_count": retry_count + 1, "delay_sec": backoff_delay},
                    )
                    await asyncio.sleep(backoff_delay)
                    await self._redis.redis.lpush(QueueName.PAYMENT_WEBHOOK, json.dumps(payload))
                    logger.info("Payment webhook job re-queued after backoff", extra={"gateway": gateway})
                else:
                    await self._redis.redis.lpush(DLQ_KEY, raw_payload)
                    logger.error(
                        "Payment webhook job sent to DLQ — max retries exceeded",
                        extra={"gateway": gateway, "dlq": DLQ_KEY},
                    )

    async def _handle(self, db, payload: dict) -> None:
        gateway = payload.get("gateway")
        raw = payload.get("raw") or {}

        if gateway == "jazzcash":
            await self._handle_jazzcash(db, raw)
        elif gateway == "safepay":
            await self._handle_safepay(db, raw)
        elif gateway == "stripe":
            await self._handle_stripe(db, raw)
        else:
            logger.warning("Unknown gateway in payment webhook job — dropping", extra={"gateway": gateway})

    async def _handle_jazzcash(self, db, raw: dict) -> None:
        client = JazzCashClient(settings.JAZZCASH_MERCHANT_ID, settings.JAZZCASH_PASSWORD)
        event = client.parse_event(json.dumps(raw).encode("utf-8"))

        if event.get("status") != "success":
            logger.info("JazzCash webhook job ignored — non-success status", extra={"order_id": event.get("order_id")})
            return

        await self._confirm_and_issue(db, event, merchant_domain=None)

    async def _handle_safepay(self, db, raw: dict) -> None:
        client = SafepayClient(settings.SAFEPAY_API_KEY, settings.SAFEPAY_API_SECRET)
        event = client.parse_event(json.dumps(raw).encode("utf-8"))

        if event.get("status") not in _SAFEPAY_SUCCESS_STATUSES:
            logger.info("SafePay webhook job ignored — non-success status", extra={"order_id": event.get("order_id")})
            return

        await self._confirm_and_issue(db, event, merchant_domain=raw.get("merchant_domain"))

    async def _confirm_and_issue(self, db, event: dict, *, merchant_domain: str | None) -> None:
        order_id = event.get("order_id")
        if order_id is None:
            logger.error("Payment webhook job missing order_id — cannot process")
            return

        amount_pkr = Decimal(str(event["amount_pkr"]))
        service = VcnService(db, self._redis)
        await service.confirm_down_payment(
            order_id=int(order_id),
            amount_pkr=amount_pkr,
            gateway_txn_id=event.get("gateway_txn_id", ""),
        )
        await service.queue_issue(
            order_id=int(order_id),
            amount_pkr=amount_pkr,
            merchant_domain=merchant_domain,
        )
        await db.commit()

    async def _handle_stripe(self, db, raw: dict) -> None:
        from src.orchestration.vcn_orchestrator import VcnOrchestrator

        event_type = raw.get("type")
        data_object = raw.get("data", {}).get("object", {})
        if not event_type:
            logger.warning("Stripe webhook job missing event type — dropping")
            return

        orchestrator = VcnOrchestrator(db, self._redis)
        await orchestrator.handle_stripe_event(event_type, data_object)
        await db.commit()


def main() -> None:
    setup_logging("payment-webhook-consumer", settings.LOG_LEVEL)
    worker = PaymentWebhookConsumer(concurrency=settings.PAYMENT_WEBHOOK_WORKER_CONCURRENCY)

    loop = asyncio.get_event_loop()

    def _handle_signal(*_):
        worker.stop()

    import signal
    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    loop.run_until_complete(worker.run())


if __name__ == "__main__":
    main()
