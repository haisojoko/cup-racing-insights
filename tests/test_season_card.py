import unittest

import duckdb

from cup_racing_insights.render.infographic import render_season_html
from cup_racing_insights.render.season import build_season_summary


class SeasonCardTests(unittest.TestCase):
    def make_connection(self):
        con = duckdb.connect(":memory:")
        con.execute(
            """
            CREATE TABLE seasons (
                season_id VARCHAR,
                season_num INTEGER,
                type VARCHAR,
                car VARCHAR,
                wdc VARCHAR
            );
            CREATE TABLE race_results (
                season_id VARCHAR,
                venue_order INTEGER,
                race_num INTEGER,
                driver VARCHAR,
                position INTEGER,
                points INTEGER,
                is_pole BOOLEAN,
                is_fastest_lap BOOLEAN,
                dns BOOLEAN
            );
            CREATE TABLE weighted_scores (
                driver VARCHAR,
                season_id VARCHAR,
                win_pct DOUBLE,
                pod_pct DOUBLE,
                top5_pct DOUBLE,
                fl_pct DOUBLE,
                pole_pct DOUBLE,
                pts_rate DOUBLE
            );
            """
        )
        return con

    def test_summary_uses_weighted_score_rates_for_rate_tiles(self):
        con = self.make_connection()
        con.execute(
            "INSERT INTO seasons VALUES (?, ?, ?, ?, ?)",
            ["S21", 21, "Formula", "Formula Renault", "Josie"],
        )
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("S21", 1, 1, "Josie", 1, 32, True, False, False),
                ("S21", 1, 2, "Josie", 2, 25, False, True, False),
                ("S21", 1, 3, "Josie", 4, 20, False, False, False),
                ("S21", 1, 4, "Josie", 8, 0, False, False, False),
            ],
        )
        con.execute(
            "INSERT INTO weighted_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ["Josie", "S21", 0.375, 0.938, 1.0, 0.063, 0.0, 0.799],
        )

        summary = build_season_summary(con, "Josie", "S21")

        self.assertIsNotNone(summary)
        assert summary is not None
        self.assertAlmostEqual(summary.win_rate, 0.375)
        self.assertAlmostEqual(summary.podium_rate, 0.938)
        self.assertAlmostEqual(summary.top5_rate, 1.0)
        self.assertAlmostEqual(summary.points_rate or 0.0, 0.799)
        self.assertEqual(
            [tile["label"] for tile in summary.rate_tiles],
            ["Points rate", "Win rate", "Podium rate", "Top-5 rate"],
        )
        self.assertEqual(
            [tile["value"] for tile in summary.rate_tiles],
            ["79.9%", "37.5%", "93.8%", "100.0%"],
        )

        html = render_season_html(summary)
        self.assertIn("Points rate", html)
        self.assertIn("79.9%", html)


if __name__ == "__main__":
    unittest.main()
