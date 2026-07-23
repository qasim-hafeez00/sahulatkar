import pytest

from sk_shared.events import (
    EVENT_LOAN_CREATED,
    EventEnvelopeSchema,
    build_event_envelope,
    event_channel,
)


def test_build_event_envelope_populates_ids_and_timestamp():
    envelope = build_event_envelope(
        event=EVENT_LOAN_CREATED,
        source_service="credit-engine",
        payload={"loan_id": 1},
    )
    assert envelope.event == EVENT_LOAN_CREATED
    assert envelope.source_service == "credit-engine"
    assert envelope.payload == {"loan_id": 1}
    assert envelope.event_id
    assert envelope.correlation_id
    assert envelope.timestamp


def test_build_event_envelope_reuses_provided_correlation_id():
    envelope = build_event_envelope(
        event=EVENT_LOAN_CREATED,
        source_service="credit-engine",
        payload={},
        correlation_id="corr-123",
    )
    assert envelope.correlation_id == "corr-123"


def test_build_event_envelope_rejects_unknown_event():
    with pytest.raises(ValueError, match="Unknown event"):
        build_event_envelope(
            event="not.a.registered.event",
            source_service="credit-engine",
            payload={},
        )


def test_event_envelope_schema_rejects_empty_source_service():
    with pytest.raises(ValueError):
        EventEnvelopeSchema(
            event=EVENT_LOAN_CREATED,
            event_id="evt-1",
            timestamp="2026-01-01T00:00:00Z",
            source_service="   ",
            correlation_id="corr-1",
            payload={},
        )


def test_event_envelope_schema_rejects_non_dict_payload():
    with pytest.raises(ValueError):
        EventEnvelopeSchema(
            event=EVENT_LOAN_CREATED,
            event_id="evt-1",
            timestamp="2026-01-01T00:00:00Z",
            source_service="credit-engine",
            correlation_id="corr-1",
            payload=["not", "a", "dict"],
        )


def test_event_envelope_to_json_round_trips():
    envelope = build_event_envelope(
        event=EVENT_LOAN_CREATED,
        source_service="credit-engine",
        payload={"loan_id": 7},
    )
    import json

    decoded = json.loads(envelope.to_json())
    assert decoded["event"] == EVENT_LOAN_CREATED
    assert decoded["payload"] == {"loan_id": 7}


def test_event_channel_naming():
    assert event_channel(EVENT_LOAN_CREATED) == f"sk:events:{EVENT_LOAN_CREATED}"
