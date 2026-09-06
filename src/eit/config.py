"""Appliance configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PATHS = (
    Path("/etc/eit/config.json"),
    Path("config.json"),
)


@dataclass
class Config:
    lan: str = "eth0"
    wan: str = "eth1"
    bridge: str = "br-eit"
    listen_host: str = "127.0.0.1"
    listen_port: int = 8080
    default_duration_s: int = 60
    max_duration_s: int = 3600
    profile_dir: Path = Path("/etc/eit/profiles")
    assumed_link_bps: int = 1_000_000_000

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        ifaces = data.get("interfaces", {})
        listen = data.get("listen", {})
        return cls(
            lan=ifaces.get("lan", cls.lan),
            wan=ifaces.get("wan", cls.wan),
            bridge=ifaces.get("bridge", cls.bridge),
            listen_host=listen.get("host", cls.listen_host),
            listen_port=int(listen.get("port", cls.listen_port)),
            default_duration_s=int(data.get("default_duration_s", cls.default_duration_s)),
            max_duration_s=int(data.get("max_duration_s", cls.max_duration_s)),
            profile_dir=Path(data.get("profile_dir", cls.profile_dir)),
            assumed_link_bps=int(data.get("assumed_link_bps", cls.assumed_link_bps)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "interfaces": {"lan": self.lan, "wan": self.wan, "bridge": self.bridge},
            "listen": {"host": self.listen_host, "port": self.listen_port},
            "default_duration_s": self.default_duration_s,
            "max_duration_s": self.max_duration_s,
            "profile_dir": str(self.profile_dir),
            "assumed_link_bps": self.assumed_link_bps,
        }


def load_config(path: Path | None = None) -> Config:
    cfg = Config()
    chosen = path
    if chosen is None:
        env = os.environ.get("EIT_CONFIG")
        if env:
            chosen = Path(env)
        else:
            for candidate in DEFAULT_PATHS:
                if candidate.is_file():
                    chosen = candidate
                    break
    if chosen is not None and chosen.is_file():
        data = json.loads(chosen.read_text(encoding="utf-8"))
        cfg = Config.from_dict(data)
    cfg.lan = os.environ.get("EIT_LAN", cfg.lan)
    cfg.wan = os.environ.get("EIT_WAN", cfg.wan)
    return cfg
