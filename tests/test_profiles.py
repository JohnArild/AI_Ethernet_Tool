import json
import tempfile
import unittest
from pathlib import Path

from eit.models import FaultError
from eit.profiles import list_profiles, load_profile, merge_profile


class TestProfiles(unittest.TestCase):
    def test_builtin_loss(self):
        spec = load_profile("loss-1pct")
        self.assertEqual(spec.loss_pct, 1)
        self.assertEqual(spec.direction, "both")

    def test_builtin_bad_wan(self):
        spec = load_profile("bad-wan")
        self.assertEqual(spec.delay_ms, 200)
        self.assertEqual(spec.loss_pct, 2)
        self.assertEqual(spec.rate, "2mbit")

    def test_list_includes_builtins(self):
        names = list_profiles()
        self.assertIn("loss-1pct", names)
        self.assertIn("link-down-wan", names)
        self.assertIn("phy-100", names)

    def test_missing(self):
        with self.assertRaises(FaultError):
            load_profile("does-not-exist")

    def test_overlay(self):
        spec = merge_profile({"profile": "delay-100ms", "loss_pct": 3, "duration_s": 10})
        self.assertEqual(spec.delay_ms, 100)
        self.assertEqual(spec.loss_pct, 3)
        self.assertEqual(spec.duration_s, 10)

    def test_extra_dir_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "loss-1pct.json"
            path.write_text(json.dumps({"loss_pct": 9}), encoding="utf-8")
            spec = load_profile("loss-1pct", extra=Path(tmp))
            self.assertEqual(spec.loss_pct, 9)


if __name__ == "__main__":
    unittest.main()
