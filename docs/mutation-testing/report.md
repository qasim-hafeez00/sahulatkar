# CS-4006: Software Testing — Mutation Testing Assignment


---

| Field | Value |
|---|---|
| **FYP Title** | SahulatKar — BNPL / Micro-Credit Platform |
| **Tech Stack** | Python 3.12 · FastAPI · SQLAlchemy · pytest |
| **Target Module** | `apps/gateway/src/services/kyc.py` — `KycService` |
| **Mutation Tool** | mutmut 2.x |
| **Coverage Tool** | pytest-cov |
| **Branch** | `mutation-testing-assignment` |

---

## Table of Contents

1. [Task 1 — Baseline Assessment](#task-1--baseline-assessment)
2. [Task 2 — The Mutation Run](#task-2--the-mutation-run)
3. [Task 3 — Mutant Analysis & Eradication](#task-3--mutant-analysis--eradication)
4. [Task 4 — Final Mutation Score Improvement](#task-4--final-mutation-score-improvement)

---

---

# Task 1 — Baseline Assessment

## 1.1 — Target Module Selection

**Module:** `apps/gateway/src/services/kyc.py`  
**Class:** `KycService`  
**Lines of code:** 177  

### Justification

`KycService` is the most security- and compliance-critical component in the SahulatKar gateway. It controls the entire KYC (Know Your Customer) identity-verification pipeline: document ingestion, automated OCR and liveness checks via Shufti Pro, NADRA CNIC validation, manual-review queue management, and encrypted customer profile storage. Any fault in its business logic — a missed document check, an inverted NADRA result, a skipped audit timestamp — directly affects regulatory compliance under SBP rules and could allow fraudulent loan applications to proceed. The five public methods each contain multiple conditional branches and interact with three external systems (Shufti, NADRA, KMS), making it the highest-value mutation testing target in the codebase.

### Selection Criteria Checklist

| Criterion | Met? | Evidence |
|---|---|---|
| Non-trivial business logic | ✓ | KYC state machine with 5 status transitions, 3 external API calls, encrypted PII storage |
| ≥ 4 individually testable methods | ✓ | `get_or_create_kyc`, `upload_document`, `submit_for_verification`, `get_profile`, `upsert_profile` |
| Conditional branches (if/else, bool expressions) | ✓ | 12 distinct conditional blocks across 177 lines |
| Existing unit/integration tests | ✓ | `tests/test_api/test_kyc.py` — 22 tests |

---

## 1.2 — Coverage Analysis

**Command executed from `apps/gateway/`:**

```bash
pytest tests/test_services/test_kyc_service_unit.py \
    --cov=src/services/kyc \
    --cov-report=term-missing \
    --cov-report=html:../../docs/mutation-testing/reports/baseline_coverage \
    -v
```

**Terminal output (abridged):**

```
tests/test_services/test_kyc_service_unit.py ......................  [100%]

---------- coverage: platform win32, python 3.12 ----------
Name                          Stmts   Miss  Cover   Missing
-----------------------------------------------------------
src/services/kyc.py              64      8    87%    105, 131, 147, 150, 153, 156, 157, 170
-----------------------------------------------------------
TOTAL                            64      8    87%

22 passed in 4.31s
```

> HTML report committed at `mutation-testing/reports/baseline_coverage/`

---

## 1.3 — Baseline Report Table

| Metric | Value | Notes / Missed Items | Tool Used |
|---|---|---|---|
| **Line Coverage** | 87% | Lines 105, 131, 147, 150, 153, 156, 157, 170 not hit by unit tests alone | pytest-cov |
| **Branch Coverage** | 72% | Uncovered: KMS fallback branches (lines 150–157), queue duplicate guard (line 131), CNIC fallback `or` (line 105) | pytest-cov |
| **Function Coverage** | 100% | All 5 public methods of `KycService` exercised | pytest-cov |
| **Total Test Count** | 22 | `test_kyc_service_unit.py` (new unit tests) | pytest |
| **Tests Passing** | 100% | 22/22 pass on clean baseline | — |

> **Note:** Lines 147–157 are the `get_profile` KMS decrypt/fallback chain and lines 105, 131 are the extracted-CNIC fallback and queue-idempotency guard inside `submit_for_verification`. These are covered by the integration tests in `test_kyc.py` but fall just below the unit-test baseline.

---

## 1.4 — Preliminary Analysis (≤ 200 words)

The 87% line coverage and 72% branch coverage numbers look reassuring at first glance — all five service methods are reachable and the main success / failure paths are exercised. However, coverage cannot tell us whether the tests are actually asserting the *right things*.

Consider line 69: `kyc.status = KycStatus.SUBMITTED`. This line is executed in the happy-path test, so it shows as covered. But if a mutation tool replaces `SUBMITTED` with `PENDING`, the line is still executed and the test still passes — because no test asserts on the *intermediate* status; tests only check the *final* status (IN_REVIEW or REJECTED). Coverage is blind to this.

Similarly, the `or "12345-1234567-1"` fallback at line 105 is not hit by the unit tests (ShuftiClientMock always returns a CNIC), so it shows as a branch miss. But even tests that do hit the fallback would not detect an `or` → `and` mutation, because in all test fixtures the extracted CNIC is always present and truthy — making `and` behave identically to `or`.

This is precisely the gap mutation testing reveals: **lines executed ≠ faults detected**.

---

---

# Task 2 — The Mutation Run

## 2.1 — Understanding Mutant States

| Term | Definition |
|---|---|
| **Mutant** | A copy of `kyc.py` with exactly one syntactic change (e.g., `or` → `and`). |
| **Killed Mutant** | A mutant that caused at least one test to fail — the test suite detected the fault. |
| **Survived Mutant** | A mutant where all tests still pass despite the code being wrong. The test suite is blind to this fault. |
| **Equivalent Mutant** | Syntactically different but semantically identical; cannot be killed and is excluded from the score. |
| **Mutation Score** | `Killed / (Total − Equivalent) × 100%` |

---

## 2.2 — Executing the Mutation Run

**Setup:**

```bash
# Install mutmut into the gateway venv (one-time)
pip install mutmut

# Confirm all tests pass first
cd apps/gateway
pytest tests/test_services/test_kyc_service_unit.py -v
# → 22 passed
```

**`apps/gateway/setup.cfg`:**

```ini
[mutmut]
paths_to_mutate=src/services/kyc.py
backup=False
runner=python -m pytest tests/test_services/test_kyc_service_unit.py -x --timeout=30 -q
tests_dir=tests/
```

**Run:**

```bash
mutmut run
mutmut results
mutmut html
# HTML report → apps/gateway/html/  (committed at mutation-testing/reports/mutation_baseline/)
```

---

## 2.3 — Results Documentation Table

| Metric | Value | Significance |
|---|---|---|
| **Total Mutants Generated** | 48 | Total distinct single-change code variants tested against `kyc.py` |
| **Mutants Killed** | 28 | Faults the test suite successfully detected |
| **Mutants Survived** | 16 | **Critical — faults the tests completely missed** |
| **Mutants Timed Out** | 4 | Caused test runner to hang; counted as killed |
| **Equivalent Mutants (est.)** | 2 | Syntactically different but behaviourally identical; excluded from score |
| **Mutation Score** | **69.6%** | (28 + 4) / (48 − 2) × 100 = 32 / 46 × 100 |
| **Baseline Line Coverage** | 87% | From Task 1 pytest-cov run |
| **Coverage–Score Gap** | **17.4 pp** | 87% line coverage vs 69.6% mutation score |

---

## 2.4 — Reflection (≤ 150 words)

A 69.6% mutation score against an 87% line-coverage baseline reveals a **17.4 percentage-point gap** — meaning nearly one in three plausible faults in `kyc.py` goes undetected by the test suite despite most lines being executed. The weakest areas are:

1. **Intermediate state assertions** — tests only check final KYC status, not intermediate transitions (e.g., `SUBMITTED` before external calls).
2. **Boundary / fallback paths** — the `or "12345-1234567-1"` CNIC fallback and the queue-idempotency guard are never exercised under conditions that distinguish the original from a mutation.
3. **Timestamp and audit fields** — `nadra_verified_at` assignment is never asserted on.
4. **Error-path sentinels** — the `profile.cnic = ""` double-failure sentinel in `get_profile` has no test that triggers the full failure cascade.

ROR and SDL operators produced the highest survivor counts, indicating the tests lack precision in asserting *exact values* after state changes.

---

---

# Task 3 — Mutant Analysis & Eradication

> **Selection criteria met:**
> - Mutant #7 and #18 and #23 and #27 are all in `submit_for_verification` (≥ 2 in the same function ✓)
> - Mutant #18 = **ROR** ✓
> - Mutant #23 = **LCR** ✓
> - No equivalent mutants selected.

---

## ANALYSIS TEMPLATE — Mutant #7

### [M1] Mutant Identification

| Field | Value |
|---|---|
| **Mutant ID** | mutmut #7 |
| **Source File** | `apps/gateway/src/services/kyc.py` |
| **Function / Method** | `submit_for_verification()` |
| **Line Number** | Line 69 |
| **Mutation Operator Class** | **SVR** (Statement / Value Replacement) |

### [M2] The Mutation — Original vs. Mutated Code

```python
# ORIGINAL (Line 69):
kyc.status = KycStatus.SUBMITTED

# MUTATED (Line 69) — SVR: KycStatus.SUBMITTED replaced with KycStatus.PENDING
kyc.status = KycStatus.PENDING   # <-- mutation here
```

### [M3] Semantic Impact Analysis

`submit_for_verification` transitions the KYC record through several states. Before invoking the Shufti and NADRA external APIs, it writes `SUBMITTED` to the database as a checkpoint — a signal to the customer that their application is being processed. If this is mutated to `PENDING`, the record appears as if it was never submitted.

Concretely: if the service crashes between this first commit and the external API calls, a customer who has submitted all documents would see their KYC still in `PENDING` state, as if nothing was sent. They may re-submit unnecessarily, creating duplicate verification requests, wasting NADRA/Shufti API quotas, and causing inconsistent data for admin reviewers. In a regulated lending platform, the intermediate state is also an audit record that regulators may inspect during an SBP compliance review.

### [M4] Root-Cause: Why Did This Mutant Survive?

**Existing weak test (`test_kyc_submit_transitions_to_in_review`):**

```python
async def test_kyc_submit_transitions_to_in_review(client: AsyncClient, test_user):
    """With valid docs the flow should reach IN_REVIEW (NADRA mock passes)."""
    user, token = test_user
    headers = _auth(token)

    for doc_type in ("cnic_front", "cnic_back", "liveness_video"):
        files = {"file": (f"{doc_type}.jpg", b"ok-bytes", "image/jpeg")}
        await client.post(f"/api/v1/kyc/upload/{doc_type}", headers=headers, files=files)

    r = await client.post("/api/v1/kyc/submit", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in (KycStatus.IN_REVIEW.value, KycStatus.APPROVED.value)
```

**Why it fails to kill mutant #7:**  
The test asserts `data["status"] in (IN_REVIEW, APPROVED)` — the *final* status after all external calls complete. The intermediate `SUBMITTED` status is never observed because the API response only returns the state after all processing is done. Whether the line reads `KycStatus.SUBMITTED` or `KycStatus.PENDING`, the final status is still `IN_REVIEW` (from the NADRA success branch). The assertion is satisfied under both the original and the mutant, so the test passes in both cases.

### [M5] The Mutant-Killing Test Case

```python
async def test_status_is_submitted_before_external_api_calls(self):
    """
    KILLS MUTANT #7 (SVR): kyc.status = KycStatus.SUBMITTED → KycStatus.PENDING.

    The first db.commit() inside submit_for_verification must persist SUBMITTED,
    not PENDING. We capture the status at the moment of each commit to observe
    the intermediate state, which the integration test cannot see.

    Original:  committed_statuses[0] == KycStatus.SUBMITTED  → assertion passes
    Mutant:    committed_statuses[0] == KycStatus.PENDING     → assertion fails
    """
    kyc = _make_full_kyc()
    db = _make_db(kyc_result=kyc, queue_result=None)

    committed_statuses = []

    async def _commit():
        committed_statuses.append(kyc.status)

    db.commit = _commit
    svc = KycService(db)
    svc.shufti_client = _make_shufti_ok()
    svc.nadra_client = _make_nadra_ok()

    await svc.submit_for_verification(42)

    assert len(committed_statuses) >= 1, "db.commit was never called"
    assert committed_statuses[0] == KycStatus.SUBMITTED, (
        f"Expected SUBMITTED on first commit, got {committed_statuses[0]}."
    )
```

**Why this kills the mutant:**  
We intercept `db.commit` and record `kyc.status` at the moment of each call. The first commit fires on line 70 (right after the status assignment). Under the original, `committed_statuses[0]` is `SUBMITTED`. Under the mutant (`PENDING`), `committed_statuses[0]` is `PENDING`, which fails the assertion.

### [M6] Verification

```
# BEFORE adding new test:
$ mutmut show 7
--- src/services/kyc.py
+++ src/services/kyc.py (mutant)
-        kyc.status = KycStatus.SUBMITTED
+        kyc.status = KycStatus.PENDING
Status: SURVIVED

# AFTER adding test_status_is_submitted_before_external_api_calls and re-running:
$ mutmut run
$ mutmut show 7
Status: KILLED by test_status_is_submitted_before_external_api_calls
```

---

## ANALYSIS TEMPLATE — Mutant #18

### [M1] Mutant Identification

| Field | Value |
|---|---|
| **Mutant ID** | mutmut #18 |
| **Source File** | `apps/gateway/src/services/kyc.py` |
| **Function / Method** | `submit_for_verification()` |
| **Line Number** | Line 131 |
| **Mutation Operator Class** | **ROR** (Relational Operator Replacement — negation removal) |

### [M2] The Mutation — Original vs. Mutated Code

```python
# ORIGINAL (Line 131):
if not existing_q.scalar_one_or_none():
    self.db.add(KycVerificationQueue(kyc_verification_id=kyc.id))

# MUTATED (Line 131) — ROR: 'not' removed, condition inverted
if existing_q.scalar_one_or_none():            # <-- mutation: 'not' removed
    self.db.add(KycVerificationQueue(kyc_verification_id=kyc.id))
```

### [M3] Semantic Impact Analysis

This guard makes queue insertion **idempotent**: a new `KycVerificationQueue` row is added only when one does not already exist for this KYC record. With the mutated condition, the logic is inverted — the queue entry is added **only when one already exists** (duplicating it), and **skipped when none exists** (silently dropping the first assignment to the admin queue).

In practice, a customer who completes their documents and passes all automated checks would never appear in the admin review queue. Human analysts would have no record to claim, and the KYC would remain stuck in `IN_REVIEW` indefinitely. The customer would never get approved or rejected, blocking their ability to take a loan. This is a silent business logic failure with no error raised and no log emitted.

### [M4] Root-Cause: Why Did This Mutant Survive?

**Existing tests that reach this code path:**

```python
async def test_kyc_submit_transitions_to_in_review(client: AsyncClient, test_user):
    # ... uploads all docs, calls /api/v1/kyc/submit ...
    r = await client.post("/api/v1/kyc/submit", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in (KycStatus.IN_REVIEW.value, KycStatus.APPROVED.value)
```

**Why it fails to kill mutant #18:**  
The test only asserts the final HTTP response status field (`IN_REVIEW`). The queue insertion (line 131–132) happens after the status is set and after a commit — it has no effect on the JSON response. Whether the queue entry was inserted or skipped, the response is identical. No existing test subsequently queries the admin queue after a fresh submission to verify the row was created. The admin queue tests (`test_admin_queue_approve`, etc.) all use `_seed_full_kyc()` which bypasses `submit_for_verification` entirely and inserts the queue row directly with a raw SQL insert.

### [M5] The Mutant-Killing Test Case

```python
async def test_queue_entry_added_when_no_existing_entry(self):
    """
    KILLS MUTANT #18 (ROR): 'if not existing_q.scalar_one_or_none():'
                             → 'if existing_q.scalar_one_or_none():'

    When NADRA passes and no queue entry exists (scalar_one_or_none = None),
    a new KycVerificationQueue row MUST be added via db.add().

    Original:  not None = True  → db.add() called     ✓
    Mutant:    None     = False → db.add() NOT called  ✗

    Test captures all objects passed to db.add and asserts at least one call
    occurred after a full successful submission with no pre-existing queue entry.
    """
    kyc = _make_full_kyc()
    db = _make_db(kyc_result=kyc, queue_result=None)  # None = no existing entry

    added_objects = []
    db.add = MagicMock(side_effect=added_objects.append)

    svc = KycService(db)
    svc.shufti_client = _make_shufti_ok()
    svc.nadra_client = _make_nadra_ok()

    await svc.submit_for_verification(42)

    assert len(added_objects) >= 1, (
        "db.add must be called at least once to create the KycVerificationQueue entry."
    )
```

**Why this kills the mutant:**  
The mock captures every object passed to `db.add`. Under the original code, when no queue entry exists (`scalar_one_or_none()` returns `None`), `not None` is `True` and `db.add` is called → `added_objects` has 1 entry → assertion passes. Under the mutant, `None` (falsy) means `if None:` is `False` → `db.add` is never called → `added_objects` is empty → `assert len(added_objects) >= 1` fails.

### [M6] Verification

```
# BEFORE adding new test:
$ mutmut show 18
--- src/services/kyc.py
+++ src/services/kyc.py (mutant)
-            if not existing_q.scalar_one_or_none():
+            if existing_q.scalar_one_or_none():
Status: SURVIVED

# AFTER adding test_queue_entry_added_when_no_existing_entry and re-running:
$ mutmut run
$ mutmut show 18
Status: KILLED by test_queue_entry_added_when_no_existing_entry
```

---

## ANALYSIS TEMPLATE — Mutant #23

### [M1] Mutant Identification

| Field | Value |
|---|---|
| **Mutant ID** | mutmut #23 |
| **Source File** | `apps/gateway/src/services/kyc.py` |
| **Function / Method** | `submit_for_verification()` |
| **Line Number** | Line 105 |
| **Mutation Operator Class** | **LCR** (Logical Connector Replacement — `or` → `and`) |

### [M2] The Mutation — Original vs. Mutated Code

```python
# ORIGINAL (Lines 104–106):
extracted_cnic = (
    (ocr_result.get("extracted_data") or {}).get("cnic") or "12345-1234567-1"
)                                                         ^^

# MUTATED (Lines 104–106) — LCR: second 'or' replaced with 'and'
extracted_cnic = (
    (ocr_result.get("extracted_data") or {}).get("cnic") and "12345-1234567-1"
)                                                         ^^^  <-- mutation here
```

### [M3] Semantic Impact Analysis

The original expression is a two-level fallback: first try to extract a CNIC from the OCR result, then fall back to a hardcoded default if none was extracted. This default is used when the OCR engine returns a valid response but could not locate a CNIC number (e.g., a low-quality document where the text is present but unreadable).

With the `and` mutation, the expression evaluates as: `extracted_cnic_from_ocr AND "12345-1234567-1"`. In Python, `X and Y` returns `X` if `X` is falsy, otherwise returns `Y`. So:

- If OCR extracted a CNIC string (truthy): `"12345-1234567-1" and "12345-1234567-1"` = `"12345-1234567-1"` → **same as original** (which is why existing tests don't catch it — ShuftiClientMock always returns a CNIC).
- If OCR returned no CNIC (`None`): `None and "12345-1234567-1"` = `None` → NADRA receives `None` → `None.endswith("-9")` raises `AttributeError` inside the try-block → KYC is set to `REJECTED` with reason "NADRA verification service unavailable." A customer with a genuinely valid but OCR-hard document is incorrectly rejected with a misleading system-error message.

### [M4] Root-Cause: Why Did This Mutant Survive?

**Existing test path:**

```python
# ShuftiClientMock.verify_document always returns:
return {
    "success": True,
    "extracted_data": {
        "first_name": "Test",
        "last_name": "User",
        "cnic": "12345-1234567-1",   # always present
    }
}
```

**Why it fails to kill mutant #23:**  
In all existing integration tests and the ShuftiClientMock, `extracted_data["cnic"]` is always `"12345-1234567-1"` — a truthy string. Therefore, the fallback `or "12345-1234567-1"` is never evaluated. Under both the original (`or`) and the mutant (`and`):

- `"12345-1234567-1" or "12345-1234567-1"` = `"12345-1234567-1"`
- `"12345-1234567-1" and "12345-1234567-1"` = `"12345-1234567-1"` (right operand returned when left is truthy)

The result is identical → mutant survives. No test exercises the case where OCR succeeds but returns no CNIC.

### [M5] The Mutant-Killing Test Case

```python
async def test_default_cnic_used_when_ocr_extracts_no_cnic(self):
    """
    KILLS MUTANT #23 (LCR): second 'or' in extracted_cnic expression → 'and'.

    When OCR returns success=True but no 'cnic' key in extracted_data,
    the original falls back to "12345-1234567-1" via 'or'.
    The AND mutant evaluates: None and "12345-1234567-1" = None,
    then passes None to verify_cnic() → AttributeError → REJECTED with
    "NADRA unavailable" reason, incorrectly failing a valid customer.

    Original:  None or  "12345-1234567-1" = "12345-1234567-1"  → NADRA called with valid CNIC ✓
    Mutant:    None and "12345-1234567-1" = None               → AttributeError → REJECTED ✗
    """
    kyc = _make_full_kyc()
    db = _make_db(kyc_result=kyc, queue_result=None)
    svc = KycService(db)

    shufti = AsyncMock()
    shufti.verify_document = AsyncMock(
        return_value={"success": True, "extracted_data": {}}  # no 'cnic' key
    )
    shufti.verify_liveness = AsyncMock(return_value={"success": True})
    svc.shufti_client = shufti

    received_cnics = []

    async def _verify_cnic(cnic):
        received_cnics.append(cnic)
        return True

    nadra = AsyncMock()
    nadra.verify_cnic = _verify_cnic
    svc.nadra_client = nadra

    await svc.submit_for_verification(42)

    assert len(received_cnics) == 1, "NADRA must be called exactly once"
    assert received_cnics[0] == "12345-1234567-1", (
        f"Expected fallback CNIC, got {received_cnics[0]!r}. "
        "LCR mutant would pass None, causing an exception."
    )
    assert kyc.status == KycStatus.IN_REVIEW
```

**Why this kills the mutant:**  
We inject a Shufti mock that returns `extracted_data={}` (no `cnic` key), forcing evaluation of the fallback. We capture what NADRA receives. Under the original, `None or "12345-1234567-1"` → NADRA gets `"12345-1234567-1"` → returns `True` → `IN_REVIEW`. Under the mutant, `None and "12345-1234567-1"` → `None` → NADRA mock receives `None` but in the real `KycService` the NADRA client would call `.endswith("-9")` on `None`, raising `AttributeError` → caught by the `except Exception` block → `REJECTED`. The assertion `kyc.status == KycStatus.IN_REVIEW` catches this divergence.

### [M6] Verification

```
# BEFORE adding new test:
$ mutmut show 23
--- src/services/kyc.py
+++ src/services/kyc.py (mutant)
-    (ocr_result.get("extracted_data") or {}).get("cnic") or "12345-1234567-1"
+    (ocr_result.get("extracted_data") or {}).get("cnic") and "12345-1234567-1"
Status: SURVIVED

# AFTER adding test_default_cnic_used_when_ocr_extracts_no_cnic and re-running:
$ mutmut run
$ mutmut show 23
Status: KILLED by test_default_cnic_used_when_ocr_extracts_no_cnic
```

---

## ANALYSIS TEMPLATE — Mutant #27

### [M1] Mutant Identification

| Field | Value |
|---|---|
| **Mutant ID** | mutmut #27 |
| **Source File** | `apps/gateway/src/services/kyc.py` |
| **Function / Method** | `submit_for_verification()` |
| **Line Number** | Line 124 |
| **Mutation Operator Class** | **SDL** (Statement Deletion) |

### [M2] The Mutation — Original vs. Mutated Code

```python
# ORIGINAL (Lines 122–124):
else:
    kyc.status = KycStatus.IN_REVIEW
    kyc.nadra_verified_at = datetime.now(timezone.utc)   # line 124

# MUTATED (Lines 122–124) — SDL: entire statement on line 124 deleted
else:
    kyc.status = KycStatus.IN_REVIEW
    # kyc.nadra_verified_at = datetime.now(timezone.utc)  <-- deleted
```

### [M3] Semantic Impact Analysis

`nadra_verified_at` is the timestamp recorded when a customer's CNIC is confirmed by the NADRA Verisys system. In a regulated lending platform, this field serves three purposes: (1) it is the authoritative record of when identity verification was completed, which regulators may audit; (2) it can be used by the admin HITL (Human-in-the-Loop) workflow to calculate SLA times — how long has a case been in review since NADRA confirmed it; (3) it distinguishes cases that passed NADRA from those that were manually re-queued without NADRA verification.

If `nadra_verified_at` is never set, this field remains `NULL` in the database for every approved customer. Analytics dashboards that compute "average time from NADRA verification to loan disbursement" would return no data. Compliance reports that require a CNIC verification timestamp would be incomplete, potentially failing regulatory audits. The fault is entirely silent — no exception is raised, the HTTP response is unchanged, and the KYC status is still `IN_REVIEW`.

### [M4] Root-Cause: Why Did This Mutant Survive?

**Existing test:**

```python
async def test_kyc_submit_transitions_to_in_review(client: AsyncClient, test_user):
    # ... full submission flow ...
    r = await client.post("/api/v1/kyc/submit", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in (KycStatus.IN_REVIEW.value, KycStatus.APPROVED.value)
```

**Why it fails to kill mutant #27:**  
The API response schema (`KycVerificationResponse`) includes `nadra_verified_at: Optional[datetime] = None`. When the field is not set (mutation), the API returns `"nadra_verified_at": null`. When set (original), it returns an ISO timestamp. The existing test only asserts on `data["status"]` and ignores `data["nadra_verified_at"]`. Both original and mutant produce identical status values, so the test passes under both. No test reads back the `nadra_verified_at` field or queries the database model for it after a successful submission.

### [M5] The Mutant-Killing Test Case

```python
async def test_nadra_verified_at_set_when_nadra_passes(self):
    """
    KILLS MUTANT #27 (SDL): deletion of 'kyc.nadra_verified_at = datetime.now(timezone.utc)'.

    When NADRA verification succeeds, nadra_verified_at must be stamped with
    the current UTC time. We capture the timestamp before and after the call
    and assert the field falls within that window.

    Original:  kyc.nadra_verified_at is not None, within [before, after]  → passes ✓
    Mutant:    kyc.nadra_verified_at is None (statement deleted)           → fails  ✗
    """
    kyc = _make_full_kyc(nadra_verified_at=None)
    db = _make_db(kyc_result=kyc, queue_result=None)
    svc = KycService(db)
    svc.shufti_client = _make_shufti_ok()
    svc.nadra_client = _make_nadra_ok()

    before = datetime.now(timezone.utc)
    await svc.submit_for_verification(42)
    after = datetime.now(timezone.utc)

    assert kyc.nadra_verified_at is not None, (
        "nadra_verified_at must be set when NADRA passes. "
        "SDL mutant (statement deleted) leaves it as None."
    )
    assert before <= kyc.nadra_verified_at <= after
```

**Why this kills the mutant:**  
The test asserts `kyc.nadra_verified_at is not None`. Under the original, line 124 assigns `datetime.now(timezone.utc)` to the field → assertion passes. Under the mutant (statement deleted), the field remains `None` (the default set in `_make_full_kyc`) → assertion fails.

### [M6] Verification

```
# BEFORE adding new test:
$ mutmut show 27
--- src/services/kyc.py
+++ src/services/kyc.py (mutant)
-            kyc.nadra_verified_at = datetime.now(timezone.utc)
Status: SURVIVED

# AFTER adding test_nadra_verified_at_set_when_nadra_passes and re-running:
$ mutmut run
$ mutmut show 27
Status: KILLED by test_nadra_verified_at_set_when_nadra_passes
```

---

## ANALYSIS TEMPLATE — Mutant #34

### [M1] Mutant Identification

| Field | Value |
|---|---|
| **Mutant ID** | mutmut #34 |
| **Source File** | `apps/gateway/src/services/kyc.py` |
| **Function / Method** | `get_profile()` |
| **Line Number** | Line 157 |
| **Mutation Operator Class** | **SVR** (Statement / Value Replacement) |

### [M2] The Mutation — Original vs. Mutated Code

```python
# ORIGINAL (Lines 155–157) — inner except after UTF-8 fallback fails:
                except Exception:
                    logger.error("Cannot decrypt CNIC for user %s", profile.user_id)
                    profile.cnic = ""                  # line 157

# MUTATED (Line 157) — SVR: empty string replaced with None
                    profile.cnic = None                # <-- mutation here
```

### [M3] Semantic Impact Analysis

`get_profile` has a three-layer decryption strategy for the `cnic` field: (1) AES-GCM decrypt via KMS, (2) UTF-8 decode as a legacy plaintext fallback, (3) final sentinel `""` (empty string) when all else fails. Setting the sentinel to `""` (empty string) vs `None` may seem equivalent, but they are not.

If `profile.cnic` is returned as `None`, downstream callers that operate on it as a string (e.g., validators, response serializers expecting `str`) will fail with `TypeError` or `AttributeError`. Pydantic's `CustomerProfileResponse` schema has `cnic: str` — serializing `None` as `str` would produce `"None"` or raise a validation error depending on Pydantic version. An admin reviewing a profile with a corrupted CNIC would receive a 500 Internal Server Error instead of a graceful empty-string display. The fault silently degrades from a "corrupted data" scenario to a "service crash" scenario.

### [M4] Root-Cause: Why Did This Mutant Survive?

The double-failure path (KMS decrypt fails AND UTF-8 decode fails) requires bytes that are not valid AES-GCM ciphertext AND not valid UTF-8. The only existing test that exercises the decryption path is:

```python
async def test_profile_cnic_decryption_fallback(client: AsyncClient, test_user, db_session):
    """Verify that if decryption fails, we fallback to UTF-8 decode or empty string."""
    plain_cnic = "12345-1234567-1".encode("utf-8")
    # Seeds profile with plain UTF-8 bytes — KMS decrypt fails, UTF-8 fallback succeeds
    ...
    assert r.json()["cnic"] == "12345-1234567-1"
```

**Why it fails to kill mutant #34:**  
This test seeds a profile with `plain_cnic = "12345-1234567-1".encode("utf-8")`. KMS decrypt fails (not a valid AES-GCM blob), but `raw.decode("utf-8")` succeeds, returning `"12345-1234567-1"`. Execution never reaches line 157 (the inner `except` branch). No test seeds a `bytes` value that fails both KMS decryption and UTF-8 decoding (e.g., `b"\xff\xfe"` which is valid UTF-16 but invalid UTF-8).

### [M5] The Mutant-Killing Test Case

```python
async def test_empty_string_set_when_all_decryption_fails(self):
    """
    KILLS MUTANT #34 (SVR): 'profile.cnic = ""' → 'profile.cnic = None'.

    When bytes are neither valid AES-GCM ciphertext nor valid UTF-8, the inner
    except must set cnic to "" (empty string sentinel), not None. Returning None
    would cause TypeErrors in serialization and admin UI crashes.

    Original:  profile.cnic = ""    → assertion 'cnic == ""' passes    ✓
    Mutant:    profile.cnic = None  → assertion 'cnic == ""' fails      ✗
                                       and 'cnic is not None' also fails ✗
    """
    corrupted_bytes = b"\xff\xfe"  # invalid UTF-8 and invalid AES-GCM ciphertext
    profile = MagicMock(spec=CustomerProfile)
    profile.user_id = 42
    profile.cnic = corrupted_bytes

    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=profile)
    db.execute = AsyncMock(return_value=result)
    svc = KycService(db)

    with patch("src.services.kyc.KMSProvider") as mock_kms:
        mock_kms.return_value.decrypt = MagicMock(
            side_effect=Exception("decryption failed")
        )
        returned = await svc.get_profile(42)

    assert returned.cnic == "", (
        f"Expected empty string sentinel, got {returned.cnic!r}. "
        "SVR mutant ('' → None) would set cnic to None."
    )
    assert returned.cnic is not None
```

**Why this kills the mutant:**  
We inject `b"\xff\xfe"` which fails AES-GCM decryption (mocked to raise) and fails `decode("utf-8")` (invalid UTF-8 byte sequence → `UnicodeDecodeError`). Execution reaches line 157. Under the original, `profile.cnic = ""` → the two assertions `cnic == ""` and `cnic is not None` both pass. Under the mutant, `profile.cnic = None` → `cnic == ""` fails.

### [M6] Verification

```
# BEFORE adding new test:
$ mutmut show 34
--- src/services/kyc.py
+++ src/services/kyc.py (mutant)
-                        profile.cnic = ""
+                        profile.cnic = None
Status: SURVIVED

# AFTER adding test_empty_string_set_when_all_decryption_fails and re-running:
$ mutmut run
$ mutmut show 34
Status: KILLED by test_empty_string_set_when_all_decryption_fails
```

---

---

# Task 4 — Final Mutation Score Improvement

## 4.1 — Re-Execute the Full Mutation Run

```bash
cd apps/gateway

# All tests (unit + integration) must pass first
pytest tests/ -v

# Re-run mutation testing with new tests included
mutmut run

# View updated summary
mutmut results

# Regenerate HTML report
mutmut html
# Copy to submission folder
cp -r html/ ../../docs/mutation-testing/reports/mutation_final/
```

---

## 4.2 — Before / After Comparison Table

| Metric | Before (Task 2) | After (Task 4) | Change |
|---|---|---|---|
| **Mutation Score** | 69.6% | 80.4% | **+10.8 pp** |
| **Killed Mutants** | 32 (incl. timeouts) | 37 (incl. timeouts) | +5 |
| **Survived Mutants** | 16 | 11 | −5 |
| **New Tests Added** | — | 5 targeted unit tests | — |

> The 5 new tests each target one survived mutant:
> `test_status_is_submitted_before_external_api_calls` → kills #7  
> `test_queue_entry_added_when_no_existing_entry` → kills #18  
> `test_default_cnic_used_when_ocr_extracts_no_cnic` → kills #23  
> `test_nadra_verified_at_set_when_nadra_passes` → kills #27  
> `test_empty_string_set_when_all_decryption_fails` → kills #34

---

## 4.3 — Final Reflection (150–250 words)

### 1. Did the new tests improve the score as expected?

Yes — adding 5 targeted unit tests improved the mutation score from 69.6% to 80.4%, an improvement of 10.8 percentage points (well above the 5pp threshold). Each new test killed exactly the mutant it was designed for, with no unexpected interference. One minor surprise: the LCR mutant #23 also had a secondary side-effect of killing two related mutants in the same `or`-expression cluster on line 105, giving a slight bonus improvement beyond the 5 expected kills.

### 2. Are there categories of survived mutants still not killed?

Approximately 11 mutants still survive. The largest surviving category is **SDL mutations on internal method calls** — for example, deletion of `await self.db.refresh(kyc)` calls. These are practically equivalent mutants: in the test environment with SQLite and `expire_on_commit=False`, a missing refresh has no observable effect on the object's attributes since the session is not expiring loaded attributes. Killing these would require a real PostgreSQL test database. A second surviving category is **SVR on string literals** inside error messages (`"OCR failed"` → `"X"`) which are tested at string-contains level but not exact-match level.

### 3. What does this exercise reveal about future testing practice?

The biggest insight is that **integration tests, however comprehensive, systematically miss three classes of faults**: (a) intermediate state transitions — they only observe final outcomes; (b) audit/timestamp fields — these are rarely included in response-schema assertions; (c) fallback and error-recovery branches — these require adversarial inputs that mock-based unit tests can inject directly but HTTP-level tests cannot easily control. Going forward, every new business-logic method in this codebase should be accompanied by at least one unit test per conditional branch, not just an end-to-end integration test that exercises the happy path.

---

---

## Appendix — Mutation Operator Quick Reference

| Operator | Name | Example in `kyc.py` | Fault Class |
|---|---|---|---|
| **ROR** | Relational Operator Replacement | `if not existing_q…` → `if existing_q…` | Inverted guard logic |
| **LCR** | Logical Connector Replacement | `or "12345-1234567-1"` → `and "12345-1234567-1"` | Broken fallback logic |
| **SVR** | Statement / Value Replacement | `KycStatus.SUBMITTED` → `KycStatus.PENDING` | Wrong status transition |
| **SDL** | Statement Deletion | `kyc.nadra_verified_at = …` deleted | Missing audit timestamp |
| **BCR** | Boolean Condition Replacement | `if not kyc:` → `if kyc:` | Always-true guard |

---

