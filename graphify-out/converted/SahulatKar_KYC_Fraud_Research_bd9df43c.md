<!-- converted from SahulatKar_KYC_Fraud_Research.docx -->


SahulatKar
Your Ethical Financial Partner


Comprehensive Research Report
KYC & Customer Onboarding, Fraud Mitigation,
Eligibility Criteria & Banking/Insurance Partnerships
for Pakistan's Vendor-Agnostic BNPL Platform

FYP Team | National University of Computer and Emerging Science, Chiniot
Qasim Hafeez (22F-3812)  |  Minha Ghulam (22F-3653)  |  Rayyan Akram (22F-3348)
Supervised by: Dr. Muhammad Usama  |  2026

# Executive Summary
This report provides a comprehensive research framework for implementing the Know Your Customer (KYC), customer onboarding, fraud mitigation, credit eligibility, and institutional partnership strategies for SahulatKar — Pakistan's first vendor-agnostic, Shariah-compliant Buy Now Pay Later (BNPL) platform.

Operating in a market where fewer than 2 million of 241 million citizens have formal credit access, SahulatKar must navigate a unique set of challenges: a predominantly unbanked/thin-file population, NADRA-centric identity infrastructure, SECP/SBP regulatory requirements, and Pakistan-specific fraud risks including cross-border abandonment and identity theft.

The research draws on global best practices from Zilch (UK), KalPay (Pakistan), Klarna (Sweden), Daira-ABHI partnership (Pakistan), and leading fraud mitigation literature to construct a practical, implementable blueprint tailored to the Pakistani e-commerce context.


# 1. Global BNPL KYC & Onboarding Landscape
## 1.1 Why KYC is Mission-Critical for BNPL
Unlike traditional banks that handle large, one-time loans, BNPL platforms process thousands of micro-transactions daily. Each transaction is a micro-lending event requiring a sub-second credit and identity decision. According to Veriff's 2026 Identity Fraud Report, over 4% of all verification attempts in 2025 were fraudulent, and AI-generated document fraud increased 300% year-on-year. Impersonation attacks account for over 85% of all fraudulent BNPL onboarding attempts.

KYC in BNPL serves three simultaneous goals:
- Regulatory Compliance: Satisfying SECP Circular No. 15 of 2022 and 2025 amendments, AML/CFT frameworks, and FATF guidelines.
- Risk Gating: Blocking fraudulent or high-risk applicants before they enter the credit pipeline.
- Commercial Enablement: Building a clean data set that improves credit scoring accuracy over time, reducing defaults and enabling higher credit limits for trusted users.

Deloitte reports that 38% of customers abandon onboarding if it feels too lengthy or invasive — meaning KYC design is also a UX and revenue problem, not merely a compliance exercise.

## 1.2 Global KYC Approaches in Leading BNPL Platforms

### Zilch (UK) — The OTT BNPL Leader
Zilch was the first UK BNPL provider to obtain a full FCA Consumer Credit Licence in April 2020, and is now one of the first to hold a full FCA Payments Licence (December 2025). Their KYC and underwriting approach has evolved into a sophisticated, multi-layered system:
- Open Banking Integration: Uses real-time bank account data (via Experian's Open Banking and TrueLayer) to assess consumer's cash flow — income regularity, expense volatility, existing BNPL repayments, overdraft frequency.
- Soft Credit Pulls: Performs a soft credit check via Experian and TransUnion without affecting the user's credit score, enabling instant approval.
- Machine Learning Credit Scoring: Zilch's "instant-approve" model uses ML to analyze both traditional bureau data and proprietary behavioral/transactional signals for real-time decisioning.
- Credit Bureau Reporting: Since 2023, Zilch reports repayment data to Experian and TransUnion reciprocally, rewarding good borrowers with improving credit scores — creating a virtuous loop for user retention.
- StepChange Integration: Embeds a debt charity service to identify financially vulnerable users and prevent over-indebtedness.

Zilch's dynamic risk scoring drove its default rate down from 3.1% (2022) to 2.3% (Q4 2025), and its 27% annual spend-per-customer growth demonstrates that good KYC enables commercial expansion rather than constraining it.

### KalPay (Pakistan) — Domestic BNPL Pioneer
KalPay is Pakistan's largest Shariah-aligned BNPL provider, launched in 2021 and focused on productive assets like smartphones. Their current onboarding model provides an important baseline for SahulatKar:
- Eligibility: All Pakistani nationals with a CNIC (Computerized National Identity Card), a smartphone, a verifiable phone number, and an email address.
- No Pre-registration Required: Users simply select KalPay at a merchant checkout and fill in CNIC and contact details on the spot.
- Manual Phone Verification: Before order confirmation, a KalPay representative calls the customer on a recorded line to verify order details. This manual step is then reviewed by the Risk & Compliance department.
- Credit Limit: Rs. 1,500 minimum, Rs. 15,000 maximum (with enhancement possible by request).
- Down Payment as Credit Filter: A mandatory 1/3 down payment (first installment) is required upfront, serving as the primary fraud filter.
- Payment Methods: Debit/credit card, Easypaisa, or JazzCash wallets, with auto-deduction enabled at the down payment stage.


### Klarna (Sweden/Global) — Hybrid Model
Klarna uses a layered KYC approach depending on transaction size:
- Micro-transactions (below threshold): Simplified KYC using email, phone, and soft pull only — instant approval.
- Larger transactions: Full document verification, credit bureau pull, and open banking connection required.
- One-Time Cards: For their "pay anywhere" virtual card, Klarna generates a temporary card but still ties it to the user's verified Klarna account — meaning KYC happens once at account creation.
- Ongoing monitoring: Transaction patterns trigger re-verification events (e.g., unusually large purchases, address changes, new high-risk merchant categories).

### Affirm (USA) — Risk-Tiered Underwriting
Affirm uses a risk-tiered model where KYC intensity scales with loan size:
- Pay-in-4 (under $1000): Soft pull + basic identity check. Instant decision.
- Monthly installments (over $1000): Hard credit pull, income verification, and enhanced due diligence.
- Alternative Data Integration: For thin-file applicants, Affirm uses educational history, employment type, purchasing patterns, and device signals as alternative credit signals.


# 2. SahulatKar KYC & Onboarding Framework
## 2.1 Information Collected at Onboarding
SahulatKar's onboarding must strike the balance between regulatory completeness (SECP Circular 15/2022 requirements) and UX speed (sub-5-minute target). The following data is collected in two tiers:

### Tier 1 — Mandatory (All Users)

### Tier 2 — Enhanced Due Diligence (High-Value Transactions / Elevated Risk Users)

## 2.2 Step-by-Step Onboarding Flow
The target end-to-end onboarding time is under 4 minutes for Tier 1 and under 10 minutes for Tier 2.

- User downloads SahulatKar app (Android/iOS) or visits web portal.
- Provides mobile number → receives OTP → OTP verified.
- Uploads CNIC (front and back) → OCR extracts Name, CNIC number, DOB, expiry.
- Real-time NADRA Verisys API call → confirms CNIC validity and active status.
- Selfie captured with liveness detection (anti-spoofing: blink, turn head) → AI face match against CNIC photo.
- Email address collected → verified via link or code; email age/domain check performed.
- Device fingerprint captured passively (OS, device model, installed apps hash, screen resolution, IP).
- User reviews and accepts Wakalah Agreement (Shariah Agency Agreement) and Terms of Service digitally.
- Automated risk score generated (see Section 4) → instant approve/decline/enhanced review decision.
- Credit limit assigned (starting conservative: Rs. 1,500 – Rs. 5,000 for new users).
- [If EDD triggered] → Bank account connection via JazzCash/Easypaisa API or open banking redirect.

## 2.3 NADRA Integration — The Identity Backbone
NADRA (National Database & Registration Authority) is the cornerstone of KYC in Pakistan, analogous to AADHAAR in India or SSN verification in the USA. Pakistan's digital identity infrastructure is built on NADRA rails:

- NADRA Verisys API: Real-time CNIC verification service that confirms name, DOB, gender, and CNIC status (valid/blocked/expired) against NADRA's national database. SahulatKar must integrate this as the primary identity check.
- CNIC Verification Providers: Third-party KYC vendors like Shufti Pro and uqudo offer Pakistan-specific APIs that combine CNIC document verification + facial liveness + NADRA database cross-reference in a single call.
- Digital Identity Initiative: NADRA has launched a new "Digital Identity" platform in 2025 providing verifiable digital credentials for citizens — SahulatKar should prepare to integrate with this as it matures.
- SIM Ownership Verification: PTA's mobile number ownership can be cross-referenced against CNIC via telecom APIs (Telenor, Jazz, Zong partnerships), adding a powerful secondary layer of identity confirmation.


## 2.4 Eligibility Criteria
Based on SECP regulatory requirements, KalPay's existing benchmark, and SahulatKar's vendor-agnostic risk profile, the following eligibility criteria are proposed:



# 3. Credit Scoring & Alternative Data for Thin-File Users
## 3.1 The Thin-File Problem in Pakistan
Pakistan's credit bureau coverage is extremely thin. SBP's eCIB (Electronic Credit Information Bureau) primarily covers borrowers above Rs. 500,000 — well above SahulatKar's typical transaction size. TASDEEQ, Pakistan's first SBP-licensed private credit bureau, collects data from financial institutions, utilities, telecoms, and insurance companies, offering better thin-file coverage, but adoption is still nascent.

Research from Synapse Analytics finds that in Pakistan, fewer than 2 million of 241 million citizens have formal credit access, meaning the vast majority of SahulatKar's target market will be "credit invisible" — they have no formal credit history. Traditional FICO-style scoring fails these users entirely.

## 3.2 Alternative Data Sources for Credit Scoring
The following alternative data sources are available and appropriate for the Pakistani market, ordered by data quality and regulatory permissibility:


## 3.3 Recommended Credit Scoring Architecture
### Primary Model: XGBoost Gradient Boosting (as per project spec)
XGBoost is the right choice for SahulatKar's credit scoring engine. Research shows gradient boosted trees achieve 93.7% accuracy in BNPL fraud/risk scoring. The model should be trained on:
- Target variable: Binary default/no-default at 90 days past due (DPD90).
- Features: 50-300 engineered features from the alternative data sources above.
- Training data: Initially synthetic/third-party data; rapidly replaced with own repayment data.
- Retraining: Monthly incremental retraining as repayment data accumulates.

### Secondary Model: Isolation Forest (Unsupervised Anomaly Detection)
Run in parallel for real-time fraud detection at the transaction level. Isolation Forest excels at detecting anomalous patterns not present in training data — critical for novel fraud vectors.

### Score Output

## 3.4 The First Payment Barrier — Critical Filter
Research from leading BNPL platforms consistently identifies the "First Payment Barrier" as the single most effective credit filter available. SahulatKar must implement:
- Mandatory down payment of 1/4 to 1/3 of total order value, collected via debit card, Easypaisa, or JazzCash before any purchase is executed.
- Rationale: If a user cannot fund the first installment, they are definitionally insolvent for this transaction. This filter eliminates the "never-pay" fraud category and reduces default rates significantly.
- Dynamic down payment: High-risk users (lower credit scores) pay a higher fraction (40%) while low-risk users pay less (25%).


# 4. Fraud Mitigation — Comprehensive Framework
## 4.1 BNPL-Specific Fraud Vectors
SahulatKar faces a unique combination of fraud vectors that differ from both traditional BNPL (merchant-integrated) and standard e-commerce fraud:


## 4.2 Technical Fraud Detection Layer
### A. Device Fingerprinting
At app install and every session, the system silently captures a device fingerprint — a unique, stable hash of:
- Device identifiers: IMEI hash, Android ID/iOS IDFA, model, OS version, firmware.
- Hardware signals: Screen resolution, processor type, battery status, available storage.
- Network signals: IP address, IP type (residential vs. datacenter vs. VPN), ISP, geolocation.
- Installed apps: Hash of financial app list (flags if no legitimate banking apps present, or presence of fraud-related tools).
- One device — one account policy: If the same device fingerprint is associated with multiple CNIC/accounts, flag for review immediately.

### B. Behavioral Biometrics (In-App)
Behavioral biometrics captures HOW the user interacts, not just WHO they are. During onboarding and every subsequent login/transaction:
- Typing cadence: Speed and rhythm of typing CNIC, address, etc. Copy-paste behavior (red flag for pre-generated synthetic data).
- Tap pressure and touch gestures: Mobile-specific signals indicating human vs. bot interaction.
- Session timing: Time of day, session duration. Applications submitted at 3 AM with sub-30-second completion are flagged.
- Form navigation: Does the user scroll to read the Wakalah agreement? Do they hesitate on financial fields? Humans behave differently from bots.
- Tool: Sardine.ai or BioCatch for behavioral biometric capture and scoring. Both are used by leading global BNPL platforms.

### C. Real-Time Transaction Scoring (Per-Order)
Every time a user submits a product URL for financing, a real-time transaction risk score is computed within 200ms:
- Order anomaly: Is this order significantly larger than the user's historical average? (e.g., 5x normal = flag)
- Merchant risk: Is the merchant URL newly registered (<6 months)? Does it have a low Moz/Ahrefs domain authority? No verifiable business registration?
- Product category risk: Is the product in a high-resale-value category (electronics, gold jewelry, luxury goods) with a high fraud correlation?
- Shipping address: Does the shipping address match the CNIC address? If going to an airport-adjacent location, flag. Is it a freight forwarder address?
- Purchase timing: Is this within 48 hours of a travel booking? (Open banking data could surface this)
- Velocity: Multiple orders in rapid succession from same device/IP/CNIC.

### D. MCC-Based Virtual Card Locking (Collusion Fraud Prevention)
SahulatKar's virtual cards (issued via Stripe Issuing sandbox, later Lithic or local bank partner) must be locked to the specific merchant URL/domain:
- Domain-locked cards: The virtual card generated for a Nike.com order can ONLY authorize at Nike.com. If the card details are leaked and someone tries to use them at a different merchant, the card is automatically declined.
- Amount-locked cards: Card loaded at exactly order_total + 5% buffer for tax/shipping. Cannot be over-spent.
- Time-limited cards: Card expires within 6 hours of issuance. Any failed order automatically invalidates the card.
- MCC Restrictions: Block Merchant Category Codes for cash advances, gambling, crypto, and high-risk categories entirely.

## 4.3 Pakistan-Specific Fraud Scenario: Cross-Border Abandonment
This is the most unique and critical fraud risk for SahulatKar. The scenario:


Countermeasures:

- Travel Signal Detection (Proactive): Monitor for signals of imminent travel — sudden address change, passport/travel document mentioned in app, open banking transactions at airport, NADRA NICOP application (overseas CNIC), or known seasonal migration patterns (e.g., March-April and September-October peak travel seasons from Pakistan).
- Credit Bureau Reporting (Deterrence): From day one, report all repayment behavior (positive and negative) to TASDEEQ and eCIB. Create the credible threat that default = damaged credit score, making future formal credit, phone contracts, and banking harder. The deterrent value alone reduces fraud.
- Emergency Contact / Guarantor: Require a Pakistan-resident guarantor's CNIC for credit limits above Rs. 10,000. The guarantor's credit record is also affected by default. This creates social accountability.
- Geolocation Monitoring: If the app's GPS data (collected with permission) shows the device is outside Pakistan, immediately trigger a payment freeze or demand full settlement within 14 days.
- Travel Profile Risk Score: Build a machine learning model that weights age (18-30 migration-prone), occupation (skilled worker), order category (items suitable for use abroad: phones, electronics), shipping address (near major airports: Karachi, Lahore, Islamabad).
- Progressive Credit Limits: Never extend a large credit limit on the first order. Start at Rs. 3,000 max and increase after 3 successful repayment cycles. By the time the user has a Rs. 15,000 limit, they have demonstrated sufficient commitment.
- Product Restrictions: Initially restrict high-resale electronics (flagship phones, laptops) and focus on lower-risk categories (household goods, clothing, books) until the user has a repayment track record.
- Legal Framework: Include in Terms of Service a clause that outstanding balances are recoverable in Pakistan courts and by authorized debt recovery agents. Partner with FIA for cases above Rs. 50,000 — credit fraud above this threshold is a criminal offense in Pakistan.

## 4.4 Algorithm Summary for Fraud Detection

## 4.5 Fraud Response Playbook
When fraud is detected or suspected, a tiered response is triggered:

- Level 1 — Soft Block: Order paused; additional verification requested (OTP re-send, face re-scan). User not notified that fraud was suspected. 80% of cases resolve here.
- Level 2 — Hard Block: Account frozen; outstanding amounts called immediately; Credit bureau notified. User notified of account suspension pending review.
- Level 3 — Legal Escalation: For losses above Rs. 25,000; FIA cybercrime complaint filed; NADRA notified for CNIC flagging; civil recovery proceedings initiated.
- Level 4 — Industry Sharing: Confirmed fraud profiles (device fingerprint, CNIC, phone number) shared with Pakistan Banks' Association (PBA) fraud ring for industry-wide blacklisting.


# 5. Banking & Insurance Partnerships
## 5.1 Why SahulatKar Needs Institutional Partnerships
As an NBFC (Non-Banking Finance Company) under SECP, SahulatKar cannot originate deposits or hold banking licenses. To function as a lending platform, it needs institutional partnerships for three critical functions:
- Capital for Lending: SahulatKar buys products on behalf of users using its own capital — this requires a warehouse credit facility or banking partner to fund the loan book.
- Payment Rails: Receiving and disbursing funds requires integration with licensed payment operators.
- Risk Coverage: Insurance products can cover credit default risk, delivery failures, and product liability.

## 5.2 Model: The Daira-ABHI Microfinance Bank Blueprint
In January 2026, Daira (an SECP-licensed NBFC under FinVolution/Finleap) and ABHI Microfinance Bank announced Pakistan's first bank-fintech BNPL partnership — the closest existing template for SahulatKar:
- Structure: Daira handles the technology, product, and customer acquisition. ABHI Microfinance Bank provides regulated banking infrastructure — capital, clearing, and deposit-taking.
- Result: 1.5 million registered users achieved within 15 months of launch.
- Regulatory Benefit: Partnering with a licensed bank gives Daira access to SBP's eCIB data, formal interbank payment rails, and increased borrower credibility.


## 5.3 Types of Banking Partnerships
### A. Sponsor Bank / Lending Partner
SahulatKar originates the loan but a sponsor bank holds it on their balance sheet, funding each transaction. SahulatKar earns a servicing fee. This is common in the USA (Affirm + Cross River Bank) and increasingly in Pakistan.
- Target Partners: ABHI Microfinance Bank, U Microfinance Bank, Telenor Microfinance Bank, Mobilink Microfinance Bank.
- Benefit: Access to SBP eCIB, significantly lower capital requirements for SahulatKar (NBFC minimum PKR 300-500M vs. bank's balance sheet).
- Structure: Revenue-sharing on interest/fee income. Bank takes credit risk; SahulatKar takes operational/technology risk.

### B. Payment/Disbursement Partner
For receiving user repayments and disbursing purchase payments to merchants:
- Raast (SBP): Pakistan's instant payment system for low-cost real-time fund transfers. SahulatKar should register as a Raast participant (or partner with a Raast-connected bank) to enable instant installment repayments.
- JazzCash / Easypaisa: Partner with both wallet operators to enable repayment collection from the unbanked majority. Their combined 30M+ user base is SahulatKar's primary target market.
- HBL / MCB: For merchant payouts via IBFT (Interbank Fund Transfer) once the product purchase is confirmed.

### C. Virtual Card Partner
For issuing single-use virtual cards to execute purchases on merchant websites:
- International (MVP Phase): Stripe Issuing (sandbox first). Low engineering overhead; global acceptance. Limitation: Pakistani businesses cannot currently hold a US Stripe account directly without a US entity — requires careful legal structuring.
- Local Partner (Scale Phase): HBL, MCB, or UBL have existing Visa/Mastercard issuance programs. Partnering with them to issue commercial prepaid cards under their BIN (Bank Identification Number) is the preferred long-term model. This also resolves the MCC-locking requirement natively.
- Alternative: 1LINK's shared payment switch infrastructure connects all Pakistani banks — a partnership here enables multi-bank card issuance.

## 5.4 Credit Bureau Integration
SahulatKar must integrate with Pakistan's credit bureaus at both the data intake and reporting stages:



## 5.5 Insurance Partnerships
SahulatKar's unique risk profile — acting as buyer/proxy for products it does not physically hold — creates insurance needs that differ from standard BNPL:

### A. Credit Default Insurance
Covers the principal loss when a user defaults on their installments. Structure:
- Provider: Adamjee Insurance, Jubilee Insurance, EFU General Insurance, or new digital insurtech players.
- Coverage: SahulatKar pays a premium (% of each loan originated) and in return, the insurer covers a defined percentage of default losses above a certain threshold (e.g., covers 60% of losses above 2% default rate).
- Benefit: Dramatically reduces capital requirements, enables faster growth, and makes SahulatKar more attractive to a banking capital partner.
- Onboarding Insurers: SahulatKar must share its loan data schema, fraud mitigation framework, and projected default rates. Start with a quota share arrangement (insurer takes a defined % of each loan's risk in exchange for a defined % of the fee revenue).

### B. Product Liability & Non-Delivery Insurance
Unique to SahulatKar's proxy buyer model: what if the product is not delivered, is counterfeit, or is significantly different from what was described?
- Provider: Marine cargo / e-commerce insurance products from Salaam Takaful, EFU General, or a Takaful operator (for Shariah compliance).
- Coverage: Reimburses SahulatKar for the purchase price if the merchant fails to deliver, delivers a counterfeit product, or misrepresents the item — covering cases where chargeback recovery is insufficient.
- Shariah Compliance: Use Takaful (Islamic insurance) products to maintain Shariah compliance of the platform end-to-end. Key Takaful operators in Pakistan: Salaam Takaful, Pak-Qatar Family Takaful.

### C. Embedded Insurance for Users
A revenue-generating feature: offer users optional product insurance (warranty extension, accidental damage) embedded within the SahulatKar checkout:
- White-label insurance product sourced from a Takaful partner, embedded at checkout.
- Revenue model: SahulatKar earns an affiliate commission on each policy sold.
- User benefit: One-click device insurance for the phone/laptop they just financed.

## 5.6 Partnership Onboarding Playbook
How to approach banks and insurance companies:

- Regulatory Foundation First: Obtain SECP NBFC lending license before approaching banks. Banks will not partner with an unlicensed entity. NBFC licensing requires PKR 300-500 million minimum paid-up capital and a fit-and-proper test for directors.
- Build an MVP Data Room: Prepare loss rate projections, credit model documentation, KYC flow diagrams, and fraud mitigation framework (this research document is the foundation). Banks need to see that the credit risk is modeled properly.
- Start with Microfinance Banks (MFBs): More agile and mission-aligned (financial inclusion) than commercial banks. ABHI MFB, U Microfinance Bank, and Telenor MFB are the top targets based on the Daira precedent.
- Apply to SBP Regulatory Sandbox: For innovative fintech products, SBP's sandbox allows testing with limited regulatory oversight before full licensing — reduces time-to-market and signals regulatory goodwill.
- Insurance: Approach Adamjee or Jubilee with an actuarial pitch — provide them with your projected loan book size, default rate assumptions, and KYC/fraud framework. Negotiate a pilot quota share arrangement covering the first 6 months.
- SECP Fintech Office: SECP has a dedicated fintech facilitation desk. Engage proactively — they can expedite licensing and provide regulatory clarity on specific features (e.g., Wakalah structure for Shariah compliance).


# 6. Regulatory Compliance Checklist (Pakistan)
SahulatKar must comply with the following regulatory requirements:



# 7. KYC & Fraud Implementation Roadmap


# 8. Key Recommendations & Conclusions
## 8.1 Top 10 Strategic Recommendations

- Integrate NADRA Verisys as the primary identity backbone — no other verification layer can replace CNIC confirmation at the state level.
- Implement facial biometric liveness detection from day one — this is the single most effective countermeasure against CNIC theft and impersonation fraud.
- Mandate a first installment down payment before any purchase execution — the "first payment barrier" is the highest-ROI fraud filter available.
- Pursue a bank-fintech partnership (modeled on Daira-ABHI) for capital access, SBP eCIB integration, and Raast payment rails.
- Report to TASDEEQ from the very first transaction — positive reporting is a user retention tool; negative reporting is a deterrence mechanism.
- Build the cross-border abandonment fraud model as a first-class feature, not an afterthought — this is SahulatKar's most unique and highest-loss risk.
- Apply to SBP's Regulatory Sandbox before full launch — it reduces regulatory risk and signals credibility to banking and insurance partners.
- Use domain-locked, amount-locked, time-limited virtual cards for every transaction — this fully eliminates the collusion/fake merchant fraud vector.
- Engage a Shariah Supervisory Board to formally certify the Wakalah structure — SECP and users will require this for the platform to be taken seriously as a Shariah-compliant product.
- Start with low credit limits (Rs. 1,500-3,000) and grow them based on demonstrated repayment behavior — progressive limit expansion is both a risk control and a user engagement tool.

## 8.2 The Fraud vs. UX Balance
The fundamental tension in BNPL KYC is between security and conversion. Research shows 68% of users abandon digital onboarding that feels too invasive. SahulatKar's target is:
- Tier 1 (standard users): 4-minute onboarding maximum. CNIC OCR + NADRA verification + selfie liveness = under 3 minutes with a fast API.
- Tier 2 (enhanced review): Up to 10 minutes, but flagged users should receive clear, non-accusatory communication that their account is "under review" rather than being told they are suspected of fraud.
- Risk-based routing: Do not apply Tier 2 checks universally — only when the risk score triggers it. 80%+ of legitimate users should sail through Tier 1.


SahulatKar — Your Ethical Financial Partner
NUCES Chiniot | FYP 2026 | Research Document
| Key Finding
The viability of SahulatKar's 4% service fee model is directly contingent on achieving >90% automation in the purchasing pipeline AND maintaining a fraud/default rate below 1.5%. KYC quality is the single most important upstream variable that determines both metrics. |
| --- |
| SahulatKar Implication
KalPay's manual phone call verification is a significant bottleneck for a vendor-agnostic, automated platform. SahulatKar must replace this with real-time automated CNIC verification, biometric liveness checks, and automated credit decisioning — while maintaining an equivalent fraud filter function. |
| --- |
| Data Field | Purpose | Verification Method |
| --- | --- | --- |
| Full Name (as per CNIC) | Identity confirmation | NADRA CNIC OCR + database match |
| CNIC Number (13-digit) | Unique citizen identifier | NADRA Verisys API real-time lookup |
| Date of Birth | Age eligibility (18+) | Auto-extracted from CNIC via OCR |
| CNIC Expiry / Status | Confirm active identity | NADRA Verisys — block expired CNICs |
| Selfie / Facial Biometric | Liveness detection, face-CNIC match | AI liveness check + face match (e.g., Shufti Pro, uqudo) |
| Mobile Number (verified) | Contact, OTP authentication | OTP SMS; cross-reference NADRA-registered SIM |
| Email Address | Communications, fraud signal | Email age check + deliverability check |
| Shipping Address | Delivery, fraud geolocation check | Address validation + CNIC address cross-reference |
| Device Fingerprint | Device risk assessment | Automated at app install (see Section 4) |
| Data Field | Purpose | Trigger |
| --- | --- | --- |
| Bank Account Connection (Open Banking) | Cash flow underwriting, income verification | Orders > Rs. 5,000 or risk score flag |
| Income / Employment Proof | Repayment capacity | Orders > Rs. 10,000 |
| Utility Bill / Address Proof | Address confirmation | Mismatch between CNIC address and shipping address |
| Video KYC | High-confidence identity verification | Elevated fraud score or appeals process |
| Next-of-Kin / Guarantor CNIC | Recovery contact for high limits | Credit limits > Rs. 25,000 |
| Regulatory Requirement
SECP Circular 15 of 2022 (and 2025 amendments) mandates that all licensed NBFCs engaged in digital lending must perform digital KYC using verifiable electronic means before disbursing any credit. A "Borrower Fact Sheet" (BFS) must be presented and acknowledged before credit is extended. Failure to comply results in blacklisting from SECP's approved digital lending whitelist. |
| --- |
| Criterion | Requirement | Rationale |
| --- | --- | --- |
| Nationality | Pakistani national (CNIC holder) | NADRA verification infrastructure; NICOP holders may be accommodated later |
| Age | 18 years or older | Legal capacity to enter contracts; SECP requirement |
| CNIC Status | Valid, non-expired, non-blocked | Identity integrity; NADRA Verisys check |
| Mobile Number | Pakistani SIM, registered to applicant CNIC | PTA SIM-CNIC match; primary OTP channel |
| Device | Smartphone (Android 8+ / iOS 13+) | App functionality; device fingerprinting capability |
| Biometric Match | Selfie must match CNIC photo (>80% confidence) | Anti-impersonation; liveness detection required |
| Credit Limit Eligibility | Risk score above threshold (see Section 4) | Automated credit decision engine |
| Shipping Address | Must be within Pakistan | Critical fraud control — see Section 4.4 |
| eCIB Clean History | No active defaults > Rs. 500,000 on SBP eCIB | SECP requires credit bureau checks for lending decisions |
| Wakalah Agreement | Must accept Shariah agency agreement | Shariah compliance; legal basis for proxy purchase |
| Data Source | Signals Derived | Pakistan Availability |
| --- | --- | --- |
| Telecom/Mobile Usage | Airtime recharge frequency & amount, SIM tenure, data usage patterns, bill payment regularity | High — Telenor, Jazz, Zong APIs available |
| Mobile Wallet Behavior | JazzCash/Easypaisa: top-up cadence, P2P transfer history, merchant payment regularity, cash-out frequency | High — Primary financial rails for unbanked |
| Bank Account (Open Banking) | Income regularity, expense volatility, NSF/overdraft frequency, existing debt payments | Medium — SBP digital banks (Easypaisa Bank, Mashreq) growing |
| E-commerce History | Purchase frequency, return rate, average order value, merchant diversity (loyalty signal) | Medium — Daraz, Foodpanda, Bykea data if partnered |
| Utility Payments | WAPDA/SNGPL bill payment timeliness and regularity | Medium — TASDEEQ integrates some utility data |
| Device & Digital Footprint | Device age, installed financial apps, IP stability, email age, social media tenure | High — Capturable at app install |
| SahulatKar Repayment History | Own installment payment track record — most powerful signal | Builds over time — zero at launch |
| Behavioral Biometrics | Typing cadence, form-fill speed, mouse movements, session duration | High — Capturable in-app |
| Score Band | Risk Level | Credit Limit | Action |
| --- | --- | --- | --- |
| 750-1000 | Low | Rs. 5,000 – 25,000 | Auto-approve, instant |
| 500-749 | Medium | Rs. 1,500 – 5,000 | Auto-approve with down payment |
| 300-499 | High | Rs. 1,500 (first order only) | Enhanced checks required |
| 0-299 | Very High | Decline | Manual review or waitlist |
| Fraud Type | Description | Pakistan-Specific Risk Level |
| --- | --- | --- |
| Synthetic Identity Fraud | Combining a real CNIC number with fake name/address to create a "Frankenstein" identity. In Pakistan, stolen/borrowed CNICs are a significant risk. | HIGH — Large informal CNIC-sharing culture |
| Account Takeover (ATO) | Phishing or SIM-swapping to take over a legitimate KYC-verified account and use its credit limit fraudulently. | HIGH — SIM-swap fraud is common in PK telecoms |
| Cross-Border Abandonment | User places order, receives product, then emigrates abroad before repayment — primary Pakistan-specific risk. | CRITICAL — Pakistan-specific. Seasonal pattern around family migration. |
| Collusion Fraud (Fake Merchant) | In vendor-agnostic model: fraudster creates a fake Shopify store, "buys" from it using SahulatKar, and pockets the payment. | HIGH — Unique to SahulatKar's OTT architecture |
| Friendly Fraud / First-Party Fraud | Legitimate user receives product but disputes the charge, claims non-delivery, or defaults intentionally knowing social/legal recourse is limited. | HIGH — Limited formal credit enforcement in PK |
| Bot-Driven Mass Applications | Automated bots submitting thousands of fraudulent applications to find weak spots in the onboarding system. | MEDIUM — Growing sophistication |
| CNIC Theft/Forgery | Using a stolen or physically copied CNIC belonging to someone else. | HIGH — Facial biometric liveness is the primary countermeasure |
| Scenario
A user in Pakistan orders Rs. 20,000 worth of electronics (phone + accessories) using SahulatKar's BNPL. They receive the goods, make the first installment, then emigrate to Saudi Arabia/UAE/UK for work. They stop making payments, knowing that SahulatKar has no legal recourse across borders and Pakistani civil enforcement of micro-debts is impractical. |
| --- |
| Algorithm / Technique | Use Case | Rationale |
| --- | --- | --- |
| XGBoost (Gradient Boosting) | Credit risk scoring at onboarding and per transaction | 93.7% accuracy in BNPL fraud scoring; handles mixed data types well |
| Isolation Forest | Real-time anomaly detection for unusual transaction patterns | Unsupervised; finds novel fraud patterns not in training data |
| Random Forest | Feature importance for alternative credit scoring | Robust against overfitting; good for imbalanced fraud datasets |
| LSTM / Recurrent Neural Network | Sequential payment behavior analysis over time | Captures temporal patterns in repayment; detects deteriorating creditworthiness |
| Graph Neural Networks (GNN) | Ring fraud detection (detecting fraud networks sharing devices/addresses/CNICs) | Identifies coordinated fraud rings that individual-level models miss |
| Behavioral Biometrics ML | Typing pattern, gesture analysis to distinguish humans from bots | Real-time, frictionless; very hard for fraudsters to replicate |
| Rule-Based Velocity Checks | Hard stops: >3 orders/day, >2 CNICs/device, international IP at checkout | Zero-latency enforcement of absolute rules before ML scoring |
| Computer Vision (OCR + Face Match) | CNIC document authenticity + selfie-to-CNIC match | Primary anti-impersonation layer; Hugging Face / pre-trained models |
| Blueprint for SahulatKar
SahulatKar should pursue a similar Bank-Fintech partnership model. Target: Microfinance banks (ABHI MFB, Mobilink MFB, U Microfinance Bank) or digital banks (Easypaisa Bank, Telenor Microfinance Bank) as banking partners. This enables SBP eCIB access, Raast integration for repayments, and a legitimate capital source for the loan book. |
| --- |
| Bureau | Data Coverage | SahulatKar Action |
| --- | --- | --- |
| SBP eCIB | All SBP-regulated institutions: banks, MFBs, DFIs, NBFCs. Borrowers above Rs. 500,000. | Mandatory for NBFC membership. Access via banking partner. Report defaults > Rs. 500,000. |
| TASDEEQ | Wider coverage: telecoms, utilities, insurance, and lower-value lending. First SBP-licensed private bureau. | PRIMARY partner for SahulatKar. Report ALL repayments (positive and negative) from day one. Pull TASDEEQ score at every application. |
| DataCheck | Microfinance-focused bureau. | Integrate for thin-file applicants in microfinance-active areas. |
| Strategic Recommendation
SECP's 2025 amendments to NBFC Regulations now make credit bureau reporting mandatory for all lending NBFCs. SahulatKar must report to TASDEEQ (at minimum) for every completed loan. This is both a legal requirement AND a commercial tool — positive repayment reporting builds user loyalty (they benefit from improving credit scores) and negative reporting deters default. |
| --- |
| Requirement | Details | Status |
| --- | --- | --- |
| SECP NBFC License | PKR 300-500M paid-up capital; fit-and-proper test for directors; digital lending NBFC category | Required before launch |
| SECP Circular 15 of 2022 | Digital KYC mandatory; Key Fact Statement (KFS/BFS) before credit; data residency in Pakistan; grievance redressal mechanism | Build into onboarding flow |
| SECP 2025 Amendments | Mandatory credit bureau reporting; official BNPL definition introduced; higher prudential limits for P2P; escrow accounts for P2P | Report to TASDEEQ from day 1 |
| AML/CFT Compliance (AML Act 2010) | Customer Due Diligence; Enhanced Due Diligence for high-risk; transaction monitoring; STR/SAR filing with FMU | Build monitoring system |
| PECA 2016 (Cybercrime) | Data protection obligations; digital fraud reporting to FIA cybercrime wing | Integrate FIA reporting endpoint |
| Electronic Transactions Ordinance 2002 | Digital signatures, electronic contracts (Wakalah Agreement) are legally valid | E-signatures on Wakalah compliant |
| SBP eCIB Membership | Via banking partner; mandatory for NBFCs receiving SBP-regulated funding | Via bank partnership |
| Shariah Compliance (SECP IFD) | Agency Murabaha / Wakalah structure must be reviewed by a qualified Shariah Supervisory Board | Engage Shariah advisor |
| Data Localization | All customer data must be stored on servers within Pakistan | Use AWS Bahrain or local data centers |
| Phase | Timeline | KYC/Fraud Milestones | Key Vendors/Partners |
| --- | --- | --- | --- |
| Phase 1 | Jan-Feb 2026 | Design KYC flow; NADRA Verisys integration; Shufti Pro/uqudo API trial; device fingerprinting SDK integration | NADRA, Shufti Pro / uqudo, SECP (regulatory engagement) |
| Phase 2 | Feb-Mar 2026 | Build credit scoring XGBoost model with synthetic data; integrate TASDEEQ bureau; design Wakalah digital agreement; manual fraud review process | TASDEEQ, JazzCash/Easypaisa (wallet), law firm (Wakalah) |
| Phase 3 | Mar-Jun 2026 | Full Playwright agentic checkout with stealth; real-time fraud scoring (Isolation Forest); behavioral biometrics integration; Raast repayment integration | Sardine.ai/BioCatch, SBP (Raast access), bank partner MOU |
| Phase 4 | Jul-Aug 2026 | Testing: penetration testing of KYC flow; fraud red team exercise; credit model backtesting; regulatory audit preparation | External security auditor, SECP pre-launch review |
| Phase 5 | Sep-Oct 2026 | Go-live: SECP whitelist listing; credit bureau reporting live; bank partnership capital facility active; insurance cover in place | SECP, TASDEEQ, Bank partner, Takaful insurer |
| Final Conclusion
SahulatKar's KYC and fraud mitigation system is not merely a compliance function — it is the core engine that determines the platform's commercial viability. A well-designed system catches fraud early, enables better credit decisions, creates user trust, satisfies regulators, and provides the data infrastructure needed to grow credit limits over time. Investment in this layer pays dividends across every dimension of the business. |
| --- |