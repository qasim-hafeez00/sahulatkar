# ER Diagram

**Status:** STABLE (textual relationship map) — an actual rendered ER diagram exists in the original research materials (`Desktop/bnpl/uml/diagrams/ER_Diagram.webp`, mirrored nowhere in this knowledge base yet) but has not been reproduced here; this document is the textual equivalent for the core entity relationships, sufficient for a reader without opening the image.

## Core entity relationships

```
users (1) ──< (many) orders
users (1) ──< (many) user_kyc_verifications
users (1) ──< (many) user_devices
users (1) ──< (many) loans
users (1) ──< (many) credit_applications
users (1) ──< (many) risk_assessments

orders (1) ──  (1) products               [via extraction]
orders (1) ──  (1) wakalah_agreements
orders (1) ──  (1) murabaha_contracts
orders (1) ──  (1) loans
orders (1) ──  (1) virtual_cards
orders (1) ──  (1) purchase_executions    [can be 1-to-many across retry attempts]
orders (1) ──  (1) shipments

loans (1) ──< (many) installments
loans (1) ──  (1) murabaha_contracts

installments (1) ──< (many) payment_transactions   [retries create multiple attempts]

journal_entries (1) ──< (many) journal_entry_lines
journal_entry_lines (many) ── (1) ledger_accounts

merchants (1) ──< (many) products
merchants (1) ──< (many) scraping_jobs

shipments (1) ──< (many) tracking_events
shipments (many) ── (1) couriers

installments (1) ──  (1) late_fee_charity_allocations   [when a late fee is charged]
```

## Key relationship notes

- `orders` is the central hub — nearly every domain table (contracts, loans, VCN, shipment, purchase execution) relates back to it 1:1, reflecting the platform's one-order-one-loan financing model (see [`../03-bnpl-financing/12-bnpl-product-specification.md`](../03-bnpl-financing/12-bnpl-product-specification.md)).
- `journal_entries`/`journal_entry_lines` connects to the rest of the schema only via the polymorphic `source_type`/`source_id` pair on the entry header — not a foreign key, since a journal entry can originate from many different table types (a loan, a payment, a manual correction).
- The original UML/ER diagram (`Desktop/bnpl/uml/diagrams/ER_Diagram.webp`) should be treated as the visual reference if a graphical diagram is needed — this knowledge base does not re-render it, but it exists in the source research materials.

## Related documents

[`25-database-architecture.md`](25-database-architecture.md), [`26-database-dictionary.md`](26-database-dictionary.md), [`132-database-schema-documentation.md`](132-database-schema-documentation.md).
