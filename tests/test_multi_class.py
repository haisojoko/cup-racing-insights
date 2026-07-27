import unittest

import duckdb

from cup_racing_insights.detectors.splits import detect_multi_class_split


class MultiClassSplitTests(unittest.TestCase):
    def make_connection(self):
        con = duckdb.connect(":memory:")
        con.execute(
            """
            CREATE TABLE race_results (
                season_id VARCHAR,
                driver VARCHAR,
                position INTEGER,
                points INTEGER,
                dns BOOLEAN
            );
            CREATE TABLE driver_classes (
                season_id VARCHAR,
                driver VARCHAR,
                car_class VARCHAR,
                championship VARCHAR
            );
            """
        )
        return con

    def seed_s14(self, con):
        """S14 shape: GT3 sweeps the front, Street trails, a title in each."""
        con.executemany(
            "INSERT INTO driver_classes VALUES (?, ?, ?, ?)",
            [
                ("S14", "Josie", "GT3", "split"),
                ("S14", "Lee", "GT3", "split"),
                ("S14", "James", "GT3", "split"),
                ("S14", "Toby", "Street", "split"),
                ("S14", "Joyce", "Street", "split"),
            ],
        )
        rows = []
        for i in range(6):
            rows.append(("S14", "Josie", 1, 32, False))
            rows.append(("S14", "Toby", 10, 30, False))  # class winner, 10th overall
        con.executemany("INSERT INTO race_results VALUES (?, ?, ?, ?, ?)", rows)

    def test_reports_class_and_rival_class(self):
        con = self.make_connection()
        self.seed_s14(con)

        insights = detect_multi_class_split(con, "Toby")
        self.assertEqual(len(insights), 1)
        p = insights[0].payload
        self.assertEqual(p["car_class"], "Street")
        self.assertEqual(p["rival_class"], "GT3")
        self.assertEqual(p["class_size"], 2)
        self.assertEqual(p["rival_class_size"], 3)
        self.assertEqual(p["championship"], "split")

    def test_split_season_positions_are_labelled_as_class_positions(self):
        # The archive stores whatever decided the championship. On a split
        # season that is already the class position, so the payload must say so
        # rather than let a consumer read it as an overall result.
        con = self.make_connection()
        self.seed_s14(con)

        p = detect_multi_class_split(con, "Toby")[0].payload
        self.assertEqual(p["position_basis"], "class")
        self.assertEqual(p["avg_finish"], 10.0)
        self.assertEqual(p["wins"], 0)
        self.assertEqual(p["starts"], 6)

    def test_silent_on_a_single_class_season(self):
        con = self.make_connection()
        con.executemany(
            "INSERT INTO driver_classes VALUES (?, ?, ?, ?)",
            [("S20", "Josie", "GT3", "combined")],
        )
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?)",
            [("S20", "Josie", 1, 32, False)] * 6,
        )
        self.assertEqual(detect_multi_class_split(con, "Josie"), [])

    def test_silent_when_no_classes_are_declared(self):
        con = self.make_connection()
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?)",
            [("S20", "Josie", 1, 32, False)] * 6,
        )
        self.assertEqual(detect_multi_class_split(con, "Josie"), [])

    def test_ignores_a_cameo_below_the_start_threshold(self):
        con = self.make_connection()
        self.seed_s14(con)
        con.executemany(
            "INSERT INTO driver_classes VALUES (?, ?, ?, ?)",
            [("S14", "Nick", "Street", "split")],
        )
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?)",
            [("S14", "Nick", 12, 10, False)] * 2,
        )
        self.assertEqual(detect_multi_class_split(con, "Nick"), [])

    def test_dns_and_unclassified_races_do_not_count_as_starts(self):
        con = self.make_connection()
        self.seed_s14(con)
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?)",
            [("S14", "Josie", None, 0, True)] * 3,
        )
        p = detect_multi_class_split(con, "Josie")[0].payload
        self.assertEqual(p["starts"], 6)

    def test_combined_championship_is_labelled_differently(self):
        con = self.make_connection()
        con.executemany(
            "INSERT INTO driver_classes VALUES (?, ?, ?, ?)",
            [
                ("S18a", "Josie", "Hypercar", "combined"),
                ("S18a", "James", "GT3", "combined"),
                ("S18a", "Lee", "GT3", "combined"),
            ],
        )
        con.executemany(
            "INSERT INTO race_results VALUES (?, ?, ?, ?, ?)",
            [("S18a", "Josie", 1, 32, False)] * 6,
        )
        insight = detect_multi_class_split(con, "Josie")[0]
        self.assertEqual(insight.payload["championship"], "combined")
        self.assertEqual(insight.payload["position_basis"], "overall")
        self.assertIn("one championship", insight.body)


if __name__ == "__main__":
    unittest.main()
