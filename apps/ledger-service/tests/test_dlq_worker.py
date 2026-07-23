from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import fakeredis.aioredis
import pytest

from sk_shared.events import event_channel
from sk_shared.redis_client import RedisClient
from src.config import settings
from src.events.dlq import DeadLetterMessage
from src.workers import dlq_worker
from src.workers.dlq_worker import DLQConsumer


def _install_fake_redis(consumer: DLQConsumer) -> RedisClient:
    """DLQConsumer.__init__ builds its Redis client via get_redis_client()
    against the real (unreachable in tests) settings.redis_url. Swap it for
    a RedisClient backed by fakeredis so publish()/get() actually work."""
    client = RedisClient(fakeredis.aioredis.FakeRedis())
    consumer._redis_client = client
    return client


def test_init_builds_redis_client_from_configured_url_and_db(monkeypatch, tmp_path):
    """DLQConsumer.__init__ must forward settings.redis_url/settings.redis_db
    unchanged to get_redis_client -- not drop either argument or pass None."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    captured: dict[str, object] = {}

    def _fake_get_redis_client(url, db=0):
        captured["url"] = url
        captured["db"] = db
        return RedisClient(fakeredis.aioredis.FakeRedis())

    monkeypatch.setattr(dlq_worker, "get_redis_client", _fake_get_redis_client)

    consumer = DLQConsumer()

    assert captured == {"url": settings.redis_url, "db": settings.redis_db}
    assert consumer._redis_client is not None


@pytest.mark.asyncio
async def test_run_once_with_empty_queue_returns_zero_stats(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        stats = await consumer.run_once()
        assert stats == {"total": 0, "retried": 0, "archived": 0, "skipped": 0}
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_retries_successfully_and_drains_queue_file(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=0)

        stats = await consumer.run_once()

        assert stats == {"total": 1, "retried": 1, "archived": 0, "skipped": 0}
        # Fully-drained queue: the DLQ file should be removed, not left as an empty file.
        assert not consumer.dlq.dlq_file.exists()
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_archives_messages_that_exhausted_retries(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_max_retries", 3)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=3)

        stats = await consumer.run_once()

        assert stats == {"total": 1, "retried": 0, "archived": 1, "skipped": 0}
        assert not consumer.dlq.dlq_file.exists()
        archive_files = list(tmp_path.glob("dlq_exhausted_*.jsonl"))
        assert len(archive_files) == 1
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_keeps_message_pending_and_bumps_retry_count_on_publish_failure(monkeypatch, tmp_path):
    """A message whose retry-publish fails must stay in the DLQ (not be lost)
    with its retry_count incremented, so a future run can retry it again and
    it eventually reaches dlq_max_retries and gets archived."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()

    class _BoomRedis:
        async def publish(self, channel, message):
            raise ConnectionError("redis connection refused")

        async def close(self):
            pass

    consumer._redis_client = _BoomRedis()
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=0)

        stats = await consumer.run_once()

        assert stats == {"total": 1, "retried": 0, "archived": 0, "skipped": 1}

        remaining = await consumer.dlq.get_messages()
        assert len(remaining) == 1
        assert remaining[0].retry_count == 1
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_retried_count_accumulates_across_multiple_successes(monkeypatch, tmp_path):
    """retried must be incremented (+= 1) once per successfully-retried
    message, not merely set to 1 -- two successes in one run must report
    retried == 2."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "one"}, RuntimeError("boom"), retry_count=0)
        await consumer.dlq.push("payment.installment_paid", {"foo": "two"}, RuntimeError("boom"), retry_count=0)

        stats = await consumer.run_once()

        assert stats == {"total": 2, "retried": 2, "archived": 0, "skipped": 0}
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_skipped_count_and_retry_count_increment_not_reset(monkeypatch, tmp_path):
    """skipped must accumulate (+= 1) per failed-publish message, and each
    failed message's retry_count must be incremented from its PRIOR value
    (not reset to a fixed 1)."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()

    class _BoomRedis:
        async def publish(self, channel, message):
            raise ConnectionError("redis connection refused")

        async def close(self):
            pass

    consumer._redis_client = _BoomRedis()
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "one"}, RuntimeError("boom"), retry_count=2)
        await consumer.dlq.push("payment.installment_paid", {"foo": "two"}, RuntimeError("boom"), retry_count=0)

        stats = await consumer.run_once()

        assert stats == {"total": 2, "retried": 0, "archived": 0, "skipped": 2}

        remaining = await consumer.dlq.get_messages()
        remaining_by_marker = {m.payload["foo"]: m.retry_count for m in remaining}
        assert remaining_by_marker == {"one": 3, "two": 1}
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_skips_rebuild_when_archiving_exhausted_message_fails(monkeypatch, tmp_path):
    """If every message this run is exhausted (not retryable) and archiving
    that message fails, retried/archived/skipped all stay 0. The rebuild
    condition (`retried > 0 or archived > 0 or skipped > 0`) must then be
    False, leaving the DLQ file untouched -- not rebuilt/emptied, which
    would silently drop the message that was never actually archived."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_max_retries", 1)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=1)

        original_bytes = consumer.dlq.dlq_file.read_bytes()

        def _boom_dumps(*args, **kwargs):
            raise TypeError("simulated json failure")

        monkeypatch.setattr(dlq_worker.json, "dumps", _boom_dumps)

        stats = await consumer.run_once()

        assert stats == {"total": 1, "retried": 0, "archived": 0, "skipped": 0}
        assert consumer.dlq.dlq_file.read_bytes() == original_bytes
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_archive_exhausted_creates_nested_audit_directory(monkeypatch, tmp_path):
    """archive_dir.mkdir must be called with parents=True -- a
    reconciliation_audit_dir whose parent doesn't exist yet must still work,
    not raise FileNotFoundError."""
    nested_dir = tmp_path / "nested" / "audit"
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(nested_dir))
    monkeypatch.setattr(settings, "dlq_max_retries", 1)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=1)

        stats = await consumer.run_once()

        assert stats["archived"] == 1
        assert list(nested_dir.glob("dlq_exhausted_*.jsonl"))
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_archive_exhausted_writes_full_message_content(monkeypatch, tmp_path):
    """The archived JSONL entry must contain the actual message data, not
    just an empty/placeholder line -- nothing else asserts on file content."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_max_retries", 1)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=1)

        await consumer.run_once()

        archive_file = next(tmp_path.glob("dlq_exhausted_*.jsonl"))
        archived = json.loads(archive_file.read_text(encoding="utf-8").strip())
        assert archived["event_name"] == "payment.installment_paid"
        assert archived["payload"] == {"foo": "bar"}
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_once_logs_critical_when_depth_exceeds_alert_threshold(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_alert_threshold", 1)
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        await consumer.dlq.push("payment.installment_paid", {"foo": "bar"}, RuntimeError("boom"), retry_count=0)

        with caplog.at_level(logging.CRITICAL, logger="src.workers.dlq_worker"):
            await consumer.run_once()

        assert any("DLQ depth exceeds alert threshold" in record.message for record in caplog.records)
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_retry_message_falls_back_gracefully_on_malformed_json_string_payload(monkeypatch, tmp_path):
    """DeadLetterMessage.payload can be a raw string (e.g. re-hydrated from an
    older/foreign schema). If it looks like JSON but isn't valid, the retry
    must not blow up -- it should fall back to wrapping the raw string."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)
    try:
        msg = DeadLetterMessage(
            event_name="payment.installment_paid",
            payload="not-valid-json{{{",
            error_type="RuntimeError",
            error_message="boom",
            timestamp=datetime.now(timezone.utc),
            retry_count=0,
        )
        success = await consumer._retry_message(msg)
        assert success is True
    finally:
        await consumer.close()


class _CapturingRedis:
    """Fake redis client that records publish() calls verbatim instead of
    actually publishing, so tests can assert on the exact channel/payload
    the worker sent -- nothing else inspects what gets published."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel, message) -> None:
        self.published.append((channel, message))

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_retry_message_parses_valid_json_string_payload(monkeypatch, tmp_path):
    """A string payload that IS valid JSON (e.g. re-hydrated from an older
    schema) must be parsed into its dict form and published on the message's
    own event channel -- not silently dropped to None, wrapped as a raw
    string, or published on the wrong channel."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 0.0)
    consumer = DLQConsumer()
    fake = _CapturingRedis()
    consumer._redis_client = fake
    try:
        msg = DeadLetterMessage(
            event_name="payment.installment_paid",
            payload=json.dumps({"loan_id": 42}),
            error_type="RuntimeError",
            error_message="boom",
            timestamp=datetime.now(timezone.utc),
            retry_count=0,
        )
        success = await consumer._retry_message(msg)

        assert success is True
        assert len(fake.published) == 1
        channel, raw_envelope = fake.published[0]
        assert channel == event_channel("payment.installment_paid")
        envelope = json.loads(raw_envelope)
        assert envelope["payload"] == {"loan_id": 42}
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_retry_message_uses_exponential_backoff_delay(monkeypatch, tmp_path):
    """delay = dlq_retry_base_delay_seconds * (2 ** retry_count) -- every
    other test zeroes out the base delay, so the formula itself is never
    otherwise asserted on."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_retry_base_delay_seconds", 1.0)
    consumer = DLQConsumer()
    consumer._redis_client = _CapturingRedis()

    captured_delays: list[float] = []

    async def _fake_sleep(seconds):
        captured_delays.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    try:
        msg = DeadLetterMessage(
            event_name="payment.installment_paid",
            payload={"foo": "bar"},
            error_type="RuntimeError",
            error_message="boom",
            timestamp=datetime.now(timezone.utc),
            retry_count=3,
        )
        await consumer._retry_message(msg)

        assert captured_delays == [8.0]  # 1.0 * (2 ** 3)
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_run_forever_continues_after_unhandled_error_in_run_once(monkeypatch, tmp_path):
    """run_forever wraps run_once() in try/except so a single bad iteration
    doesn't kill the whole background worker process."""
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))
    monkeypatch.setattr(settings, "dlq_poll_interval_seconds", 0.0)
    consumer = DLQConsumer()
    _install_fake_redis(consumer)

    call_count = {"n": 0}

    async def _flaky_run_once():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("transient failure")
        # BaseException (not caught by `except Exception`) used purely as a
        # test sentinel to break out of the intentionally-infinite loop once
        # we've proven a second iteration happened after the first failed.
        raise asyncio.CancelledError()

    consumer.run_once = _flaky_run_once
    try:
        with pytest.raises(asyncio.CancelledError):
            await consumer.run_forever()
        assert call_count["n"] == 2
    finally:
        await consumer.close()


@pytest.mark.asyncio
async def test_main_closes_consumer_even_if_run_forever_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "reconciliation_audit_dir", str(tmp_path))

    close_calls = {"n": 0}

    async def _fake_run_forever(self):
        raise RuntimeError("loop crashed")

    async def _fake_close(self):
        close_calls["n"] += 1

    monkeypatch.setattr(DLQConsumer, "run_forever", _fake_run_forever)
    monkeypatch.setattr(DLQConsumer, "close", _fake_close)

    with pytest.raises(RuntimeError, match="loop crashed"):
        await dlq_worker.main()

    assert close_calls["n"] == 1
