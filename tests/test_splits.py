import unittest

import duckdb

from cup_racing_insights.detectors.splits import detect_specialist_car


class SpecialistCarTests(unittest.TestCase):
    def make_connection(self):
        con = duckdb.connect(":memory:")
        con.execute(
            """
            CREATE TABLE seasons (
                season_id VARCHAR,
                car VARCHAR
            );
            CREATE TABLE race_results (
                season_id VARCHAR,
                driver VARCHAR,
                car VARCHAR,
                position INTEGER,
                points INTEGER,
                dns BOOLEAN
            );
            """
        )
        return con

    def test_uses_season_car_when_race_car_is_blank(self):
        con = self.make_connection()
        con.executemany(
            "INSERT INTO seasons VALUES (?, ?)",
            [
                ("S1", "F1 1986 (single car spec)"),
                ("S2", "Multi-Class"),
            ],
        )
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("S1", "Josie", "", 1, 32, False),
                ("S1", "Josie", "", 1, 31, False),
                ("S1", "Josie", "", 2, 25, False),
                ("S2", "Josie", "GT3 911", 2, 25, False),
                ("S2", "Josie", "GT3 911", 3, 22, False),
                ("S2", "Josie", "GT3 911", 4, 20, False),
            ],
        )

        insights = detect_specialist_car(con, "Josie")

        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0].payload["car"], "F1 1986 (single car spec)")
        self.assertEqual(insights[0].payload["starts"], 3)
        self.assertAlmostEqual(insights[0].payload["points_per_start"], 88 / 3)

    def test_groups_car_variants_by_case_insensitive_name(self):
        con = self.make_connection()
        con.executemany(
            "INSERT INTO seasons VALUES (?, ?)",
            [
                ("S18a", "WEC"),
                ("S18b", "WEC"),
            ],
        )
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?, ?)",
            [
                ("S18a", "Josie", "Hyper 499P", 1, 32, False),
                ("S18a", "Josie", "Hyper 499P", 2, 25, False),
                ("S18a", "Josie", "Hyper 499P", 3, 22, False),
                ("S18b", "Josie", "Hyper 499p", 1, 31, False),
                ("S18b", "Josie", "Hyper 499p", 2, 25, False),
                ("S18b", "Josie", "Hyper 499p", 4, 20, False),
            ],
        )

        insights = detect_specialist_car(con, "Josie")

        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0].payload["car"], "Hyper 499P")
        self.assertEqual(insights[0].payload["starts"], 6)
        self.assertEqual(insights[0].payload["points"], 155)


if __name__ == "__main__":
    unittest.main()
