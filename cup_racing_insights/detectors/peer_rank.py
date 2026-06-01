"""Peer-rank detectors: where does a driver stand relative to a cohort?

These produce the "highest X among Y" insights that feel meaningful because
they encode context, not just a raw number.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


# Minimum career races for a driver to count as a peer (filters out cameos).
_MIN_RACES_FOR_PEER = 30


def detect_among_winless_peers(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Rank the driver against other 0-win drivers on key efficiency stats."""
    me = con.execute(
        "SELECT wins, podiums, top5, races, pod_pct, top5_pct, pts_per_race "
        "FROM career_stats WHERE driver = ?",
        [driver],
    ).fetchone()
    if not me or me[0] != 0:
        return []  # driver isn't winless

    podiums, top5, races, pod_pct, top5_pct, ppr = me[1:]

    metrics = [
        ("pod_pct", "podium rate", pod_pct, "%", 100),
        ("top5_pct", "top-5 rate", top5_pct, "%", 100),
        ("pts_per_race", "pts/race", ppr, "", 1),
    ]

    out: list[Insight] = []
    for col, label, my_val, unit, scale in metrics:
        if my_val is None:
            continue
        rows = con.execute(
            f"""
            SELECT driver, {col}
              FROM career_stats
             WHERE wins = 0 AND races >= ?
             ORDER BY {col} DESC NULLS LAST
            """,
            [_MIN_RACES_FOR_PEER],
        ).fetchall()
        # rank within winless cohort
        cohort = [r for r in rows if r[1] is not None]
        if not cohort:
            continue
        rank = next((i + 1 for i, r in enumerate(cohort) if r[0] == driver), None)
        if rank is None:
            continue
        if rank > 3:
            continue
        out.append(
            Insight(
                category=InsightCategory.PEER_RANK,
                kind=f"winless_rank_{col}",
                subject=driver,
                headline=(
                    f"#{rank} {label} among 0-win drivers "
                    f"({my_val * scale:.1f}{unit})"
                ),
                payload={
                    "rank": rank,
                    "cohort_size": len(cohort),
                    "metric": col,
                    "label": label,
                    "value": float(my_val),
                    "unit": unit,
                    "scale": scale,
                    "filter": "winless_min30",
                    "top5_in_cohort": [
                        {"driver": d, "value": float(v)} for d, v in cohort[:5]
                    ],
                },
            )
        )
    return out


def detect_distinct_venues_won(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Number of distinct circuits the driver has won at, plus rank.

    Captures career breadth — a driver who's won at 14 different venues
    has a different profile than one with 12 wins all at the same track.
    """
    my_count = con.execute(
        """
        SELECT COUNT(DISTINCT venue)
          FROM race_results
         WHERE driver = ? AND position = 1
        """,
        [driver],
    ).fetchone()[0] or 0
    if my_count < 2:
        return []

    # Build league-wide leaderboard
    rows = con.execute(
        """
        SELECT driver, COUNT(DISTINCT venue) AS venues
          FROM race_results
         WHERE position = 1
      GROUP BY driver
      ORDER BY venues DESC
        """
    ).fetchall()
    rank = next((i + 1 for i, r in enumerate(rows) if r[0] == driver), None)
    if rank is None or rank > 10:
        return []

    return [
        Insight(
            category=InsightCategory.PEER_RANK,
            kind="distinct_winning_venues",
            subject=driver,
            headline=(
                f"Won at {int(my_count)} different circuits — #{rank} all-time"
            ),
            payload={
                "venue_count": int(my_count),
                "rank": rank,
                "cohort_size": len(rows),
            },
        )
    ]


def detect_among_all_drivers(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Where does the driver rank league-wide on key metrics?
    Only surface if ranked in the top 10.
    """
    out: list[Insight] = []
    metrics = [
        ("podiums", "career podiums", "", 1),
        ("poles", "career poles", "", 1),
        ("points", "career points", "", 1),
        ("races", "career starts", "", 1),
        ("top5", "career top-5 finishes", "", 1),
    ]
    for col, label, unit, scale in metrics:
        rows = con.execute(
            f"""
            SELECT driver, {col}
              FROM career_stats
             WHERE {col} IS NOT NULL
             ORDER BY {col} DESC
            """,
        ).fetchall()
        cohort = [r for r in rows if r[1] is not None]
        if not cohort:
            continue
        rank = next((i + 1 for i, r in enumerate(cohort) if r[0] == driver), None)
        if rank is None or rank > 10:
            continue
        my_val = next(v for d, v in cohort if d == driver)
        out.append(
            Insight(
                category=InsightCategory.PEER_RANK,
                kind=f"league_rank_{col}",
                subject=driver,
                headline=f"#{rank} all-time in {label} ({my_val}{unit})",
                payload={
                    "rank": rank,
                    "cohort_size": len(cohort),
                    "metric": col,
                    "label": label,
                    "value": float(my_val) * scale,
                    "unit": unit,
                },
            )
        )
    return out
