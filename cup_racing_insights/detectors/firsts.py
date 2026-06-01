"""Firsts and lasts — the chronological bookends of a driver's career.

The "first" detectors anchor origin-story content (first pole, first win).
The "last" detectors give currency: when did this driver most recently do
something noteworthy? Useful for active-season social posts.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def _first_of(
    con: DuckDBPyConnection, driver: str, predicate_sql: str
) -> tuple | None:
    return con.execute(
        f"""
        SELECT r.season_id, r.venue, r.race_num, r.position, r.points,
               r.is_pole, r.is_fastest_lap
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND ({predicate_sql})
      ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
         LIMIT 1
        """,
        [driver],
    ).fetchone()


def _last_of(
    con: DuckDBPyConnection, driver: str, predicate_sql: str
) -> tuple | None:
    return con.execute(
        f"""
        SELECT r.season_id, r.venue, r.race_num, r.position, r.points,
               r.is_pole, r.is_fastest_lap
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND ({predicate_sql})
      ORDER BY s.season_num DESC, s.season_sub DESC, r.venue_order DESC, r.race_num DESC
         LIMIT 1
        """,
        [driver],
    ).fetchone()


def detect_career_firsts(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """First-ever win, podium, pole and fastest lap."""
    out: list[Insight] = []

    specs = [
        ("first_win", "position = 1", "win", "career"),
        ("first_podium", "position BETWEEN 1 AND 3", "podium", "career"),
        ("first_pole", "is_pole", "pole position", "qualifying"),
        ("first_fl", "is_fastest_lap", "fastest lap", "pace"),
    ]
    for kind, predicate, label, _flavour in specs:
        row = _first_of(con, driver, predicate)
        if not row:
            continue
        season_id, venue, race_num, position, points, _pole, _fl = row
        out.append(
            Insight(
                category=InsightCategory.FIRST_ONLY_LAST,
                kind=kind,
                subject=driver,
                headline=(
                    f"First career {label}: {venue} R{int(race_num)} ({season_id})"
                ),
                payload={
                    "season": season_id,
                    "venue": venue,
                    "race": int(race_num),
                    "position": int(position) if position is not None else None,
                    "points": int(points) if points is not None else 0,
                    "label": label,
                },
                sources=[season_id],
            )
        )
    return out


def detect_career_lasts(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """Most recent win, podium and pole. Useful currency for in-season posts.

    We only surface the "last" if it isn't the same race as the "first"
    (i.e. driver has more than one such result).
    """
    out: list[Insight] = []

    specs = [
        ("most_recent_win", "position = 1", "win"),
        ("most_recent_podium", "position BETWEEN 1 AND 3", "podium"),
        ("most_recent_pole", "is_pole", "pole position"),
    ]
    for kind, predicate, label in specs:
        first = _first_of(con, driver, predicate)
        last = _last_of(con, driver, predicate)
        if not last:
            continue
        # Skip if there is only a single occurrence (covered by "first_*").
        if first and (first[0], first[1], first[2]) == (last[0], last[1], last[2]):
            continue
        season_id, venue, race_num, position, points, _pole, _fl = last
        out.append(
            Insight(
                category=InsightCategory.FIRST_ONLY_LAST,
                kind=kind,
                subject=driver,
                headline=(
                    f"Most recent {label}: {venue} R{int(race_num)} ({season_id})"
                ),
                payload={
                    "season": season_id,
                    "venue": venue,
                    "race": int(race_num),
                    "position": int(position) if position is not None else None,
                    "points": int(points) if points is not None else 0,
                    "label": label,
                },
                sources=[season_id],
            )
        )
    return out
