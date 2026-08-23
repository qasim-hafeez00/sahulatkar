from abc import ABC, abstractmethod


class NadraProvider(ABC):
    """Contract every CNIC identity-verification backend must satisfy.

    src/services/kyc.py depends only on this shape (verify_cnic(cnic) ->
    bool). Swapping the mock for a real NADRA Verisys connection — or any
    other provider — is a config change (NADRA_PROVIDER) plus a new class
    implementing this method, never a change at the call site.
    """

    @abstractmethod
    async def verify_cnic(self, cnic: str) -> bool:
        """Return True if the CNIC is a valid, verified national identity record."""
        raise NotImplementedError
