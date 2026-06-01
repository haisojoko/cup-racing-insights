"""Trajectory detectors — the career-arc narrative.

Year-over-year change is one of the highest-signal patterns in sports
analytics. Even when raw totals aren't impressive, a clear improvement curve
is a story worth telling.

We compute each driver's overall season finishing rank (by total points)
on the fly so we don't need a precomputed standings table.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def _season_rank_series(con: DuckDBPyConnection, driver: str):
    """Return a sequence [(season_id, rank, points, podiums, top5, starts), ...]
    for every season the driver started at least 3 races in, ordered.
    """
    return con.execute(
        """
        WITH season_totals AS (
          SELECT season_id, driver,
                 SUM(points) AS pts,
                 SUM(CASE WHEN NOT dns THEN 1 ELSE 0 END) AS starts,
                 SUM(CASE WHEN position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
                 SUM(CASE WHEN position BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS top5
            FROM race_results
        GROUP BY season_id, driver
        ),
        ranked AS (
          SELECT season_id, driver, pts, starts, podiums, top5,
                 RANK() OVER (PARTITION BY season_id ORDER BY pts DESC) AS rnk
            FROM season_totals
        )
        SELECT ranked.season_id, ranked.rnk, ranked.pts,
               ranked.podiums, ranked.top5, ranked.starts
          FROM ranked
          JOIN seasons s USING (season_id)
         WHERE ranked.driver = ?
           AND ranked.starts >= 3
           -- Skip in-progress seasons (no WDC declared yet).
           AND s.wdc IS NOT NULL
           AND UPPER(s.wdc) NOT IN ('TBD', '')
      ORDER BY s.season_num, s.season_sub
        """,
        [driver],
    ).fetchall()


def detect_best_vs_worst_season(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Spread between a driver's best (lowest-numbered) and worst
    (highest-numbered) season finishing position.

    This captures career range rather than direction — a driver who
    oscillated P3 → P10 → P4 has a meaningful 7-place spread even though
    they didn't improve linearly. Replaces the older first→last detector.
    """
    series = _season_rank_series(con, driver)
    if len(series) < 2:
        return []
    seasons = [r[0] for r in series]
    ranks = [int(r[1]) for r in series]

    best_rank = min(ranks)
    worst_rank = max(ranks)
    spread = worst_rank - best_rank
    if spread < 2:
        return []  # too narrow to be a story (or only competed in 1 strata)
    # Only fire when the best season was genuinely good — otherwise the
    # "spread" reads as mid-pack-to-back-of-grid rather than a meaningful
    # arc. Bar set at P8 so a top-half finish anchors the story.
    if best_rank > 8:
        return []

    # Find the seasons where best/worst occurred (use the first occurrence).
    best_season = next(s for s, r in zip(seasons, ranks) if r == best_rank)
    worst_season = next(s for s, r in zip(seasons, ranks) if r == worst_rank)

    return [
        Insight(
            category=InsightCategory.TRAJECTORY,
            kind="best_vs_worst_season",
            subject=driver,
            headline=(
                f"Best vs worst season difference: "
                f"P{best_rank} ({best_season}) to P{worst_rank} ({worst_season})"
            ),
            payload={
                "best_rank": best_rank,
                "best_season": best_season,
                "worst_rank": worst_rank,
                "worst_season": worst_season,
                "spread": int(spread),
                "season_count": len(series),
                "series": [
                    {"season": s, "rank": int(rnk)}
                    for s, rnk in zip(seasons, ranks)
                ],
            },
            sources=seasons,
        )
    ]


def detect_consecutive_podium_seasons(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Longest run of consecutive seasons with at least one podium."""
    series = _season_rank_series(con, driver)
    if not series:
        return []
    best_len = 0
    best_seasons: list[str] = []
    cur_len = 0
    cur_seasons: list[str] = []
    for season_id, _rnk, _pts, podiums, _top5, _starts in series:
        if (podiums or 0) >= 1:
            cur_seasons.append(season_id)
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_seasons = list(cur_seasons)
        else:
            cur_len = 0
            cur_seasons = []
    if best_len < 3:
        return []
    return [
        Insight(
            category=InsightCategory.STREAK,
            kind="consecutive_podium_seasons",
            subject=driver,
            headline=(
                f"{best_len} consecutive seasons with a podium "
                f"({best_seasons[0]} → {best_seasons[-1]})"
            ),
            payload={
                "length": best_len,
                "seasons": best_seasons,
            },
            sources=best_seasons,
        )
    ]


def detect_personal_best_season_rank(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Career-best overall season finishing position."""
    series = _season_rank_series(con, driver)
    if not series:
        return []
    best = min(series, key=lambda r: int(r[1]))
    season_id, rnk, pts, podiums, top5, starts = best
    occurrences = [r[0] for r in series if int(r[1]) == int(rnk)]
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="best_season_rank",
            subject=driver,
            headline=f"Career-best overall finish: P{int(rnk)} ({season_id})",
            payload={
                "rank": int(rnk),
                "season": season_id,
                "points": int(pts),
                "podiums": int(podiums),
                "top5": int(top5),
                "starts": int(starts),
                "occurrences": occurrences,
            },
            sources=occurrences,
        )
    ]
