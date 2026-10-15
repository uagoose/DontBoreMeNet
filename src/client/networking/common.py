# core modules
from dataclasses import dataclass
from enum import IntEnum

# external modules
import psutil
import socket


class AddressType(IntEnum):
    MAC = socket.AF_LINK
    PSUTIL_MAC = psutil.AF_LINK
    IPv4 = socket.AF_INET
    IPv6 = socket.AF_INET6
    UNKNOWN = -999_999

    @classmethod
    def _missing_(cls, value):
        return cls.UNKNOWN


@dataclass
class Address:
    address_type: AddressType
    address: str
    mask: str | None

    @classmethod
    def from_psutil(cls, psutil_addr) -> "Address":
        return cls(
            address_type=AddressType(psutil_addr.family),
            address=psutil_addr.address,
            mask=psutil_addr.netmask,
        )
