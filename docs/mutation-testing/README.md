# Mutation Testing — Gateway KYC Service
## CS-4006 Software Testing · Spring 2025

**Target module:** `apps/gateway/src/services/kyc.py`  
**Tool:** `mutmut` + `pytest-cov`  
**Branch:** `mutation-testing-assignment`

---

## Prerequisites

```bash
# Activate the project virtual environment (from repo root)
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

# Install mutmut into the venv
pip install mutmut

# Verify
mutmut --version
pytest --version
```

---

## Step 1 — Run Baseline Coverage

```bash
cd apps/gateway

pytest tests/test_services/test_kyc_service_unit.py \
    --cov=src/services/kyc \
    --cov-report=term-missing \
    --cov-report=html:../../docs/mutation-testing/reports/baseline_coverage \
    -v
```

HTML report is written to `mutation-testing/reports/baseline_coverage/index.html`.

---

## Step 2 — Run Mutation Testing (Baseline — before new tests)

Run from `apps/gateway/`:

```bash
cd apps/gateway

# Confirm all tests pass before mutmut
pytest tests/test_services/test_kyc_service_unit.py -v

# Run mutation testing against kyc.py only
mutmut run

# View summary
mutmut results

# Inspect a specific survived mutant
mutmut show <mutant_id>

# Generate HTML report
mutmut html
# Report written to: apps/gateway/html/

# Copy to submission folder
cp -r html/ ../../docs/mutation-testing/reports/mutation_baseline/
```

---

## Step 3 — Run Final Mutation Testing (after new tests)

The new tests in `tests/test_services/test_kyc_service_unit.py` were written to
kill the survived mutants identified in Task 3.

```bash
cd apps/gateway

# Re-run with new tests included
mutmut run

mutmut results
mutmut html

cp -r html/ ../../docs/mutation-testing/reports/mutation_final/
```

---

## Folder Structure

```
mutation-testing/
├── README.md                          ← this file
├── report.md                          ← full assignment report (Tasks 1–4)
├── setup.cfg                          ← mutmut config reference (also in apps/gateway/)
├── reports/
│   ├── baseline_coverage/             ← HTML from pytest-cov (Task 1)
│   ├── mutation_baseline/             ← mutmut HTML before new tests (Task 2)
│   └── mutation_final/                ← mutmut HTML after new tests (Task 4)
└── tests/
    └── test_kyc_service_unit.py       ← reference copy of new unit tests
```

The authoritative copy of the unit tests lives at:
`apps/gateway/tests/test_services/test_kyc_service_unit.py`

---

## Mutmut Configuration

`apps/gateway/setup.cfg`:

```ini
[mutmut]
paths_to_mutate=src/services/kyc.py
backup=False
runner=python -m pytest tests/test_services/test_kyc_service_unit.py -x --timeout=30 -q
tests_dir=tests/
```

mutmut mutates only `src/services/kyc.py` and runs only the targeted unit tests
(not the full integration suite) for speed.
