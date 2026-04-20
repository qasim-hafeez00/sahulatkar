from decimal import Decimal

import pytest

from src.extractors.rye_client import RyeClient


@pytest.mark.asyncio
async def test_price_in_subunits_converted_to_decimal():
    assert RyeClient._decimal_from_subunits(1250000) == Decimal("12500.00")


def test_availability_mapping():
    assert RyeClient._map_availability("IN_STOCK") == "in_stock"
    assert RyeClient._map_availability("OUT_OF_STOCK") == "out_of_stock"
    assert RyeClient._map_availability("UNKNOWN") == "unknown"
