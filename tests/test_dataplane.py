import unittest

from eit.dataplane import DataPlane, build_netem_args
from eit.models import FaultSpec
from eit.runner import RecordingRunner


class TestBuildNetem(unittest.TestCase):
    def test_none_for_empty(self):
        self.assertIsNone(build_netem_args(FaultSpec()))

    def test_delay(self):
        args = build_netem_args(FaultSpec(delay_ms=100))
        self.assertEqual(args[:3], ["netem", "delay", "100ms"])
        self.assertIn("limit", args)

    def test_delay_jitter_loss_rate(self):
        spec = FaultSpec(delay_ms=100, jitter_ms=20, loss_pct=1, rate="10mbit")
        args = build_netem_args(spec)
        self.assertEqual(
            args[:8],
            ["netem", "delay", "100ms", "20ms", "loss", "1%", "rate", "10mbit"],
        )

    def test_limit_grows_with_delay(self):
        small = build_netem_args(FaultSpec(delay_ms=10))
        large = build_netem_args(FaultSpec(delay_ms=500))
        small_limit = int(small[small.index("limit") + 1])
        large_limit = int(large[large.index("limit") + 1])
        self.assertGreater(large_limit, small_limit)
        self.assertGreaterEqual(small_limit, 10_000)


class TestDataPlaneCommands(unittest.TestCase):
    def setUp(self):
        self.runner = RecordingRunner()
        self.plane = DataPlane("eit-lan", "eit-wan", runner=self.runner)

    def _ops(self):
        return [" ".join(cmd) for cmd in self.runner.commands]

    def test_loss_both_directions(self):
        self.plane.apply(FaultSpec(loss_pct=5, duration_s=30))
        ops = self._ops()
        replaces = [o for o in ops if o.startswith("tc qdisc replace")]
        self.assertEqual(len(replaces), 2)
        self.assertTrue(any("dev eit-lan" in o and "loss 5%" in o for o in replaces))
        self.assertTrue(any("dev eit-wan" in o and "loss 5%" in o for o in replaces))

    def test_unidirectional_to_uut(self):
        self.plane.apply(FaultSpec(delay_ms=50, direction="to_uut"))
        replaces = [o for o in self._ops() if o.startswith("tc qdisc replace")]
        self.assertEqual(len(replaces), 1)
        self.assertIn("dev eit-wan", replaces[0])
        self.assertNotIn("dev eit-lan root netem", " ".join(replaces))

    def test_link_down_wan(self):
        self.plane.apply(FaultSpec(link_down="wan"))
        self.assertIn("ip link set dev eit-wan down", self._ops())
        self.assertNotIn("ip link set dev eit-lan down", self._ops())

    def test_phy_speed(self):
        self.plane.apply(FaultSpec(phy_speed=100, phy_side="both"))
        ops = self._ops()
        self.assertTrue(any(o.startswith("ethtool -s eit-lan speed 100") for o in ops))
        self.assertTrue(any(o.startswith("ethtool -s eit-wan speed 100") for o in ops))

    def test_clear_restores(self):
        self.plane.apply(FaultSpec(loss_pct=1, link_down="lan"))
        self.runner.commands.clear()
        self.plane.clear()
        ops = self._ops()
        self.assertTrue(any("tc qdisc del dev eit-lan root" in o for o in ops))
        self.assertTrue(any("ip link set dev eit-lan up" in o for o in ops))
        self.assertTrue(any("ethtool -s eit-lan autoneg on" in o for o in ops))

    def test_apply_replaces_previous(self):
        self.plane.apply(FaultSpec(loss_pct=1))
        self.runner.commands.clear()
        self.plane.apply(FaultSpec(delay_ms=20))
        ops = self._ops()
        self.assertTrue(any("tc qdisc del" in o for o in ops))
        self.assertTrue(any("delay 20ms" in o for o in ops))
        self.assertFalse(any("loss 1%" in o for o in ops))

    def test_prepare_disables_offloads(self):
        self.plane.prepare()
        ops = self._ops()
        self.assertTrue(any(o.startswith("ethtool -K eit-lan") and "tso off" in o for o in ops))
        self.assertTrue(any("set-eee eit-lan eee off" in o for o in ops))


if __name__ == "__main__":
    unittest.main()
