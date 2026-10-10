"""Chooses a driver for a device. Only Dahua today; new vendors/models register here."""

import httpx

from app.devices.base import DeviceDriver
from app.devices.dahua.driver import DahuaDriver

SUPPORTED_VENDORS = {"dahua": DahuaDriver}


def get_driver(vendor: str, ip: str, port: int, username: str, password: str,
               transport: httpx.BaseTransport | None = None) -> DeviceDriver:
    try:
        cls = SUPPORTED_VENDORS[vendor]
    except KeyError:
        raise ValueError(f"unsupported vendor {vendor!r}") from None
    return cls(ip, port, username, password, transport=transport)
