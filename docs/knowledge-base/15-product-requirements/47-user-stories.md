# User Stories

**Status:** STABLE — derived directly from the screen references embedded in the module specs (e.g. `docs/System-md-files/M01-auth.md` cites "US-02, US-03"), which confirm a `US-01` through at least `US-20` numbering already exists in the product's design work even though a consolidated user-story document did not previously exist in this repository.

## Customer stories (US-01 through US-20, reconstructed from module-spec screen references)

| ID | Story | Source module |
|---|---|---|
| US-02 | As a new user, I want to register with just my phone number, so that I can start using SahulatKar without friction. | M01 |
| US-03 | As a new user, I want to verify my phone via OTP, so that my account is secured without needing to remember a password. | M01 |
| US-04–US-06 | As a user completing KYC, I want to submit my CNIC (front/back) and a liveness selfie, so that I can be verified quickly and start shopping. | M02 |
| US-07 | As a user, I want to see clear progress while my KYC/credit assessment runs, so that I'm not left wondering if the app is working. | M02 |
| US-08 | As a user, I want to see my credit limit as soon as it's determined, so that I know what I can afford to buy. | M02 |
| US-10 | As a user, I want to see a loading state while my pasted URL is being processed, so that I understand extraction takes a few seconds. | M03 |
| US-11 | As a user, I want to preview the extracted product (photo, price, variants) before committing, so that I can confirm it's the right item. | M03 |
| US-12 | As a user, I want to sign the Wakalah agreement clearly explaining what I'm authorizing, so that I understand SahulatKar is buying on my behalf. | M05 |
| US-13 | As a user, I want to see the full cost breakdown (cost price, profit, total) before signing the Murabaha contract, so that I know exactly what I'll repay. | M05 |
| US-14 | As a user, I want to pay my down payment through a payment method I already trust (JazzCash, EasyPaisa, card), so that I don't need to learn a new payment tool. | M06 |
| US-15 | As a user, I want to see the AI agent's purchase progress in real time, so that I have confidence my order is actually being placed. | M08 |
| US-17 | As a user, I want to track my delivery status in one place, so that I don't have to check the courier's own site separately. | M10 |
| US-18 | As a user, I want a wallet view of my active loans and balances, so that I always know what I owe. | M06 |
| US-19 | As a user, I want to pay an installment manually if I choose to, so that I'm not solely dependent on auto-debit. | M06 |

## Admin stories (AD-01 through AD-28, reconstructed from `docs/System-md-files/M12-admin.md`)

| ID | Story | Priority |
|---|---|---|
| AD-01 | As an admin of any role, I want a KPI command-center home screen, so that I can immediately see platform health. | Critical |
| AD-06 | As an operations manager, I want a prioritized HITL queue, so that I can resolve stuck checkouts before customers notice. | Critical |
| AD-09 | As a fraud analyst, I want a live alert queue, so that I can act on fraud signals before losses occur. | Critical |
| AD-13 | As a compliance officer, I want a Shariah compliance report, so that I can verify charity disbursement and disclosure compliance without querying the database directly. | High |
| AD-16 | As a compliance officer, I want a KYC manual review queue with an SLA countdown, so that no application goes stale. | High |

Full list of all 28 admin modules (AD-01–AD-28): `docs/System-md-files/M12-admin.md`.

## Known caveat

Several stories above describe screens/flows that are only partially implemented in the current build (e.g. US-15's "real-time purchase progress" depends on the checkout agent actually completing purchases, which is currently blocked — see [`../05-architecture/microservices/product-service.md`](../05-architecture/microservices/product-service.md)). These stories describe target UX, not confirmed current behavior.

## Related documents

[`45-prd.md`](45-prd.md), [`46-feature-requirements.md`](46-feature-requirements.md), [`48-acceptance-criteria.md`](48-acceptance-criteria.md).
