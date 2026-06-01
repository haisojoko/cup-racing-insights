import unittest

from cup_racing_insights.parser import parse_position_cell


class PositionCellParserTests(unittest.TestCase):
    def test_dns_keeps_parenthesized_flags(self):
        parsed = parse_position_cell("DNS (P)")

        self.assertIsNone(parsed["position"])
        self.assertTrue(parsed["dns"])
        self.assertTrue(parsed["is_pole"])
        self.assertFalse(parsed["is_fastest_lap"])
        self.assertEqual(parsed["penalty"], 0)

    def test_dns_keeps_fastest_lap_and_penalty_flags(self):
        parsed = parse_position_cell("DNS (FL,-3pen)")

        self.assertIsNone(parsed["position"])
        self.assertTrue(parsed["dns"])
        self.assertFalse(parsed["is_pole"])
        self.assertTrue(parsed["is_fastest_lap"])
        self.assertEqual(parsed["penalty"], 3)


if __name__ == "__main__":
    unittest.main()
