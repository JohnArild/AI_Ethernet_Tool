"""Fault specification and validation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

DIRECTIONS = ("both", "to_uut", "to_tester")
SIDES = ("lan", "wan", "both")
PHY_SPEEDS = (10, 100, 1000)


class FaultError(ValueError):
    """Invalid fault request."""


@dataclass
class FaultSpec:
    delay_ms: float = 0.0
    jitter_ms: float = 0.0
    loss_pct: float = 0.0
    loss_correlation: float = 0.0
    rate: str | None = None
    duplicate_pct: float = 0.0
    reorder_pct: float = 0.0
    corrupt_pct: float = 0.0
    direction: str = "both"
    link_down: str | None = None
    flap_ms: int = 0
    phy_speed: int | None = None
    phy_side: str = "both"
    duration_s: int | None = 60

    def has_netem(self) -> bool:
        return any(
            (
                self.delay_ms > 0,
                self.jitter_ms > 0,
                self.loss_pct > 0,
                self.rate,
                self.duplicate_pct > 0,
                self.reorder_pct > 0,
                self.corrupt_pct > 0,
            )
        )

    def is_pass_through(self) -> bool:
        return not self.has_netem() and not self.link_down and self.phy_speed is None

    def validate(self) -> None:
        if self.direction not in DIRECTIONS:
            raise FaultError(f"direction must be one of {DIRECTIONS}")
        if self.link_down is not None and self.link_down not in SIDES:
            raise FaultError(f"link_down must be one of {SIDES}")
        if self.phy_side not in SIDES:
            raise FaultError(f"phy_side must be one of {SIDES}")
        if self.phy_speed is not None and self.phy_speed not in PHY_SPEEDS:
            raise FaultError(f"phy_speed must be one of {PHY_SPEEDS}")
        for name in (
            "delay_ms",
            "jitter_ms",
            "loss_pct",
            "loss_correlation",
            "duplicate_pct",
            "reorder_pct",
            "corrupt_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise FaultError(f"{name} must be >= 0")
        for name in ("loss_pct", "loss_correlation", "duplicate_pct", "reorder_pct", "corrupt_pct"):
            if getattr(self, name) > 100:
                raise FaultError(f"{name} must be <= 100")
        if self.jitter_ms > 0 and self.delay_ms <= 0:
            raise FaultError("jitter_ms requires delay_ms")
        if self.flap_ms < 0:
            raise FaultError("flap_ms must be >= 0")
        if self.flap_ms and not self.link_down:
            raise FaultError("flap_ms requires link_down")
        if self.duration_s is not None and self.duration_s < 0:
            raise FaultError("duration_s must be >= 0")
        if self.rate:
            parse_rate_bps(self.rate)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FaultSpec:
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known - {"profile"}
        if unknown:
            raise FaultError(f"unknown fields: {sorted(unknown)}")
        filtered = {k: v for k, v in data.items() if k in known}
        spec = cls(**filtered)
        spec.validate()
        return spec


def parse_rate_bps(rate: str) -> int:
    """Return bits/s. Accepts tc-style units: 10mbit, 100kbit, 1gbit, 10mbps."""
    text = rate.strip().lower()
    text = (
        text.replace("mbps", "mbit")
        .replace("gbps", "gbit")
        .replace("kbps", "kbit")
        .replace("bps", "bit")
    )
    multipliers = (
        ("gbit", 1_000_000_000),
        ("mbit", 1_000_000),
        ("kbit", 1_000),
        ("bit", 1),
        ("g", 1_000_000_000),
        ("m", 1_000_000),
        ("k", 1_000),
    )
    for suffix, mul in multipliers:
        if text.endswith(suffix):
            number = text[: -len(suffix)]
            try:
                return int(float(number) * mul)
            except ValueError as exc:
                raise FaultError(f"invalid rate: {rate}") from exc
    try:
        return int(text)
    except ValueError as exc:
        raise FaultError(f"invalid rate: {rate}") from exc


def rate_to_tc(rate: str) -> str:
    """Normalize a rate string to a tc netem token (e.g. 10mbit)."""
    bps = parse_rate_bps(rate)
    if bps % 1_000_000_000 == 0:
        return f"{bps // 1_000_000_000}gbit"
    if bps % 1_000_000 == 0:
        return f"{bps // 1_000_000}mbit"
    if bps % 1_000 == 0:
        return f"{bps // 1_000}kbit"
    return f"{bps}bit"


def format_ms(value: float) -> str:
    if value == int(value):
        return f"{int(value)}ms"
    return f"{value}ms"
