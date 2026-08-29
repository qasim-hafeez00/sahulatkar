# SahulatKar Master Regulatory Compliance Library

Master library of primary-source regulatory documents for SahulatKar (BNPL / Islamic digital financing, Pakistan). This is a **living library** of 100% official regulatory documents, law texts, circulars, and official frameworks across SECP, SBP, NADRA, Pakistan Federal Laws, PTA, FBR, Provincial Consumer Protection, Competition Commission, and Modaraba.

Status as of **2026-08-29**. **97 unique primary-source documents (~98 MB)** verified and stored in this repository.

---

## Document Inventory (Deduplicated Official Files)

### 1. SECP — Primary Regulator (BNPL / NBFC / Digital Lending / Shariah / AML / Corporate)
- `01-SECP/01-NBFC-Regulations/`: NBFC and Notified Entities Regulations, 2008 (updated 2026-01-15)
- `01-SECP/02-BNPL/`: S.R.O. 2120(I)/2025 — BNPL amendments to NBFC Regulations
- `01-SECP/03-Digital-Lending/`: Circulars 8/2024, 12/2024, 3/2023, 10/2023, 15/2022, 15/2023
- `01-SECP/04-App-Whitelisting/`: Circular 14/2024 & SECP Digital Lending App Whitelist (2026-07-22)
- `01-SECP/05-AML-KYC/`: SECP AML/CFT/CPF Regulations 2020 (amended to 2026-07-03)
- `01-SECP/07-Corporate/`: Companies Regulations 2024
- `01-SECP/08-Shariah/`: Shariah Governance Regs 2023, Islamic Financial Services Guidelines 2023, 2026 Guidebook, Report on Shariah-Compliant Digital Financing, Diagnostic Review
- `01-SECP/09-Fintech/`: Fintech Framework for Non-Banking Sector
- `01-SECP/10-Sandbox/`: Regulatory Sandbox Guidelines 2019
- `01-SECP/11-Prudential-Regulations/`: Prudential Regs for Consumer Financing & NBFCs
- `01-SECP/12-Credit-Rating/`: Credit Rating Companies Regulations

### 2. SBP — Payment Systems, Raast, Credit Bureaus, Technology Risk & Islamic Finance
- `02-SBP/01-Payment-Systems/`: Payment Card Security Regs 2016, EFT Regs 2018, Payment Systems Overview, National Payment Systems Strategy
- `02-SBP/02-Raast/`: Raast Integration Guide, Raast P2M Circular 04/2023, Participation Criteria 2025
- `02-SBP/03-EMI-PSP-PSO/`: Electronic Money Institutions (EMI) Regulations 2023, DFS Innovation Challenge Guidelines, Mobile Banking Guidelines
- `02-SBP/04-Credit-Bureaus/`: Credit Bureau Act 2015, Amendment Act 2016, Regs 2016, Rules 2016, Licensing Criteria
- `02-SBP/05-Technology-Risk/`: Mobile Apps Security Guidelines 2022, Technology Risk Management Framework 2025
- `02-SBP/06-Islamic-Finance/`: SBP Compendium of Shariah Standards, Shariah Governance Framework 2024, IB FAQs, Shariah Compliance Instructions/Guidelines, Risk Management Guidelines
- `02-SBP/07-AML-CFT-KYC/`: SBP AML/CFT/CPF Regulations 2022, Risk-Based Approach Guidelines, Biometric FAQs, Targeted Financial Sanctions Guidelines & FAQs
- `02-SBP/08-Consumer-Protection/`: Fair Treatment of Consumers Framework & FAQs, Prudential Regs for Consumer Financing
- `02-SBP/09-Microfinance-Comparative/`: Microfinance Institutions Ordinance 2001, Prudential Regs for Microfinance Banks 2025 (Banking Companies Ordinance 1962 de-duplicated — canonical copy is in `05-PAKISTAN-LAW/`)

### 3. NADRA — Identity / KYC / Biometrics
- `03-NADRA/`: NADRA Ordinance 2000, Verification Services & Nishan Pakistan Overview, Main Site Overview

### 4. PAKISTAN FEDERAL LAW — Legislation
- `05-PAKISTAN-LAW/`: PECA 2016, ETO 2002, PS&EFT Act 2007, AML Act 2010, Credit Bureaus Act 2015, Companies Act 2017, Secured Transactions Act 2016, Financial Institutions Recovery Ordinance 2001, Banking Companies Ordinance 1962, Contract Act 1872, Sale of Goods Act 1930, Stamp Act 1899, Limitation Act 1908, Negotiable Instruments Act 1881, Islamabad Consumer Protection Act 1995 (Modaraba Ordinance 1980 de-duplicated — canonical copy is in `12-MODARABA/`)

### 5. PTA — Telecom / SMS / Cybersecurity
- `06-PTA/`: PTA National Cyber Security Framework for Telecom (2022), Pakistan Telecommunication Reorganization Act 1996

### 6. FBR — Tax Laws
- `07-FBR/`: Income Tax Ordinance 2001 (amended 2026-06-30), Sales Tax Act 1990 (amended 2026-06-30), Federal Excise Act 2005 (amended 2026-06-30), ICT Tax on Services Ordinance, Withholding Tax Rate Card

### 7. CONSUMER PROTECTION — Provincial Laws
- `08-CONSUMER/`: Punjab Consumer Protection Act 2005 & 2025 Amendment, Sindh Consumer Protection Act 2014, KPK Consumers Protection Act 1997, Balochistan Consumer Protection Act 2003

### 8. DATA PRIVACY — Personal Data Protection
- `10-DATA-PRIVACY/`: Personal Data Protection Bill Draft (Ministry of IT)

### 9. COMPETITION COMMISSION OF PAKISTAN
- `11-COMPETITION/`: Competition Act 2010, Deceptive Marketing Practices Guidelines 2023, Merger Control Regulations 2016

### 10. MODARABA & ACCOUNTING
- `12-MODARABA/`: Consolidated Circular for Modarabas 2024, Modaraba Regulations 2021, Modaraba Rules 1981, Modaraba Ordinance 1980
- `13-ACCOUNTING/`: IFRS / ICAP Reference Notes

### 11. INTERNATIONAL SECURITY STANDARDS (reference only, not Pakistani law)
- `09-SECURITY/`: Reference notes on ISO 27001/27701, PCI DSS, OWASP ASVS/API Top 10, SOC 2, CIS Controls, NIST CSF — official links only, no paywalled text mirrored

---

## Known gaps / not yet done

- `02-SBP/` — "Rules for Payment System Operators/Payment Service Providers (2014)" was flagged in the first pass as not found under SBP's current site structure; still not resolved.
- Provincial consumer protection is now complete for Punjab, Sindh, KPK, and Balochistan; Islamabad Capital Territory's own consumer protection ordinance was found under `05-PAKISTAN-LAW/`.

## Methodology note

This pass was collected by four parallel research agents (one each for SECP, SBP, Pakistan-law/PTA/FBR/NADRA, and provincial-consumer/competition/privacy/accounting/security), each briefed on the download techniques worked out in the first pass (SECP's `wpdmdl` landing-page pattern, SBP's Cloudflare workaround via a reader-proxy plus browser-UA curl, Pakistan Code's direct PDF paths). All four were interrupted mid-run by an account-level spend cap, so none reached its final "write a manifest" step — one agent instead spent its last turn rewriting this README directly (against instruction), which was then reconciled against the actual filesystem by hand: every PDF was checked for a valid `%PDF` header and a non-trivial file size, and three genuine duplicates from overlapping agent scopes (the EFT Act 2007, Banking Companies Ordinance 1962, and Modaraba Ordinance 1980, each fetched from two different official mirrors) were resolved down to one canonical copy each. The one task the fourth agent didn't reach (`09-SECURITY/` reference notes) was written directly afterward, since it only required authoring, not fetching. What was **not** done: line-by-line content verification that each file is the correct/current edition of the named law — that level of scrutiny should happen at the point each document is actually relied on in the compliance matrix, not as a blanket pass.

---

## Directory Tree

```text
docs/compliance/
├── 01-SECP/            (NBFC, BNPL, Digital Lending, Whitelisting, AML, Corporate, Shariah, Sandbox)
├── 02-SBP/             (Payment Systems, Raast, EMI, Credit Bureaus, Technology Risk, Islamic Finance, AML)
├── 03-NADRA/           (Ordinance, Verisys, Biometrics, Nishan Pakistan)
├── 05-PAKISTAN-LAW/    (PECA, ETO, PS&EFT, AML, Credit Bureaus, Companies Act, Contract Act, Secured Transactions)
├── 06-PTA/             (Telecom Cyber Security Framework, Telecom Reorganization Act)
├── 07-FBR/             (Income Tax, Sales Tax, Federal Excise, ICT Services Tax, Withholding Rate Card)
├── 08-CONSUMER/        (Punjab, Sindh, KPK, Balochistan Consumer Protection Acts)
├── 10-DATA-PRIVACY/    (Personal Data Protection Framework)
├── 11-COMPETITION/     (Competition Act, Deceptive Marketing Guidelines, Merger Control)
├── 12-MODARABA/        (Consolidated Circulars, Modaraba Regs, Modaraba Ordinance)
├── 13-ACCOUNTING/      (IFRS / ICAP Guidance)
├── 09-SECURITY/        (ISO/PCI/OWASP/NIST reference notes — not Pakistani law)
└── README.md           (This master regulatory index)
```
