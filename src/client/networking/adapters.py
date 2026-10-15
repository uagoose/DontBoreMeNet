# core modules
from enum import Enum, auto
import ipaddress

# external modules
import psutil
import socket
import wmi

# own modules
from common import *
from pprint import pprint as print


class AdapterType(Enum):
    PHYSICAL = auto()
    VIRTUAL = auto()
    LOOPBACK = auto()
    UNKNOWN = auto()


class AdapterNetType(Enum):
    IP_NET = auto()
    UNKNOWN = auto()


class Adapter:
    """
    - This class represents available to system network adapter.
    Class provides functionality for filtering and discovering adapters,
    and some information about them.

    - Adapter class is not intended to be created via default constructor.
    Use `discover_adapters()` function instead.
    """

    def __init__(
        self,
        name: str,
        addresses: dict[AddressType, list[Address]],
        is_loopback: bool = False,
    ) -> None:
        # given fields
        self.name = name
        self.addresses: dict[AddressType, list[Address]] = addresses

        # fields that are initialized internally
        self.adapter_type: AdapterType = AdapterType.UNKNOWN
        self.adapter_net_type: AdapterNetType = AdapterNetType.UNKNOWN

        # discover adapter type
        if is_loopback:
            self.adapter_type = AdapterType.LOOPBACK
        else:
            self.adapter_type = self.detect_adapter_type(self.name)

        # discover adapter net-type
        self.adapter_net_type = (
            AdapterNetType.IP_NET
            if (
                self.addresses[AddressType.IPv4] or self.addresses[AddressType.IPv6]
            )  # only if IPv4 or IPv6 is present
            else AdapterNetType.UNKNOWN
        )

    @staticmethod
    def detect_adapter_type(name: str) -> AdapterType:
        try:
            adapters = wmi.WMI(namespace=r"root\StandardCimv2").MSFT_NetAdapter()
        except wmi.x_wmi:
            return AdapterType.UNKNOWN

        for adapter in adapters:
            if (adapter.Name or "").casefold() != name.casefold():
                continue

            if adapter.HardwareInterface is True:
                return AdapterType.PHYSICAL

            if adapter.HardwareInterface is False:
                return AdapterType.VIRTUAL

            if adapter.Virtual is True:
                return AdapterType.VIRTUAL

            return AdapterType.UNKNOWN

        return AdapterType.UNKNOWN

    @staticmethod
    def is_loopback_adapter(addresses: list) -> bool:
        """
        - This static method expects a list of psutil's snicaddr objects.
        - Returns: bool | whether that collection of addresses is common for loopback adapter
        """

        ip_addresses = [
            ipaddress.ip_address(addr.address.split("%")[0])
            for addr in addresses
            if addr.family in (socket.AF_INET, socket.AF_INET6)
        ]

        return bool(ip_addresses) and all(addr.is_loopback for addr in ip_addresses)

    @staticmethod
    def discover_adapters(
        only_on: bool = True, ignore_loopback: bool = True
    ) -> list[Adapter]:
        # prepare info
        adapters = []
        addressable = psutil.net_if_addrs()
        adapters_stats = psutil.net_if_stats()

        def add_adapter(name: str, addresses: list):
            # handle only-on mode
            if only_on:
                stats = adapters_stats[name]
                if not stats.isup:
                    return

            is_loopback = Adapter.is_loopback_adapter(addresses)
            # handle loopback ignorance
            if ignore_loopback and is_loopback:
                return

            # initialize AddressType lists
            normalized_addresses: dict[AddressType, list[Address]] = {}
            for addr_type in AddressType:
                normalized_addresses[addr_type] = []

            # collect and create addresses
            for addr in addresses:
                normalized_addr = Address.from_psutil(addr)
                normalized_addresses[normalized_addr.address_type].append(
                    normalized_addr
                )

            new_adapter = Adapter(name, normalized_addresses, is_loopback)
            adapters.append(new_adapter)

        # go through any addressable adapter and collect them
        for adapter_name in addressable.keys():
            addresses = addressable[adapter_name]
            add_adapter(adapter_name, addresses)

        return adapters
