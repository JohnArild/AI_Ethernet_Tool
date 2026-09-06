"""ip/tc/ethtool dataplane for a two-port transparent impairment box.

netem is egress-only. Bidirectional faults are applied on both data NICs.
Link-state and PHY speed use ip/ethtool on the chosen side(s).
"""

from __future__ import annotations

import json
import logging

from eit.models import FaultSpec, format_ms, parse_rate_bps, rate_to_tc
from eit.runner import Runner, SystemRunner

log = logging.getLogger("eit.dataplane")

OFFLOAD_FEATURES = (
    "tso",
    "gso",
    "gro",
    "lro",
    "rx",
    "tx",
    "sg",
    "ufo",
    "tso6",
)


def build_netem_args(spec: FaultSpec, assumed_link_bps: int = 1_000_000_000) -> list[str] | None:
    """Return tc args after `tc qdisc replace dev X root`, or None if no netem."""
    if not spec.has_netem():
        return None
    args = ["netem"]
    if spec.delay_ms > 0:
        args += ["delay", format_ms(spec.delay_ms)]
        if spec.jitter_ms > 0:
            args += [format_ms(spec.jitter_ms)]
    if spec.loss_pct > 0:
        args += ["loss", f"{spec.loss_pct}%"]
        if spec.loss_correlation > 0:
            args += [f"{spec.loss_correlation}%"]
    if spec.duplicate_pct > 0:
        args += ["duplicate", f"{spec.duplicate_pct}%"]
    if spec.reorder_pct > 0:
        args += ["reorder", f"{spec.reorder_pct}%"]
    if spec.corrupt_pct > 0:
        args += ["corrupt", f"{spec.corrupt_pct}%"]
    if spec.rate:
        args += ["rate", rate_to_tc(spec.rate)]
    delay_s = (spec.delay_ms + spec.jitter_ms) / 1000.0
    if delay_s > 0:
        bps = parse_rate_bps(spec.rate) if spec.rate else assumed_link_bps
        # Size the queue for min-sized frames so delay does not become loss.
        limit = max(10_000, int(bps * delay_s / 8 / 64) + 256)
        args += ["limit", str(limit)]
    return args


class DataPlane:
    def __init__(
        self,
        lan: str,
        wan: str,
        runner: Runner | None = None,
        assumed_link_bps: int = 1_000_000_000,
    ):
        self.lan = lan
        self.wan = wan
        self.runner = runner or SystemRunner()
        self.assumed_link_bps = assumed_link_bps

    def ports(self) -> tuple[str, str]:
        return (self.lan, self.wan)

    def ports_for_direction(self, direction: str) -> list[str]:
        if direction == "both":
            return [self.lan, self.wan]
        if direction == "to_uut":
            return [self.wan]
        if direction == "to_tester":
            return [self.lan]
        raise ValueError(f"invalid direction: {direction}")

    def sides_to_ports(self, side: str) -> list[str]:
        if side == "both":
            return [self.lan, self.wan]
        if side == "lan":
            return [self.lan]
        if side == "wan":
            return [self.wan]
        raise ValueError(f"invalid side: {side}")

    def apply(self, spec: FaultSpec) -> None:
        spec.validate()
        self.clear()
        if spec.is_pass_through():
            return
        netem = build_netem_args(spec, self.assumed_link_bps)
        if netem:
            for dev in self.ports_for_direction(spec.direction):
                self.runner.run(["tc", "qdisc", "replace", "dev", dev, "root", *netem])
        if spec.link_down:
            for dev in self.sides_to_ports(spec.link_down):
                self.runner.run(["ip", "link", "set", "dev", dev, "down"])
        if spec.phy_speed is not None:
            for dev in self.sides_to_ports(spec.phy_side):
                self.runner.run(
                    [
                        "ethtool",
                        "-s",
                        dev,
                        "speed",
                        str(spec.phy_speed),
                        "duplex",
                        "full",
                        "autoneg",
                        "off",
                    ]
                )

    def set_link(self, side: str, up: bool) -> None:
        action = "up" if up else "down"
        for dev in self.sides_to_ports(side):
            self.runner.run(["ip", "link", "set", "dev", dev, action])

    def clear(self) -> None:
        for dev in self.ports():
            self.runner.run(["tc", "qdisc", "del", "dev", dev, "root"], check=False)
            self.runner.run(["ip", "link", "set", "dev", dev, "up"], check=False)
            self.runner.run(["ethtool", "-s", dev, "autoneg", "on"], check=False)

    def prepare(self) -> None:
        """Disable offloads and EEE so netem sees real packets."""
        for dev in self.ports():
            off_args: list[str] = []
            for feat in OFFLOAD_FEATURES:
                off_args += [feat, "off"]
            self.runner.run(["ethtool", "-K", dev, *off_args], check=False)
            self.runner.run(["ethtool", "--set-eee", dev, "eee", "off"], check=False)
            self.runner.run(["ethtool", "-A", dev, "rx", "off", "tx", "off"], check=False)

    def qdisc(self, dev: str) -> str:
        result = self.runner.run(["tc", "qdisc", "show", "dev", dev], check=False)
        return result.stdout.strip()

    def iface_status(self, dev: str) -> dict:
        result = self.runner.run(["ip", "-j", "link", "show", "dev", dev], check=False)
        if result.returncode == 0 and result.stdout.strip():
            try:
                payload = json.loads(result.stdout)
                if payload:
                    entry = payload[0]
                    return {
                        "name": entry.get("ifname", dev),
                        "operstate": entry.get("operstate", "unknown").lower(),
                        "mtu": entry.get("mtu"),
                    }
            except json.JSONDecodeError:
                log.debug("ip -j parse failed for %s", dev)
        ethtool = self.runner.run(["ethtool", dev], check=False)
        return {
            "name": dev,
            "operstate": "unknown",
            "ethtool": ethtool.stdout.strip(),
        }

    def status(self) -> dict:
        return {
            "lan": {**self.iface_status(self.lan), "qdisc": self.qdisc(self.lan)},
            "wan": {**self.iface_status(self.wan), "qdisc": self.qdisc(self.wan)},
        }
