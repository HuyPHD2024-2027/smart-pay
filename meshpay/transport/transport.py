from typing import Dict, Optional, Protocol, Union, List
from enum import Enum
from meshpay.types import Address
from meshpay.messages import Message

class NetworkTransport(Protocol):
    """Protocol that any concrete transport must implement."""

    def send_message(self, message: Message, target: Address) -> bool:  # pragma: no cover
        """Transmit *message* to *target*.

        Implementations **must** be blocking and return *True* only when the payload has been
        handed over to the network stack without local errors.  They **should not** attempt to
        infer success on the remote side; higher-level logic in :class:`Client` is in charge
        of evaluating responses.
        """

    def receive_message(self, timeout: float = 1.0) -> Optional[Message]:  # pragma: no cover
        """Blocking receive with *timeout* seconds.
        
        The method should return a fully deserialised :class:`mn_wifi.messages.Message` instance or
        *None* when the timeout expires.  Implementations are free to raise exceptions on fatal
        conditions, but transient errors should be logged internally and converted into *None* to
        allow the caller to decide on a retry strategy.
        """

class TransportKind(Enum):
    """User-friendly enumeration to select the desired transport type."""

    TCP = "tcp"
    UDP = "udp"
    WIFI_DIRECT = "wifi_direct"