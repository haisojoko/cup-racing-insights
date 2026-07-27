"""Stewards' penalty placements must not be averaged as finishing positions.

S21 Monza R4 records James at P99 — a self-inflicted DNF the stewards let stand
as the penalty rather than reclassifying it to last. It is a real result, so it
counts as a start and keeps its points, but averaging it as a position turned a
season he won 9 of 16 races into an average finish of 7.88.
"""

import duckdb

from cup_racing_insights.detectors.splits import detect_specialist_car
from cup_racing_insights.detectors.venue import detect_best_avg_venue
from cup_racing_insights.models import PENALTY_POSITION_MIN


def make_connection():
    con = duckdb.connect(":memory:")
    con.execute(
        """
        CREATE TABLE seasons (season_id VARCHAR, car VARCHAR);
        CREATE TABLE race_results (
            season_id VARCHAR, venue VARCHAR, driver VARCHAR, car VARCHAR,
            position INTEGER, points INTEGER, dns BOOLEAN
        );
        """
    )
    con.execute("INSERT INTO seasons VALUES ('S21', 'Caterham')")
    rows = [
        ("S21", "Monza", "James", "Caterham 420R", 1, 30, False),
        ("S21", "Monza", "James", "Caterham 420R", 2, 25, False),
        ("S21", "Monza", "James", "Caterham 420R", 3, 22, False),
        ("S21", "Monza", "James", "Caterham 420R", 99, 1, False),
    ]
    con.executemany("INSERT INTO race_results VALUES (?,?,?,?,?,?,?)", rows)
    return con


def test_threshold_sits_clear_of_any_real_field():
    # The largest field the league has ever run is 19.
    assert PENALTY_POSITION_MIN > 19


def test_venue_average_ignores_the_penalty_placement():
    con = make_connection()
    insights = detect_best_avg_venue(con, "James")
    assert insights, "expected a best-average-venue insight"
    p = insights[0].payload
    # (1 + 2 + 3) / 3 = 2.0, not (1 + 2 + 3 + 99) / 4 = 26.25
    assert round(p["avg_position"], 2) == 2.0
    assert p["starts"] == 4  # the penalty race is still a start


def test_specialist_car_average_ignores_it_but_keeps_points_and_starts():
    con = make_connection()
    insights = detect_specialist_car(con, "James")
    assert insights, "expected a specialist-car insight"
    p = insights[0].payload
    assert round(p["avg_position"], 2) == 2.0
    assert p["starts"] == 4
    assert p["points"] == 78  # the 1 point from the penalty race survives
    assert p["wins"] == 1
