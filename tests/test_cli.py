import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from eit.cli import flags_to_dict, main
from eit.models import FaultError
from eit.profiles import merge_profile


class TestCliFlags(unittest.TestCase):
    def test_apply_help(self):
        buf = io.StringIO()
        with redirect_stdout(buf), self.assertRaises(SystemExit) as ctx:
            main(["apply", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("--loss-pct", buf.getvalue())

    def test_flags_to_dict(self):
        from eit.cli import build_parser

        args = build_parser().parse_args(
            ["apply", "--delay-ms", "50", "--loss-pct", "1", "--duration", "15"]
        )
        data = flags_to_dict(args)
        self.assertEqual(data["delay_ms"], 50)
        self.assertEqual(data["loss_pct"], 1)
        self.assertEqual(data["duration_s"], 15)

    def test_merge_from_flags(self):
        spec = merge_profile({"profile": "loss-1pct", "duration_s": 5})
        self.assertEqual(spec.loss_pct, 1)
        self.assertEqual(spec.duration_s, 5)

    def test_apply_requires_params(self):
        from argparse import Namespace

        args = Namespace(
            profile=None,
            delay_ms=None,
            jitter_ms=None,
            loss_pct=None,
            loss_correlation=None,
            rate=None,
            duplicate_pct=None,
            reorder_pct=None,
            corrupt_pct=None,
            direction=None,
            link_down=None,
            flap_ms=None,
            phy_speed=None,
            phy_side=None,
            duration=None,
        )
        from eit.cli import spec_from_args
        from pathlib import Path

        with self.assertRaises(FaultError):
            spec_from_args(args, Path("/nonexistent"))

    def test_direct_clear(self):
        from eit.dataplane import DataPlane

        with mock.patch("eit.cli.DataPlane") as plane_cls:
            instance = mock.Mock(spec=DataPlane)
            plane_cls.return_value = instance
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--direct", "clear"])
            self.assertEqual(rc, 0)
            instance.clear.assert_called_once()

    def test_direct_apply_profile(self):
        from eit.dataplane import DataPlane

        with mock.patch("eit.cli.DataPlane") as plane_cls:
            instance = mock.Mock(spec=DataPlane)
            instance.status.return_value = {"lan": {}, "wan": {}}
            plane_cls.return_value = instance
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--direct", "apply", "--profile", "loss-1pct"])
            self.assertEqual(rc, 0)
            instance.apply.assert_called_once()
            spec = instance.apply.call_args[0][0]
            self.assertEqual(spec.loss_pct, 1)

    def test_http_status(self):
        payload = {"state": "pass-through", "applied": None}
        with mock.patch("eit.cli.http_json", return_value=payload) as http:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["status"])
            self.assertEqual(rc, 0)
            http.assert_called_once()
            self.assertIn("pass-through", buf.getvalue())
            printed = json.loads(buf.getvalue())
            self.assertEqual(printed["state"], "pass-through")


if __name__ == "__main__":
    unittest.main()
