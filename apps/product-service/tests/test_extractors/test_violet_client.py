from src.extractors.violet_client import VioletClient


def test_violet_availability_mapping():
    assert VioletClient._map_availability("IN_STOCK") == "in_stock"
    assert VioletClient._map_availability("OUT_OF_STOCK") == "out_of_stock"
    assert VioletClient._map_availability("LOW_STOCK") == "limited"
    assert VioletClient._map_availability("unknown") == "unknown"
