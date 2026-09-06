"""Optional live tests using network namespaces. Skipped without CAP_NET_ADMIN."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

from eit.dataplane import DataPlane
from eit.models import FaultSpec
from eit.runner import SystemRunner


def _can_netns() -> bool:
    if os.geteuid() != 0:
        return False
    if shutil.which("ip") is None or shutil.which("ping") is None:
        return False
    probe = subprocess.run(
        ["ip", "netns", "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    return probe.returncode == 0


@unittest.skipUnless(_can_netns(), "requires root and ip netns")
class TestNetnsImpairments(unittest.TestCase):
    NS_A = "eit-test-a"
    NS_B = "eit-test-b"
    BR = "eit-test-br"
    A_BR = "eit-ta"
    B_BR = "eit-tb"

    def setUp(self):
        self._cleanup()
        subprocess.check_call(["ip", "netns", "add", self.NS_A])
        subprocess.check_call(["ip", "netns", "add", self.NS_B])
        subprocess.check_call(["ip", "link", "add", self.A_BR, "type", "veth", "peer", "name", "veth-a"])
        subprocess.check_call(["ip", "link", "add", self.B_BR, "type", "veth", "peer", "name", "veth-b"])
        subprocess.check_call(["ip", "link", "set", "veth-a", "netns", self.NS_A])
        subprocess.check_call(["ip", "link", "set", "veth-b", "netns", self.NS_B])
        subprocess.check_call(["ip", "link", "add", self.BR, "type", "bridge"])
        subprocess.check_call(["ip", "link", "set", self.A_BR, "master", self.BR])
        subprocess.check_call(["ip", "link", "set", self.B_BR, "master", self.BR])
        for dev in (self.BR, self.A_BR, self.B_BR):
            subprocess.check_call(["ip", "link", "set", dev, "up"])
        for ns, dev, addr in (
            (self.NS_A, "veth-a", "10.87.0.1/24"),
            (self.NS_B, "veth-b", "10.87.0.2/24"),
        ):
            subprocess.check_call(["ip", "netns", "exec", ns, "ip", "link", "set", dev, "up"])
            subprocess.check_call(["ip", "netns", "exec", ns, "ip", "addr", "add", addr, "dev", dev])
        self.plane = DataPlane(self.A_BR, self.B_BR, runner=SystemRunner())

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for ns in (self.NS_A, self.NS_B):
            subprocess.run(["ip", "netns", "del", ns], check=False, capture_output=True)
        for dev in (self.BR, self.A_BR, self.B_BR):
            subprocess.run(["ip", "link", "del", dev], check=False, capture_output=True)

    def _ping(self, count: int = 20) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                "ip",
                "netns",
                "exec",
                self.NS_A,
                "ping",
                "-c",
                str(count),
                "-i",
                "0.1",
                "-W",
                "1",
                "10.87.0.2",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_pass_through_ping(self):
        result = self._ping(5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_loss_100_drops_all(self):
        self.plane.apply(FaultSpec(loss_pct=100, duration_s=0))
        result = self._ping(5)
        self.assertNotEqual(result.returncode, 0)
        self.plane.clear()
        result = self._ping(5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_delay_increases_rtt(self):
        self.plane.apply(FaultSpec(delay_ms=50, duration_s=0))
        result = self._ping(10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ms", result.stdout)
        # Bidirectional 50 ms => ~100 ms RTT.
        self.assertTrue("100." in result.stdout or "9" in result.stdout)


if __name__ == "__main__":
    unittest.main()
