"""Tests for the JSON race-dataset loader and the pace/qualifying detectors."""

import json

import duckdb

from cup_racing_insights import races
from cup_racing_insights.detectors import pace


# ---------------------------------------------------------------------------
# Loader — pace stats + extraction
# ---------------------------------------------------------------------------

def test_pace_stats_drops_lap1_and_outliers():
    # Lap 1 (standing start) is dropped; a pit/off lap >120% of median is too.
    laps = [99000, 90000, 90200, 90100, 130000]
    stats = races._pace_stats(laps)
    assert stats["laps_used"] == 3          # 99000 (lap1) and 130000 (outlier) removed
    assert stats["best_ms"] == 90000
    assert stats["worst_ms"] == 90200
    assert 0 <= stats["cv_pct"] < 1         # very consistent → tiny CV


def test_pace_stats_none_when_no_valid_laps():
    assert races._pace_stats([0, -5, 999999999]) is None


_SEASON = {
    "season": "S99",
    "events": [
        {
            "venue": "Testring", "venueOrder": 1,
            "qualifying": {"qual1": {"times": {
                "A": {"bestMs": 90000}, "B": {"bestMs": 90500}, "C": {"bestMs": 99000},
            }}},
            "races": {
                "1": {
                    "laps": {
                        "A": [95000, 90000, 90100, 90050],
                        "B": [96000, 91000, 91200],
                        "C": [97000, 120000],
                    },
                    "overtakes": [
                        {"lap": 1, "driver": "A", "passed": "B"},
                        {"lap": 2, "driver": "B", "passed": "C"},
                    ],
                    "contacts": [{"driver1": "A", "driver2": "C"}],
                }
            },
        }
    ],
}


def test_extract_rows():
    rows = races._extract(_SEASON)
    assert len(rows["qual"]) == 3
    assert len(rows["pace"]) == 3          # A, B, C each get a pace row
    # Overtakes: A made 1, B made 1 + suffered 1, C suffered 1
    ot = {r[4]: (r[5], r[6]) for r in rows["overtakes"]}
    assert ot["A"] == (1, 0)
    assert ot["B"] == (1, 1)
    assert ot["C"] == (0, 1)
    contacts = {r[4]: r[5] for r in rows["contacts"]}
    assert contacts == {"A": 1, "C": 1}


def test_load_races_integration(tmp_path):
    seasons_dir = tmp_path / "seasons"
    seasons_dir.mkdir()
    (seasons_dir / "S99.json").write_text(json.dumps(_SEASON), encoding="utf-8")
    (tmp_path / "index.json").write_text(
        json.dumps({"seasons": {"S99": {"file": "seasons/S99.json"}}}), encoding="utf-8"
    )
    con = duckdb.connect(":memory:")
    counts = races.load_races(con, tmp_path)
    assert counts["race_pace"] == 3
    assert counts["qual_times"] == 3
    assert con.execute("SELECT SUM(made) FROM race_overtakes").fetchone()[0] == 2


def test_load_races_missing_dir_is_empty(tmp_path):
    con = duckdb.connect(":memory:")
    counts = races.load_races(con, tmp_path / "nope")
    assert counts == {"race_pace": 0, "qual_times": 0, "race_overtakes": 0, "race_contacts": 0}
    # Tables still exist (empty), so detectors can query them safely.
    assert con.execute("SELECT COUNT(*) FROM race_pace").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detector_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute(races.RACES_SCHEMA_SQL)
    return con


def _pace(con, season, vo, rn, driver, avg, best, laps=4):
    con.execute(
        "INSERT INTO race_pace VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [season, "V", vo, rn, driver, avg, best, best + 500, 100.0, 100.0 / avg * 100, laps],
    )


def test_pole_margin_picks_widest_and_ignores_garbage(_detector=None):
    con = _detector_db()
    # Real pole margin 0.4s; plus a garbage session where P2 only did an outlap.
    con.executemany(
        "INSERT INTO qual_times VALUES (?,?,?,?,?,?)",
        [
            ("S1", "Brands", 1, "qual1", "X", 90000.0),
            ("S1", "Brands", 1, "qual1", "Y", 90400.0),
            ("S1", "Brands", 1, "qual1", "Z", 91000.0),
            # Garbage: X on pole, everyone else set only a 20s-slower outlap.
            ("S2", "Spa", 1, "qual1", "X", 100000.0),
            ("S2", "Spa", 1, "qual1", "Y", 120000.0),
            ("S2", "Spa", 1, "qual1", "Z", 121000.0),
        ],
    )
    out = pace.detect_pole_margin(con, "X")
    assert len(out) == 1
    assert out[0].payload["gap_s"] == 0.4          # the real one, not the 20s garbage
    assert out[0].payload["season"] == "S1"


def test_dominant_fastest_lap_ignores_one_lap_backmarker():
    con = _detector_db()
    _pace(con, "S1", 1, 1, "X", 90000, 89500, laps=5)   # fastest lap
    _pace(con, "S1", 1, 1, "Y", 90800, 90100, laps=5)   # next best (0.6s back)
    _pace(con, "S1", 1, 1, "W", 91500, 90900, laps=5)   # third, keeps field >= 3
    _pace(con, "S1", 1, 1, "Z", 99000, 98000, laps=1)   # one slow lap — excluded
    out = pace.detect_dominant_fastest_lap(con, "X")
    assert len(out) == 1
    assert out[0].payload["gap_s"] == 0.6              # vs Y, not the backmarker Z
    assert out[0].payload["field"] == 3                # Z excluded from the field


def test_avg_pace_gap_sets_pace_setter_and_follower():
    con = _detector_db()
    for rn in (1, 2, 3):
        _pace(con, "S1", 1, rn, "X", 90000, 89000)     # fastest every race
        _pace(con, "S1", 1, rn, "Y", 90900, 90000)     # ~1% slower every race
    x = pace.detect_avg_pace_gap(con, "X")
    y = pace.detect_avg_pace_gap(con, "Y")
    assert any(i.kind == "pace_setter_season" and i.payload["season"] == "S1" for i in x)
    follower = [i for i in y if i.kind == "pace_gap_to_leader"]
    assert follower and follower[0].payload["pace_rank"] == 2
    assert 0.5 < follower[0].payload["gap_pct"] < 1.5   # ~1%


def test_pace_stats_single_clean_lap_has_null_dev():
    # Two raw laps → lap 1 dropped → one clean lap → no meaningful spread.
    stats = races._pace_stats([99000, 90000])
    assert stats["laps_used"] == 1
    assert stats["stdev_ms"] is None
    assert stats["cv_pct"] is None


def test_pace_setter_participation_guard():
    con = _detector_db()
    # 5-round season. A and C run all 5; B runs only rounds 1-2 but is quickest
    # there. B must NOT be crowned pace-setter (ran < 60% of rounds).
    for rn in (1, 2, 3, 4, 5):
        _pace(con, "S1", 1, rn, "A", 90000, 89000)
        _pace(con, "S1", 1, rn, "C", 90900, 90000)
    for rn in (1, 2):
        _pace(con, "S1", 1, rn, "B", 88000, 87000)
    assert any(i.kind == "pace_setter_season" for i in pace.detect_avg_pace_gap(con, "A"))
    assert pace.detect_avg_pace_gap(con, "B") == []   # excluded, not ranked at all


def test_all_stats_avg_finish_pace_and_overtaken():
    con = _detector_db()
    con.execute(
        "CREATE TABLE race_results (season_id VARCHAR, venue VARCHAR, venue_order INT, "
        "race_num INT, driver VARCHAR, car VARCHAR, position INT, points INT, "
        "is_pole BOOL, is_fastest_lap BOOL, penalty INT, dns BOOL)"
    )
    con.executemany(
        "INSERT INTO race_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [("S1", "V", 1, 1, "X", "c", 2, 25, False, False, 0, False),
         ("S1", "V", 1, 2, "X", "c", 4, 20, False, False, 0, False)],
    )
    for rn in (1, 2):
        _pace(con, "S1", 1, rn, "X", 90000, 89000)
        _pace(con, "S1", 1, rn, "Y", 91000, 90000)
    con.executemany(
        "INSERT INTO race_overtakes VALUES (?,?,?,?,?,?,?)",
        [("S1", "V", 1, 1, "X", 3, 1), ("S1", "V", 1, 2, "X", 2, 2)],
    )
    from cup_racing_insights.render.season import _all_stats
    avg_finish, pace_vs_field, overtaken = _all_stats(con, "X", "S1")
    assert avg_finish == 3.0                      # (2 + 4) / 2
    assert -0.7 < pace_vs_field < -0.4            # ~-0.55% vs 90500 field avg
    assert overtaken == 3                          # 1 + 2 suffered
