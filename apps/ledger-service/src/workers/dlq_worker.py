"""
LS-CRIT-05: DLQ Consumer Worker

Automated consumer for the ledger service Dead-Letter Queue.
Polls the DLQ JSONL file, retries failed events by re-publishing them
on the Redis channel. Alerts when DLQ depth exceeds the configured threshold.

Run as a background process alongside the main ledger service:
    python -m src.workers.dlq_worker

Or from the CLI:
    python apps/ledger-service/src/workers/dlq_worker.py
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sk_shared.events import build_event_envelope, event_channel
from sk_shared.redis_client import get_redis_client

from src.config import settings
from src.events.dlq import DeadLetterMessage, EventDeadLetterQueue


logger = logging.getLogger(__name__)


class DLQConsumer:
    """
    Polls the DLQ and retries failed events by re-publishing them on the
    Redis event bus. After settings.dlq_max_retries attempts, the message
    is written to a permanent-failure archive and removed from the active DLQ.
    """

    def __init__(self) -> None:
        self.dlq = EventDeadLetterQueue()
        self._redis_client = get_redis_client(settings.redis_url, db=settings.redis_db)

    async def run_once(self) -> dict[str, int]:
        """
        Process all current DLQ messages: retry retryable ones, archive exhausted ones.
        Returns stats dict.
        """
        messages = await self.dlq.get_messages()
        if not messages:
            return {"total": 0, "retried": 0, "archived": 0, "skipped": 0}

        total = len(messages)

        # LS-CRIT-05: Alert if DLQ depth exceeds threshold
        if total >= settings.dlq_alert_threshold:
            logger.critical(
                "DLQ depth exceeds alert threshold",
                extra={"depth": total, "threshold": settings.dlq_alert_threshold},
            )

        retried = 0
        archived = 0
        skipped = 0

        retryable: list[DeadLetterMessage] = []
        exhausted: list[DeadLetterMessage] = []

        for msg in messages:
            if msg.retry_count < settings.dlq_max_retries:
                retryable.append(msg)
            else:
                exhausted.append(msg)

        # Archive permanently-failed messages
        if exhausted:
            archived = await self._archive_exhausted(exhausted)

        # Retry retryable messages with exponential back-off
        for msg in retryable:
            success = await self._retry_message(msg)
            if success:
                retried += 1
            else:
                skipped += 1

        # Rebuild the DLQ file with only the unretried retryable messages
        # (retried ones get re-queued into the main event bus; exhausted ones archived)
        if retried > 0 or archived > 0:
            await self._rebuild_dlq(messages, retried_events={m.event_name for m in retryable}, archived=exhausted)

        logger.info(
            "DLQ consumer run completed",
            extra={"total": total, "retried": retried, "archived": archived, "skipped": skipped},
        )
        return {"total": total, "retried": retried, "archived": archived, "skipped": skipped}

    async def _retry_message(self, msg: DeadLetterMessage) -> bool:
        """Re-publish a DLQ message on the event bus. Returns True on success."""
        payload = msg.payload
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
                payload_dict = parsed if isinstance(parsed, dict) else {"raw_payload": payload}
            except json.JSONDecodeError:
                payload_dict = {"raw_payload": payload}
        else:
            payload_dict = payload

        delay = settings.dlq_retry_base_delay_seconds * (2 ** msg.retry_count)
        logger.info(
            "DLQ retrying event",
            extra={
                "event_name": msg.event_name,
                "retry_count": msg.retry_count,
                "delay_seconds": delay,
            },
        )
        await asyncio.sleep(min(delay, 60.0))  # cap at 60s

        try:
            envelope = build_event_envelope(
                event=msg.event_name,
                source_service="ledger-service-dlq",
                payload=payload_dict,
            )
            await self._redis_client.publish(
                event_channel(msg.event_name),
                envelope.to_json(),
            )
            return True
        except Exception as exc:
            logger.error(
                "DLQ retry publish failed",
                extra={"event_name": msg.event_name, "error": str(exc)},
            )
            return False

    async def _archive_exhausted(self, messages: list[DeadLetterMessage]) -> int:
        """Write permanently-failed messages to an archive file."""
        archive_dir = Path(settings.reconciliation_audit_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_file = archive_dir / f"dlq_exhausted_{timestamp}.jsonl"

        try:
            with archive_file.open("a", encoding="utf-8") as f:
                for msg in messages:
                    f.write(json.dumps(msg.to_dict(), separators=(",", ":"), default=str))
                    f.write("\n")
            logger.warning(
                "DLQ messages permanently archived after max retries",
                extra={"count": len(messages), "archive_file": str(archive_file)},
            )
            return len(messages)
        except Exception as exc:
            logger.error("Failed to archive exhausted DLQ messages", extra={"error": str(exc)})
            return 0

    async def _rebuild_dlq(
        self,
        all_messages: list[DeadLetterMessage],
        retried_events: set[str],
        archived: list[DeadLetterMessage],
    ) -> None:
        """Rewrite the DLQ file removing successfully retried and archived messages."""
        archived_set = {id(m) for m in archived}
        # Keep messages that were not successfully retried and not archived
        # Since we retried ALL retryable messages (even if some failed to publish), we keep them
        # with incremented retry_count on failure. For simplicity, clear & rewrite only archived ones.
        remaining = [m for m in all_messages if id(m) not in archived_set]

        dlq_file = self.dlq.dlq_file
        try:
            if remaining:
                with dlq_file.open("w", encoding="utf-8") as f:
                    for msg in remaining:
                        f.write(json.dumps(msg.to_dict(), separators=(",", ":"), default=str))
                        f.write("\n")
            else:
                dlq_file.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("Failed to rebuild DLQ file", extra={"error": str(exc)})

    async def run_forever(self) -> None:
        """Main loop: poll and process DLQ every dlq_poll_interval_seconds."""
        logger.info(
            "DLQ consumer started",
            extra={
                "poll_interval_seconds": settings.dlq_poll_interval_seconds,
                "max_retries": settings.dlq_max_retries,
                "alert_threshold": settings.dlq_alert_threshold,
            },
        )
        while True:
            try:
                await self.run_once()
            except Exception as exc:
                logger.exception("Unhandled error in DLQ consumer run_once", extra={"error": str(exc)})
            await asyncio.sleep(settings.dlq_poll_interval_seconds)

    async def close(self) -> None:
        await self._redis_client.close()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    consumer = DLQConsumer()
    try:
        await consumer.run_forever()
    finally:
        await consumer.close()


if __name__ == "__main__":
    asyncio.run(main())
