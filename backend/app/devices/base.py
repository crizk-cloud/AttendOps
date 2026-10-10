"""Vendor-neutral device integration interface.

Each device model is driven by a DeviceDriver. At registration the driver identifies the device
(model, firmware) and probes which operations it supports. The result is stored per device in
devices.capabilities, so the rest of the app asks "can this device do X?" instead of assuming.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class DeviceStatus(StrEnum):
    unknown = "unknown"          # never checked
    online = "online"            # answered an authenticated request
    offline = "offline"          # no network answer (timeout, refused, unreachable)
    auth_failed = "auth_failed"  # reachable, but credentials rejected
    error = "error"              # reachable, but answered unexpectedly


class Operation(StrEnum):
    device_info = "device.info"
    history_read = "history.read"
    events_subscribe = "events.subscribe"
    users_read = "users.read"
    cards_read = "cards.read"
    cards_read_legacy = "cards.read_legacy"
    users_write = "users.write"
    cards_write = "cards.write"


class CapabilityState(StrEnum):
    verified = "verified"        # a real call succeeded against this device
    unsupported = "unsupported"  # the device answered that it does not support it
    unverified = "unverified"    # not tested (or result inconclusive) - treat as unavailable


@dataclass
class Capability:
    state: CapabilityState
    detail: str = ""


@dataclass
class DeviceIdentity:
    model: str | None = None
    firmware: str | None = None
    serial_no: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class CheckResult:
    status: DeviceStatus
    identity: DeviceIdentity | None = None
    error: str | None = None
    response_ms: int | None = None


class DeviceDriver(Protocol):
    vendor: str

    def check(self) -> CheckResult:
        """Cheap authenticated call: is the device reachable and are the credentials right?"""
        ...

    def probe_capabilities(self) -> dict[Operation, Capability]:
        """Read-only probing of which operations work. Must never modify the device."""
        ...


def capabilities_to_json(caps: dict[Operation, Capability]) -> dict[str, Any]:
    return {op.value: {"state": c.state.value, "detail": c.detail} for op, c in caps.items()}
