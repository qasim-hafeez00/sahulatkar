# IFRS / ICAP Accounting Reference Notes

**Purpose:** Quick-reference index of accounting standards relevant to SahulatKar's BNPL / Shariah-compliant receivables business. This document does **not** reproduce copyrighted standard text — IFRS Foundation and ICAP standards are licensed content. It points to the official sources to consult and explains *why* each standard matters to the business.

---

## 1. Most Relevant IFRS Standards

### IFRS 9 — Financial Instruments
**Why it matters:** SahulatKar originates consumer receivables (BNPL installment plans). IFRS 9 governs classification/measurement of these receivables and, critically, the **Expected Credit Loss (ECL)** impairment model — a forward-looking provisioning methodology (as opposed to the old "incurred loss" model). For a BNPL lender, ECL modeling directly drives:
- How loan-loss provisions are calculated and staged (Stage 1/2/3 buckets based on credit deterioration)
- Balance sheet provisioning for the credit-engine's risk output
- Disclosure requirements around credit risk concentration

This is the single most consequential standard for the credit-engine and ledger-service's accounting treatment of receivables.

### IFRS 15 — Revenue from Contracts with Customers
**Why it matters:** Governs recognition timing of BNPL merchant fees, late fees, and any profit/markup earned on installment plans. Under IFRS 15's five-step model, revenue (or profit, in a Shariah-compliant structure) must be recognized as performance obligations are satisfied — relevant to how SahulatKar times recognition of markup/fee income across the installment period rather than upfront.

### IFRS 16 — Leases
**Why it matters:** Only relevant **if** SahulatKar contemplates an Ijarah-style (lease-based) Islamic finance product. IFRS 16's lessee/lessor accounting model would need to be read alongside AAOIFI's Ijarah standard (FAS 32) to determine which framework governs recognition for that product line. Not currently applicable to a pure murabaha/BNPL installment model, but worth flagging if the product roadmap expands.

---

## 2. IFRS vs. AAOIFI — Which Applies?

Shariah-compliant entities operating in Pakistan frequently need to reference **both** frameworks:

- **IFRS**, as adopted and notified by the SECP, is the baseline financial reporting framework for companies in Pakistan.
- **AAOIFI Financial Accounting Standards (FAS)** — issued by the Accounting and Auditing Organization for Islamic Financial Institutions — provide Shariah-specific accounting treatments for Islamic contracts (Murabaha, Ijarah, Musharaka, Diminishing Musharaka, etc.) that IFRS does not directly address, since IFRS is contract-structure-agnostic and was not designed with Islamic finance instruments in mind.
- In practice, Pakistani Islamic financial institutions often apply IFRS as the general framework **and** layer AAOIFI FAS guidance for the Shariah-specific substance of individual product structures (e.g., how a Murabaha-based BNPL receivable's profit component should be presented/disclosed).

**ICAP (Institute of Chartered Accountants of Pakistan)** is the body that issues technical guidance on which framework/standard applies in a given fact pattern, including any SECP-notified exemptions or modifications for Islamic finance entities. Given SahulatKar's Shariah-compliant BNPL structure, this determination (IFRS-only vs. IFRS + AAOIFI FAS overlay) should be confirmed with ICAP or a qualified external auditor familiar with Islamic finance reporting — do not assume either framework alone is sufficient without professional confirmation.

---

## 3. Official Reference Links

| Body | Purpose | Link |
|---|---|---|
| IFRS Foundation | Official IFRS standards text, IASB updates | https://www.ifrs.org |
| ICAP | Pakistan's accounting standard-setting/professional body; guidance on IFRS adoption and AAOIFI applicability in Pakistan | https://icap.org.pk |
| AAOIFI | Islamic finance accounting, auditing, governance & Shariah standards (FAS series) | https://aaoifi.com |
| SECP | Notifies which IFRS standards are applicable in Pakistan and any modifications/exemptions | https://www.secp.gov.pk |

**Note on licensing:** Full standard text for IFRS and AAOIFI FAS is not freely redistributable — access requires a subscription/license via the links above, or through ICAP membership. This document is a navigational reference only; consult the primary sources (or a qualified accountant) before applying any specific standard to SahulatKar's financial statements.
