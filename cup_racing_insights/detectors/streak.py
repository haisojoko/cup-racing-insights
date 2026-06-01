"""Streak detectors — sequences of consecutive results matching a predicate."""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


_SEASON_ORDER = """
    s.season_num,
    s.season_sub,
    r.venue_order,
    r.race_num
"""


def _ordered_results(con: DuckDBPyConnection, driver: str):
    """Return every race row for a driver in true season order."""
    return con.execute(
        f"""
        SELECT
            r.season_id, r.venue, r.venue_order, r.race_num,
            r.position, r.points, r.dns
        FROM race_results r
        JOIN seasons s USING (season_id)
        WHERE r.driver = ?
        ORDER BY {_SEASON_ORDER}
        """,
        [driver],
    ).fetchall()


def detect_top_n_streak(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """Find the longest run of consecutive races finishing in the top N.

    DNS rows break the streak (so does any finish > N).
    """
    insights: list[Insight] = []
    rows = _ordered_results(con, driver)
    if not rows:
        return insights

    for threshold in (3, 5, 10):
        best_len = 0
        best_start = best_end = None
        cur_len = 0
        cur_start = None

        for r in rows:
            season_id, venue, venue_order, race_num, position, points, dns = r
            in_streak = (not dns) and (position is not None) and position <= threshold
            if in_streak:
                if cur_len == 0:
                    cur_start = r
                cur_len += 1
                if cur_len > best_len:
                    best_len = cur_len
                    best_start = cur_start
                    best_end = r
            else:
                cur_len = 0
                cur_start = None

        # Only surface streaks of meaningful length.
        if best_len >= max(4, threshold - 1):
            insights.append(
                Insight(
                    category=InsightCategory.STREAK,
                    kind=f"top{threshold}_streak",
                    subject=driver,
                    headline=f"{best_len}-race top-{threshold} streak",
                    payload={
                        "threshold": threshold,
                        "length": best_len,
                        "start": {
                            "season": best_start[0],
                            "venue": best_start[1],
                            "race": best_start[3],
                        },
                        "end": {
                            "season": best_end[0],
                            "venue": best_end[1],
                            "race": best_end[3],
                        },
                    },
                    sources=[best_start[0], best_end[0]],
                )
            )
    return insights


def detect_in_season_hot_streak(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Longest top-3 / top-5 streak that occurred *within a single season*.

    Complements `detect_top_n_streak`, which spans seasons. Mid-season hot
    runs are a different editorial angle: "won 4 in a row at Sepang/Monza"
    is a season story, not a career arc.
    """
    rows = con.execute(
        """
        SELECT r.season_id, r.venue, r.venue_order, r.race_num,
               r.position, r.dns
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ?
      ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    out: list[Insight] = []
    for threshold in (3, 5):
        # Run a per-season longest-consecutive scan
        best_len = 0
        best_season = best_start = best_end = None
        cur_len = 0
        cur_season = None
        cur_start = None
        for r in rows:
            season_id, venue, venue_order, race_num, position, dns = r
            # Reset on season boundary
            if season_id != cur_season:
                cur_season = season_id
                cur_len = 0
                cur_start = None
            in_streak = (not dns) and (position is not None) and position <= threshold
            if in_streak:
                if cur_len == 0:
                    cur_start = r
                cur_len += 1
                if cur_len > best_len:
                    best_len = cur_len
                    best_season = season_id
                    best_start = cur_start
                    best_end = r
            else:
                cur_len = 0
                cur_start = None
        if best_len >= 3 and best_len > threshold - 1:
            out.append(
                Insight(
                    category=InsightCategory.STREAK,
                    kind="in_season_hot_streak",
                    subject=driver,
                    headline=(
                        f"{best_len}-race top-{threshold} streak in {best_season}"
                    ),
                    payload={
                        "threshold": threshold,
                        "length": best_len,
                        "season": best_season,
                        "start": {
                            "season": best_start[0],
                            "venue": best_start[1],
                            "race": best_start[3],
                        },
                        "end": {
                            "season": best_end[0],
                            "venue": best_end[1],
                            "race": best_end[3],
                        },
                    },
                    sources=[best_season],
                )
            )
    return out


def detect_consecutive_season_bests(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Longest run of consecutive races within a season where each result
    set a new in-season points high.

    A "building momentum" stat. A 4-race rising streak means the driver
    posted four results in a row where each was strictly better (by points)
    than every previous race that season.
    """
    rows = con.execute(
        """
        SELECT r.season_id, r.venue, r.venue_order, r.race_num,
               r.points, r.dns
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ?
      ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    best_len = 0
    best_season = best_start = best_end = None
    cur_season = None
    cur_len = 0
    cur_max = -1
    cur_start = None
    for r in rows:
        season_id, venue, venue_order, race_num, points, dns = r
        if season_id != cur_season:
            cur_season = season_id
            cur_len = 0
            cur_max = -1
            cur_start = None
        if dns:
            cur_len = 0
            cur_start = None
            continue
        if points > cur_max:
            if cur_len == 0:
                cur_start = r
            cur_len += 1
            cur_max = points
            if cur_len > best_len:
                best_len = cur_len
                best_season = season_id
                best_start = cur_start
                best_end = r
        else:
            cur_len = 0
            cur_start = None
            # NOTE: cur_max is preserved — a later non-improving result
            # doesn't reset the season's running maximum.

    if best_len < 3:
        return []
    return [
        Insight(
            category=InsightCategory.STREAK,
            kind="consecutive_season_bests",
            subject=driver,
            headline=(
                f"{best_len} consecutive races each setting a new {best_season} season high"
            ),
            payload={
                "length": best_len,
                "season": best_season,
                "start": {
                    "season": best_start[0],
                    "venue": best_start[1],
                    "race": best_start[3],
                },
                "end": {
                    "season": best_end[0],
                    "venue": best_end[1],
                    "race": best_end[3],
                    "points": int(best_end[4]),
                },
            },
            sources=[best_season],
        )
    ]


def detect_seasons_always_scoring(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Seasons in which the driver scored points in every race of the season.

    Requires perfect attendance (no DNS, no missed races on the roster) — a
    skipped weekend disqualifies the season, even if every race they did
    contest scored. Need at least 8 starts for the stat to be meaningful.
    """
    rows = con.execute(
        """
        WITH season_races AS (
            SELECT season_id,
                   COUNT(DISTINCT (venue_order, race_num)) AS scheduled
              FROM race_results
          GROUP BY season_id
        ),
        driver_season AS (
            SELECT season_id,
                   COUNT(*)                                              AS rows_for_driver,
                   SUM(CASE WHEN dns THEN 1 ELSE 0 END)                  AS dns_count,
                   SUM(CASE WHEN NOT dns THEN 1 ELSE 0 END)              AS starts,
                   SUM(CASE WHEN NOT dns AND points > 0 THEN 1 ELSE 0 END) AS scoring
              FROM race_results
             WHERE driver = ?
          GROUP BY season_id
        )
        SELECT ds.season_id, ds.starts
          FROM driver_season ds
          JOIN season_races sr USING (season_id)
         WHERE ds.starts >= 8
           AND ds.dns_count = 0
           AND ds.rows_for_driver = sr.scheduled
           AND ds.starts = ds.scoring
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    # Build a single aggregate insight; the season list is the story
    seasons = [r[0] for r in rows]
    seasons_sorted = sorted(seasons, key=lambda s: (
        int(s.lstrip("S").rstrip("ab")), s[-1] if s[-1].isalpha() else ""
    ))
    examples = ", ".join(seasons_sorted)
    return [
        Insight(
            category=InsightCategory.STREAK,
            kind="seasons_always_scoring",
            subject=driver,
            headline=(
                f"{len(rows)} season{'s' if len(rows) != 1 else ''} with a "
                f"perfect points-scoring record"
            ),
            payload={
                "season_count": len(rows),
                "seasons": seasons_sorted,
                "details": [
                    {"season": r[0], "starts": int(r[1])} for r in rows
                ],
            },
            sources=seasons_sorted,
        )
    ]


def detect_consecutive_points_streak(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Longest run of consecutive points-scoring finishes (points > 0, not DNS)."""
    rows = _ordered_results(con, driver)
    if not rows:
        return []

    best_len = 0
    best_start = best_end = None
    cur_len = 0
    cur_start = None
    for r in rows:
        _, _, _, _, _, points, dns = r
        if (not dns) and (points or 0) > 0:
            if cur_len == 0:
                cur_start = r
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
                best_end = r
        else:
            cur_len = 0
            cur_start = None

    if best_len < 6:
        return []

    return [
        Insight(
            category=InsightCategory.STREAK,
            kind="points_streak",
            subject=driver,
            headline=f"{best_len}-race points-scoring streak",
            payload={
                "length": best_len,
                "start": {
                    "season": best_start[0],
                    "venue": best_start[1],
                    "race": best_start[3],
                },
                "end": {
                    "season": best_end[0],
                    "venue": best_end[1],
                    "race": best_end[3],
                },
            },
            sources=[best_start[0], best_end[0]],
        )
    ]
