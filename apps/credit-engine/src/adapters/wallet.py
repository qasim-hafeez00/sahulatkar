from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WalletAdapter(Protocol):
    """Port for a mobile-wallet activity signal. AffordabilityEngine depends only on this
    interface, so swapping the mock for a real JazzCash/Easypaisa integration is a
    one-adapter change with no changes to the engine or pipeline."""

    provider: str

    async def get_activity_score(self, user_id: str) -> float: ...


class MockJazzCashAdapter:
    """Stand-in until the real JazzCash/Easypaisa wallet API integration exists. Returns the
    same fixed score the old layer4_alt_data.py mock always did."""

    provider = "mock-jazzcash"

    async def get_activity_score(self, user_id: str) -> float:
        return 55.0
