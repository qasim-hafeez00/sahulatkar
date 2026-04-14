from typing import Optional


PROHIBITED_CATEGORIES = {
    "alcohol",
    "tobacco",
    "gambling",
    "adult content",
    "weapons",
    "interest-bearing instruments",
    "non-halal food",
}


def run_order_overlay(
    base_limit: float,
    base_down_payment: float,
    category: str,
) -> tuple[float, float, bool, Optional[str], list[str]]:
    flags: list[str] = []
    normalized = category.strip().lower()

    if normalized in PROHIBITED_CATEGORIES:
        return 0.0, 0.0, True, "Prohibited category", ["prohibited_category"]

    multipliers = {
        "smartphones": 0.60,
        "gold jewelry": 0.40,
        "laptops": 0.65,
        "cameras": 0.70,
        "clothing": 1.0,
        "footwear": 1.0,
        "home appliances": 1.0,
        "general": 1.0,
    }
    mult = multipliers.get(normalized, 1.0)
    if mult < 1.0:
        flags.append("high_risk_category")

    adjusted_limit = base_limit * mult
    adjusted_down_payment = min(base_down_payment + (5.0 if mult < 0.7 else 0.0), 60.0)
    return adjusted_limit, adjusted_down_payment, False, None, flags
