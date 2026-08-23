# Event Schema

**Status:** STABLE (what exists) — the central finding of this document is that no enforced schema actually exists.

## Envelope structure (as designed)

`sk_shared`'s `build_event_envelope()` wraps a payload with metadata (event name, timestamp, presumably a source-service identifier) before publishing. This gives every event a consistent outer shape.

## The gap: no payload validation

**`build_event_envelope()` does not validate the payload against a Pydantic model or any other schema before publishing** (`SH-GAP-03`). This means any service can publish an event with a missing field, wrong type, or malformed structure, and nothing stops it — the first place a malformed event would be caught is whatever consumer tries to use the missing/wrong field, likely as a runtime error far from the actual mistake.

## Recommended fix

Define a Pydantic model per event type (in `sk_shared`, so both publisher and consumer import the same definition) and validate against it at publish time, not just hope the consumer's own parsing catches problems. This is the single highest-leverage fix for event reliability platform-wide, since it would catch malformed events at the source rather than downstream.

## Example schema definitions that should exist (illustrative, not yet implemented)

```python
class PaymentDownPaymentConfirmedEvent(BaseModel):
    order_id: UUID
    installment_id: UUID
    amount_pkr: Decimal
    vcn_id: str
    vcn_pan: str  # should this even be in an event payload — see security note below
    vcn_expiry: str
    vcn_cvv: str
```

**Security note:** the documented `payment.down_payment_confirmed` payload includes plaintext `vcn_pan`/`vcn_cvv` fields (per `docs/System-md-files/00Sahulatkar-System.md`'s integration-contract example) — given Redis Pub/Sub messages may be logged or observable to anything with Redis access, this is worth a dedicated security review: should raw card data ever travel through an event payload, even internally, or should the event carry only a reference (VCN ID) that the consumer separately fetches via the access-controlled decrypt endpoint? This is exactly the kind of design question a formal event-schema review would surface.

## Related documents

[`24-event-catalog.md`](24-event-catalog.md), [`../08-security/27-security-architecture.md`](../08-security/27-security-architecture.md).
