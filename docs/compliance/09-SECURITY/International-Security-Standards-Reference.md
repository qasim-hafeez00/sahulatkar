# International Security & Privacy Standards — Reference

None of these are Pakistani law. They're voluntary international benchmarks worth using for external security assessments, vendor due diligence, and shaping SahulatKar's own technical controls (especially around NADRA/KYC data and payment integrations). Where a standard's text is paywalled/licensed, only the official link is given — do not mirror the paywalled text into this repo.

| Standard | Relevance to SahulatKar | Official link |
|---|---|---|
| ISO/IEC 27001 (ISMS) | Certifiable framework for an information security management system; the standard reference point when a bank/EMI partner or an SECP digital-lending self-assessment asks "what's your security posture." Paywalled text. | https://www.iso.org/standard/27001 |
| ISO/IEC 27701 (Privacy extension to 27001) | Extends 27001 to personal-data management — directly relevant given the volume of CNIC/biometric data flowing through NADRA verification and KYC. Paywalled text. | https://www.iso.org/standard/71670.html |
| PCI DSS | Only in scope if SahulatKar's own systems store, process, or transmit cardholder data directly. If card capture happens entirely inside a licensed payment processor's hosted fields/redirect, PCI scope shrinks dramatically (SAQ-A territory) — this distinction should be an explicit architecture decision, not an accident. Requires an account to access full text. | https://www.pcisecuritystandards.org/ |
| OWASP ASVS (Application Security Verification Standard) | Free. A concrete, checklist-style standard for verifying the lending app's/API's security controls — good fit for the "self-assessment declaration" SECP's digital-lending whitelisting circular expects. | https://owasp.org/www-project-application-security-verification-standard/ |
| OWASP API Security Top 10 | Free. SahulatKar's product is API-driven (credit-engine, gateway, ledger, notification services) — this is the most directly applicable OWASP project. | https://owasp.org/API-Security/ |
| SOC 2 | Common ask from enterprise/bank partners doing vendor due diligence on a fintech counterparty; Type II (covering a period of operation, not just a point-in-time design review) is what's usually requested for an ongoing partnership. | https://www.aicpa-cima.com/resources/landing/system-and-organization-controls-soc-suite-of-services |
| CIS Controls | A prioritized, practical controls list (asset inventory, access control, logging, etc.) — useful as an implementation checklist underneath an ISO 27001 program rather than a certification target on its own. | https://www.cisecurity.org/controls |
| NIST Cybersecurity Framework (CSF) | Useful as a common vocabulary (Identify/Protect/Detect/Respond/Recover) when discussing risk posture with partners or regulators, even though it's a US framework with no direct Pakistani regulatory force. | https://www.nist.gov/cyberframework |

## How this fits with the Pakistani regulatory documents already in this library

- SECP's digital-lending circulars (`01-SECP/03-Digital-Lending/`, `04-App-Whitelisting/`) require a self-assessment declaration before an app is whitelisted — OWASP ASVS is the most practical free standard to run that self-assessment against.
- SBP's Technology Risk Management Framework for Payment Institutions (`02-SBP/05-Technology-Risk/`) and Mobile Apps Security Guidelines cover payment-institution-specific technical controls; treat those as the binding requirements and the standards above as the implementation toolkit underneath them.
- NADRA data handling (`03-NADRA/`) is the strongest driver for ISO 27701 relevance specifically — biometric and CNIC data is about as sensitive as personal data gets in this market.
