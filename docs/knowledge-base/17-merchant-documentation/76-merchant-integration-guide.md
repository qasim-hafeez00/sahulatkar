# Merchant Integration Guide

**Status:** STABLE — there is no integration for a merchant to build. This document exists so that if a merchant (or a partner-relations person fielding a merchant's question) asks "how do we integrate with SahulatKar," there's a clear, documented answer rather than silence or an improvised one.

## The answer, for a merchant asking how to integrate

**There is nothing to integrate.** SahulatKar does not offer a checkout SDK, a webhook contract, an order API, or any other merchant-facing integration surface. If a customer wants to buy from your store using SahulatKar, they simply paste your product's URL into the SahulatKar app — no action is required on your side, and none is possible today even if you wanted to formally partner.

## What SahulatKar does instead of asking a merchant to integrate

Builds and maintains its own extraction and checkout automation against your site's existing, ordinary consumer-facing storefront (see [`70-merchant-checkout-flow.md`](70-merchant-checkout-flow.md)) — the entire point of the vendor-agnostic model is that this doesn't require your cooperation.

## If a merchant wants a deeper relationship

Route to Business Development for the "affiliate partner" question (see [`75-merchant-commission-fee-model.md`](75-merchant-commission-fee-model.md)) — but be transparent that current engineering documentation does not confirm what, if anything, that relationship concretely offers a merchant today.

## Related documents

[`65-merchant-overview.md`](65-merchant-overview.md), [`70-merchant-checkout-flow.md`](70-merchant-checkout-flow.md), [`75-merchant-commission-fee-model.md`](75-merchant-commission-fee-model.md).
