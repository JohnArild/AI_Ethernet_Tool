import unittest

from eit.models import FaultError, FaultSpec, parse_rate_bps, rate_to_tc


class TestFaultSpec(unittest.TestCase):
    def test_pass_through(self):
        spec = FaultSpec()
        self.assertTrue(spec.is_pass_through())
        self.assertFalse(spec.has_netem())

    def test_loss_is_netem(self):
        spec = FaultSpec(loss_pct=1)
        spec.validate()
        self.assertTrue(spec.has_netem())
        self.assertFalse(spec.is_pass_through())

    def test_invalid_direction(self):
        with self.assertRaises(FaultError):
            FaultSpec(direction="sideways").validate()

    def test_jitter_requires_delay(self):
        with self.assertRaises(FaultError):
            FaultSpec(jitter_ms=10).validate()

    def test_flap_requires_link_down(self):
        with self.assertRaises(FaultError):
            FaultSpec(flap_ms=100).validate()

    def test_phy_speed(self):
        FaultSpec(phy_speed=100).validate()
        with self.assertRaises(FaultError):
            FaultSpec(phy_speed=2500).validate()

    def test_loss_bounds(self):
        with self.assertRaises(FaultError):
            FaultSpec(loss_pct=101).validate()

    def test_from_dict_rejects_unknown(self):
        with self.assertRaises(FaultError):
            FaultSpec.from_dict({"loss_pct": 1, "foo": 1})

    def test_roundtrip(self):
        spec = FaultSpec(delay_ms=50, loss_pct=1, rate="10mbit", direction="to_uut")
        spec.validate()
        again = FaultSpec.from_dict(spec.to_dict())
        self.assertEqual(again.delay_ms, 50)
        self.assertEqual(again.rate, "10mbit")


class TestRate(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_rate_bps("10mbit"), 10_000_000)
        self.assertEqual(parse_rate_bps("10Mbps"), 10_000_000)
        self.assertEqual(parse_rate_bps("1gbit"), 1_000_000_000)
        self.assertEqual(parse_rate_bps("100kbit"), 100_000)

    def test_tc(self):
        self.assertEqual(rate_to_tc("10Mbps"), "10mbit")
        self.assertEqual(rate_to_tc("1gbit"), "1gbit")

    def test_bad_rate(self):
        with self.assertRaises(FaultError):
            parse_rate_bps("fast")


if __name__ == "__main__":
    unittest.main()
