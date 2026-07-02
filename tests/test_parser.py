import unittest

from cup_racing_insights.parser import (
    ParsedDataset,
    _parse_weighted_scores,
    parse_position_cell,
)


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


class WeightedScoreHeaderTests(unittest.TestCase):
    """Columns must be resolved by header name, so inserting extra columns (the data
    file grew 'Field' and 'Pen.') doesn't shift participation/WDC/WCC parsing."""

    def _parse(self, header: str, row: str):
        lines = [
            "## All-Time Weighted Score Rankings",
            "",
            header,
            "| " + " | ".join(["---"] * header.count("|")) + " |",
            row,
        ]
        ds = ParsedDataset()
        _parse_weighted_scores(lines, ds)
        return ds.weighted_scores

    def test_new_layout_with_field_and_penalty_columns(self):
        rows = self._parse(
            "| Rank | Driver | Season | W.Score | Win% | Pod% | Top5% | Pts/Race | "
            "FL% | Pole% | PtsRate | Field | Pen. | Part. | WDC | WCC |",
            "| 1 | Toby | S14 | 1.0265 | 93.8% | 100.0% | 100.0% | 31.7 | 100.0% | "
            "100.0% | 99.0% | 18 | 0 | 100.0% | Yes | Yes |",
        )
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertAlmostEqual(r.weighted_score, 1.0265)
        self.assertAlmostEqual(r.participation, 1.0)  # NOT the field size (18)
        self.assertTrue(r.has_wdc)
        self.assertTrue(r.has_wcc)

    def test_old_layout_still_parses(self):
        rows = self._parse(
            "| Rank | Driver | Season | W.Score | Win% | Pod% | Top5% | Pts/Race | "
            "FL% | Pole% | PtsRate | Part. | WDC | WCC |",
            "| 5 | Lee | S18b | 0.653 | 40% | 60% | 80% | 20.0 | 10% | 5% | 55% | "
            "90.0% | Yes | No |",
        )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0].participation, 0.9)
        self.assertTrue(rows[0].has_wdc)
        self.assertFalse(rows[0].has_wcc)


if __name__ == "__main__":
    unittest.main()
