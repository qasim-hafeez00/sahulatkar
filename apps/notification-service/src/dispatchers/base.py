from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class DispatchResult:
    success: bool
    provider_message_id: Optional[str] = None
    provider_name: Optional[str] = None
    failure_reason: Optional[str] = None
    should_retry: bool = True  # False for permanent failures (e.g. invalid number)


class BaseDispatcher(ABC):
    """
    All dispatchers implement this interface.
    Dispatchers are stateless; they receive fully-rendered content and
    a destination identifier (phone / token / email).
    """

    @abstractmethod
    async def send(
        self,
        *,
        destination: str,        # phone / device_token / email_address
        content: str,            # fully rendered message body
        subject: Optional[str],  # email subject / push title
        notification_id: int,    # for correlation in logs
    ) -> DispatchResult:
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Returns True if the provider is reachable."""
        ...
