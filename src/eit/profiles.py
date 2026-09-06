"""Named fault profiles stored as JSON."""

from __future__ import annotations

import json
from pathlib import Path

from eit.models import FaultError, FaultSpec

BUILTIN_DIR = Path(__file__).resolve().parent / "builtin_profiles"


def profile_paths(extra: Path | None = None) -> list[Path]:
    dirs = []
    if extra is not None:
        dirs.append(extra)
    dirs.append(Path("/etc/eit/profiles"))
    dirs.append(BUILTIN_DIR)
    return dirs


def find_profile(name: str, extra: Path | None = None) -> Path:
    filename = name if name.endswith(".json") else f"{name}.json"
    for directory in profile_paths(extra):
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    raise FaultError(f"profile not found: {name}")


def load_profile(name: str, extra: Path | None = None) -> FaultSpec:
    path = find_profile(name, extra)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise FaultError(f"profile {name} is not a JSON object")
    return FaultSpec.from_dict(data)


def list_profiles(extra: Path | None = None) -> list[str]:
    names: set[str] = set()
    for directory in profile_paths(extra):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            names.add(path.stem)
    return sorted(names)


def merge_profile(data: dict, extra: Path | None = None) -> FaultSpec:
    """Load optional profile then overlay explicit fields."""
    data = dict(data)
    name = data.pop("profile", None)
    if name:
        base = load_profile(str(name), extra).to_dict()
        for key, value in data.items():
            if value is not None:
                base[key] = value
        data = base
    return FaultSpec.from_dict(data)
