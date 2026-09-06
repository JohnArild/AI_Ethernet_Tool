import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from eit.config import Config
from eit.daemon import Session, make_handler
from eit.dataplane import DataPlane
from eit.models import FaultError, FaultSpec
from eit.runner import RecordingRunner


class TestSession(unittest.TestCase):
    def setUp(self):
        self.runner = RecordingRunner()
        self.plane = DataPlane("lan0", "wan0", runner=self.runner)
        self.config = Config(lan="lan0", wan="wan0", default_duration_s=60, max_duration_s=120)
        self.session = Session(self.plane, self.config)

    def tearDown(self):
        self.session.clear()

    def test_apply_and_status(self):
        spec = FaultSpec(loss_pct=2, duration_s=30)
        payload = self.session.apply(spec)
        self.assertEqual(payload["state"], "impaired")
        self.assertEqual(payload["applied"]["loss_pct"], 2)
        self.assertIsNotNone(payload["expires_at"])

    def test_clear(self):
        self.session.apply(FaultSpec(delay_ms=10, duration_s=30))
        payload = self.session.clear()
        self.assertEqual(payload["state"], "pass-through")

    def test_duration_cap(self):
        with self.assertRaises(FaultError):
            self.session.apply(FaultSpec(loss_pct=1, duration_s=10_000))

    def test_auto_clear(self):
        self.session.apply(FaultSpec(loss_pct=1, duration_s=1))
        time.sleep(1.4)
        self.assertEqual(self.session.status()["state"], "pass-through")


class TestHTTP(unittest.TestCase):
    def setUp(self):
        self.runner = RecordingRunner()
        plane = DataPlane("lan0", "wan0", runner=self.runner)
        self.config = Config(lan="lan0", wan="wan0")
        self.session = Session(plane, self.config)
        handler = make_handler(self.session, self.config)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.session.clear()
        self.server.shutdown()
        self.server.server_close()

    def _json(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"} if body is not None else {},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())

    def test_status_pass_through(self):
        payload = self._json("GET", "/v1/status")
        self.assertEqual(payload["state"], "pass-through")

    def test_apply_profile(self):
        payload = self._json("POST", "/v1/faults", {"profile": "loss-1pct", "duration_s": 20})
        self.assertEqual(payload["state"], "impaired")
        self.assertEqual(payload["applied"]["loss_pct"], 1)
        ops = [" ".join(c) for c in self.runner.commands]
        self.assertTrue(any("loss 1%" in o for o in ops))

    def test_clear_http(self):
        self._json("POST", "/v1/faults", {"delay_ms": 25, "duration_s": 20})
        payload = self._json("POST", "/v1/clear", {})
        self.assertEqual(payload["state"], "pass-through")

    def test_bad_json(self):
        req = urllib.request.Request(
            self.base + "/v1/faults",
            data=b"not-json",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()

    def test_profiles_list(self):
        payload = self._json("GET", "/v1/profiles")
        self.assertIn("delay-100ms", payload["profiles"])


if __name__ == "__main__":
    unittest.main()
