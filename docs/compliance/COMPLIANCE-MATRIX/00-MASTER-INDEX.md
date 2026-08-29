# SahulatKar Compliance Matrix — Master Index

Purpose: turn the 98-document regulatory library in `docs/compliance/` into an actionable requirement → business-rule → workflow mapping, so a lawyer/Shariah advisor/tax advisor reviewing this can confirm coverage rather than have to go find what's missing. Every matrix file follows the same chain from the original research brief:

**Regulation → Legal Requirement → Business Rule → Workflow → Backend Service → DB Field → API → Frontend Disclosure → Audit Evidence**

This is a documentation/design-layer artifact, not a code audit. It maps what each regulation requires SahulatKar to do; it does **not** claim the codebase already does it — that's a separate, later gap-analysis pass once this matrix is confirmed correct. Treat every row's "System/Workflow" column as the *intended* target, not a verified implementation.

## The one decision this whole matrix pivots on

SECP's digital-lending framework (Circular 8/12/14 of 2024, the App Whitelist) is written for **"NBFCs engaged in digital lending"** — the whitelist is explicitly titled "Digital Lending Apps being run and administered by duly licensed Lending NBFCs." There is no third path in SECP's current framework: a BNPL app must be operated either (a) by an entity that is itself a licensed lending NBFC, or (b) as a technology/service provider working under a licensed NBFC's license and name. This determines which rows below are "Applicable" vs "Applicable through partner, as a contract requirement" vs "Not Applicable."

**This matrix is built dual-track** — every applicability column below is tagged for both scenarios — specifically so it doesn't need to be redone once the decision is made:

- **Track A — SahulatKar is/becomes the licensed NBFC.** SahulatKar directly holds the SECP NBFC license, is directly subject to every SECP regulation, and integrates with SBP-regulated partners (bank/EMI/PSP) for money movement only.
- **Track B — SahulatKar operates as a technology provider under a partner's NBFC license.** The partner NBFC is the regulated entity of record; SahulatKar's compliance obligations mostly become **contractual pass-through requirements** it must design its system to satisfy on the partner's behalf (data handling, disclosure content, audit trail, Shariah structuring), while direct SECP licensing/reporting obligations sit with the partner.
- **Track C — Modaraba structure.** Only relevant if the funding/investment side of the business (as opposed to the lending/BNPL product side) is structured as a Modaraba — a distinct decision from A/B above, and the two aren't mutually exclusive (a Modaraba can be the funding vehicle behind either an NBFC or a partner-NBFC arrangement).

Recommendation: this is a corporate-structuring decision for SahulatKar's founders/board with the lawyer, not something to guess at in a document library. What the matrix does instead is make sure the analysis is ready the moment the decision is made.

## Matrix files — status as of 2026-08-29

All four files now contain real, verified content (clause-level citations, produced by direct document reads — not agent-reported summaries taken on trust). Roughly 350+ substantive matrix rows across the four files.

| File | Regulator(s) covered | Source documents | Depth |
|---|---|---|---|
| `01-SECP-matrix.md` | SECP NBFC/BNPL/Digital Lending core framework + Modaraba | `01-SECP/`, `12-MODARABA/` | **Deep**: NBFC Regulations 2008, all 5 Digital Lending circulars (03/2023, 08/2024, 12/2024, 14/2024 + whitelist), fully read with real clause citations. **Gaps flagged in-file**: SECP Shariah Governance/Guidebook cluster (highest priority — not yet read), AML/CFT Regs, Prudential Regs, Sandbox/Fintech/Credit-Rating/Companies-Regs (lighter priority), Modaraba cluster (conditional on Track C). |
| `02-SBP-matrix.md` | SBP Payment Systems/Raast/EMI-PSP-PSO/Credit Bureaus/Tech Risk/Islamic Finance/AML-CFT-KYC | `02-SBP/` | **Deep**: 247 table rows, the most thoroughly covered file. **Gap flagged in-file**: Consumer Protection (Fair Treatment framework) + Microfinance Comparative subfolders not yet read (agent cut off by rate limit). |
| `03-PAKISTAN-LAW-NADRA-PTA-matrix.md` | Federal law, NADRA, PTA | `05-PAKISTAN-LAW/`, `03-NADRA/`, `06-PTA/` | **Deep**: 12 of 14 Pakistan-law documents covered in detail (Contract Act, Sale of Goods Act, PECA, ETO, AML Act, EFT Act, Secured Transactions Act, Recovery Ordinance, Negotiable Instruments Act, Stamp Act, Limitation Act, Islamabad Consumer Act), plus NADRA and all 3 PTA documents. **Gap flagged in-file**: Companies Act 2017, Banking Companies Ordinance 1962. |
| `04-FBR-CONSUMER-COMPETITION-PRIVACY-matrix.md` | FBR, provincial consumer protection, Competition Commission, data privacy, accounting, security | `07-FBR/`, `08-CONSUMER/`, `10-DATA-PRIVACY/`, `11-COMPETITION/`, `13-ACCOUNTING/`, `09-SECURITY/` | **Solid**: real findings on the FBR tax-treatment question (concrete Sales Tax Act citations, not a placeholder), Punjab CPA + CCP Deceptive Marketing Guidelines read directly, Data Privacy draft bill's key provisions extracted. **Gaps flagged in-file**: CCP §8 (E-Commerce), comparative read of Sindh/KPK/Balochistan CPAs. |

## Two concrete open questions surfaced during this pass (worth resolving first, not generic placeholders)

1. **Does SECP's Nano-Lending-specific pricing cap (274% APR, aggregate cost ≤ principal) in Circular 12/2024 extend to BNPL specifically?** The circular states these numeric caps under the Digital Nano Lending subsection; BNPL is organized as a structurally distinct category in the same circular without its own explicitly-stated numeric cap in the sections reviewed. This determines the maximum lawful markup for SahulatKar's actual product — a lawyer with direct SECP contact could likely resolve this quickly. See `01-SECP-matrix.md`.
2. **Does SahulatKar's specific contract structure trigger hire-purchase sales-tax characterization?** Sales Tax Act 1990 s.2(33) explicitly includes hire-purchase in the "supply" definition, and s.2(44)(b) makes sales tax due at contract signing (not spread over installments) for such supplies — a real cash-flow question, not just a compliance checkbox, that depends on exactly who is "seller of record" in the final structure. See `04-FBR-CONSUMER-COMPETITION-PRIVACY-matrix.md`.

## Status legend used throughout

- **Applicable** — binds SahulatKar directly regardless of A/B/C track
- **Applicable (Track A only)** — only if SahulatKar itself becomes the licensed NBFC
- **Applicable (Track B — contract pass-through)** — becomes a requirement SahulatKar's contract with the partner NBFC must impose on itself/be imposed by
- **Applicable (Track C only)** — only if a Modaraba funding structure is adopted
- **Needs professional review** — genuinely unresolved by document research alone (tax treatment, Shariah product structuring specifics) — flagged, not guessed at
- **Not Applicable** — reviewed and excluded, with the reason stated

## Known open items going into the matrix (carried over, not yet resolved)

1. **FBR / Islamic finance tax neutrality** — could not confirm via public search whether Pakistan has SRO-level sales-tax/stamp-duty relief for NBFC-originated (as opposed to bank-originated) Murabaha/Ijarah-style transactions, where the underlying "sale" could otherwise trigger different tax treatment than a conventional loan. This is flagged as **Needs professional review (tax advisor)** everywhere it's relevant — not resolved by more searching.
2. **AAOIFI full standard texts** — SBP's Compendium (adopted-standards summary) is in the library; the full AAOIFI standard texts are paywalled and were deliberately not mirrored. Any matrix row needing clause-level AAOIFI detail beyond SBP's summary is flagged **Needs professional review (Shariah advisor with AAOIFI access)**.
3. **Document currency** — this library was built by finding each document's current official URL as of 2026-08-29, but SECP/SBP publish amendments on a rolling basis. Before this matrix is treated as final, re-check each "Applicable" row's source document against the regulator's live circulars page for anything more recent.
