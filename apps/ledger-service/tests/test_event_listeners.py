import pytest

from src.core.event_listeners import EventProcessingFailed, _run_with_retry


@pytest.mark.asyncio
async def test_run_with_retry_retries_transient_and_succeeds():
    attempts = {"count": 0}

    async def flaky() -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ConnectionError("temporary network failure")

    retries = await _run_with_retry(flaky, max_retries=3, base_delay_seconds=0)
    assert retries == 1


@pytest.mark.asyncio
async def test_run_with_retry_does_not_retry_non_transient():
    async def non_transient() -> None:
        raise ValueError("bad payload")

    with pytest.raises(EventProcessingFailed) as exc_info:
        await _run_with_retry(non_transient, max_retries=3, base_delay_seconds=0)

    assert exc_info.value.retry_count == 0
    assert isinstance(exc_info.value.cause, ValueError)


@pytest.mark.asyncio
async def test_run_with_retry_stops_after_max_retries():
    async def always_transient() -> None:
        raise TimeoutError("database timeout")

    with pytest.raises(EventProcessingFailed) as exc_info:
        await _run_with_retry(always_transient, max_retries=2, base_delay_seconds=0)

    assert exc_info.value.retry_count == 2
    assert isinstance(exc_info.value.cause, TimeoutError)
