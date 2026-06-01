"""Range / consistency detectors.

Finishing-position spread within a season is a strong signal of metronomic
performance. "Worst result was P5 in 16 races" is the kind of stat that
makes a season feel mechanical, even if the headline win count is zero.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


_MIN_STARTS_PER_SEASON = 8


def _season_ranges(con: DuckDBPyConnection, driver: str):
    return con.execute(
        """
        SELECT season_id,
               MIN(position) AS best,
               MAX(position) AS worst,
               COUNT(*)      AS starts
          FROM race_results
         WHERE driver = ? AND NOT dns AND position IS NOT NULL
      GROUP BY season_id
        HAVING starts >= ?
        """,
        [driver, _MIN_STARTS_PER_SEASON],
    ).fetchall()


def detect_tightest_season_range(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Smallest spread between best and worst finish in a season."""
    rows = _season_ranges(con, driver)
    if not rows:
        return []
    # Smallest range, tie-broken by best (lower) position.
    rows = sorted(rows, key=lambda r: (r[2] - r[1], r[1]))
    season_id, best, worst, starts = rows[0]
    spread = int(worst) - int(best)
    # Tight = spread small relative to start count. Require strong threshold.
    if spread > 6:
        return []
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="tightest_season_range",
            subject=driver,
            headline=(
                f"Tightest season: {season_id} — every result between "
                f"P{int(best)} and P{int(worst)} ({int(starts)} starts)"
            ),
            payload={
                "season": season_id,
                "best": int(best),
                "worst": int(worst),
                "spread": spread,
                "starts": int(starts),
            },
            sources=[season_id],
        )
    ]


def detect_season_never_outside_top_n(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Identify seasons where the worst non-DNS finish was inside the top N."""
    rows = _season_ranges(con, driver)
    out: list[Insight] = []
    seen_thresholds: set[int] = set()
    # Surface the best threshold (smallest N) per season.
    for season_id, best, worst, starts in sorted(rows, key=lambda r: r[2]):
        worst = int(worst)
        if worst > 10:
            continue
        for n in (3, 5, 10):
            if worst <= n and n not in seen_thresholds:
                out.append(
                    Insight(
                        category=InsightCategory.STREAK,
                        kind="season_never_outside_top_n",
                        subject=driver,
                        headline=(
                            f"Never outside the top {n} in {season_id} "
                            f"({int(starts)} starts, worst P{worst})"
                        ),
                        payload={
                            "season": season_id,
                            "threshold": n,
                            "worst": worst,
                            "best": int(best),
                            "starts": int(starts),
                        },
                        sources=[season_id],
                    )
                )
                seen_thresholds.add(n)
                break
    return out
