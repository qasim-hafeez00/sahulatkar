from src.config import settings

from .base import NadraProvider
from .mock_provider import MockNadraProvider
from .verisys_provider import NadraVerisysProvider


def get_nadra_provider() -> NadraProvider:
    """Resolve the configured CNIC verification backend (NADRA_PROVIDER)."""
    if settings.NADRA_PROVIDER == "verisys":
        return NadraVerisysProvider()
    return MockNadraProvider()
