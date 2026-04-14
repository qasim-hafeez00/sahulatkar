from typing import Any


async def run_alt_data_signal(user_id: str) -> dict[str, Any]:
    # Stub adapter that can be swapped for JazzCash/Telco integration.
    return {
        "provider": "mock-jazzcash",
        "wallet_activity_score": 55.0,
        "income_signal": "stable",
        "user_id": user_id,
    }
