"""Command-line interface. Talks to eitd over HTTP, or applies locally with --direct."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from eit import __version__
from eit.config import load_config
from eit.dataplane import DataPlane
from eit.models import FaultError, FaultSpec
from eit.profiles import list_profiles, merge_profile
from eit.runner import CommandError


def _url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def http_json(method: str, url: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
            message = payload.get("error", raw)
        except json.JSONDecodeError:
            message = raw or str(exc)
        raise SystemExit(f"eitd error ({exc.code}): {message}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"cannot reach eitd at {url}: {exc.reason}. "
            "Start eitd, or pass --direct to apply on this host."
        ) from exc


def print_status(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2))


def add_fault_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="Named profile (JSON in profile dir)")
    parser.add_argument("--delay-ms", type=float, default=None)
    parser.add_argument("--jitter-ms", type=float, default=None)
    parser.add_argument("--loss-pct", type=float, default=None)
    parser.add_argument("--loss-correlation", type=float, default=None)
    parser.add_argument("--rate", help="Throughput cap, e.g. 10mbit")
    parser.add_argument("--duplicate-pct", type=float, default=None)
    parser.add_argument("--reorder-pct", type=float, default=None)
    parser.add_argument("--corrupt-pct", type=float, default=None)
    parser.add_argument("--direction", choices=("both", "to_uut", "to_tester"))
    parser.add_argument("--link-down", choices=("lan", "wan", "both"))
    parser.add_argument("--flap-ms", type=int, default=None, help="Link flap period in ms")
    parser.add_argument("--phy-speed", type=int, choices=(10, 100, 1000))
    parser.add_argument("--phy-side", choices=("lan", "wan", "both"))
    parser.add_argument("--duration", type=int, default=None, help="Seconds; 0 = until clear")


def flags_to_dict(args: argparse.Namespace) -> dict[str, Any]:
    mapping = {
        "profile": "profile",
        "delay_ms": "delay_ms",
        "jitter_ms": "jitter_ms",
        "loss_pct": "loss_pct",
        "loss_correlation": "loss_correlation",
        "rate": "rate",
        "duplicate_pct": "duplicate_pct",
        "reorder_pct": "reorder_pct",
        "corrupt_pct": "corrupt_pct",
        "direction": "direction",
        "link_down": "link_down",
        "flap_ms": "flap_ms",
        "phy_speed": "phy_speed",
        "phy_side": "phy_side",
        "duration": "duration_s",
    }
    data: dict[str, Any] = {}
    for attr, key in mapping.items():
        value = getattr(args, attr, None)
        if value is not None:
            data[key] = value
    return data


def spec_from_args(args: argparse.Namespace, profile_dir: Path) -> FaultSpec:
    data = flags_to_dict(args)
    if not data:
        raise FaultError("no fault parameters given")
    return merge_profile(data, profile_dir)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eit",
        description="Error Injection Tool — apply Ethernet faults on the inline box",
    )
    parser.add_argument("--version", action="version", version=f"eit {__version__}")
    parser.add_argument("--config", help="Path to config.json")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8080",
        help="eitd base URL (default http://127.0.0.1:8080)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Apply via ip/tc/ethtool on this host instead of talking to eitd",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Show current impairments and link state")
    sub.add_parser("clear", help="Remove all impairments (pass-through)")
    sub.add_parser("prepare", help="Disable NIC offloads and EEE")
    sub.add_parser("profiles", help="List named profiles")

    apply_p = sub.add_parser("apply", help="Apply a fault or named profile")
    add_fault_flags(apply_p)
    return parser


def run_direct(cmd: str, args: argparse.Namespace) -> int:
    config = load_config(Path(args.config) if args.config else None)
    plane = DataPlane(config.lan, config.wan, assumed_link_bps=config.assumed_link_bps)
    if cmd == "status":
        print_status({"state": "unknown", "interfaces": plane.status()})
        return 0
    if cmd == "clear":
        plane.clear()
        print("cleared")
        return 0
    if cmd == "prepare":
        plane.prepare()
        print("prepared")
        return 0
    if cmd == "profiles":
        for name in list_profiles(config.profile_dir):
            print(name)
        return 0
    if cmd == "apply":
        spec = spec_from_args(args, config.profile_dir)
        plane.apply(spec)
        print_status({"applied": spec.to_dict(), "interfaces": plane.status()})
        return 0
    raise SystemExit(f"unknown command {cmd}")


def run_http(cmd: str, args: argparse.Namespace) -> int:
    base = args.url
    if cmd == "status":
        print_status(http_json("GET", _url(base, "/v1/status")))
        return 0
    if cmd == "clear":
        print_status(http_json("POST", _url(base, "/v1/clear"), {}))
        return 0
    if cmd == "prepare":
        print_status(http_json("POST", _url(base, "/v1/prepare"), {}))
        return 0
    if cmd == "profiles":
        payload = http_json("GET", _url(base, "/v1/profiles"))
        for name in payload.get("profiles", []):
            print(name)
        return 0
    if cmd == "apply":
        data = flags_to_dict(args)
        if not data:
            raise FaultError("no fault parameters given")
        print_status(http_json("POST", _url(base, "/v1/faults"), data))
        return 0
    raise SystemExit(f"unknown command {cmd}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.direct:
            return run_direct(args.cmd, args)
        return run_http(args.cmd, args)
    except FaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except CommandError as exc:
        print(f"command failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
