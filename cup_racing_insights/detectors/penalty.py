"""Penalty / discipline detectors.

The penalty column on race_results is positive points deducted in-race.
Summed and segmented, this exposes a different narrative axis: cleanliness,
costly weekends, and points-left-on-the-table stories.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def detect_penalty_summary(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """Career total + worst-season penalty exposure."""
    out: list[Insight] = []

    totals = con.execute(
        """
        SELECT COALESCE(SUM(penalty), 0) AS total_pen,
               SUM(CASE WHEN penalty > 0 THEN 1 ELSE 0 END) AS pen_races,
               COUNT(*) AS starts
          FROM race_results
         WHERE driver = ? AND NOT dns
        """,
        [driver],
    ).fetchone()
    if not totals:
        return out
    total_pen, pen_races, starts = totals
    if (starts or 0) == 0:
        return out

    pen_rate = (pen_races or 0) / starts if starts else 0.0

    # Career "clean driver" callout (lots of starts, almost no penalties).
    if starts >= 30 and pen_rate <= 0.06 and total_pen <= 10:
        out.append(
            Insight(
                category=InsightCategory.RECORD,
                kind="clean_career",
                subject=driver,
                headline=(
                    f"Career-clean: only {int(pen_races)} of {int(starts)} starts "
                    f"penalised ({int(total_pen)} total pts)"
                ),
                payload={
                    "total_pen": int(total_pen),
                    "pen_races": int(pen_races),
                    "starts": int(starts),
                    "pen_rate": pen_rate,
                },
            )
        )

    # Heaviest penalty single race.
    worst = con.execute(
        """
        SELECT r.season_id, r.venue, r.race_num, r.position, r.penalty
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND r.penalty > 0
      ORDER BY r.penalty DESC, s.season_num, s.season_sub, r.venue_order, r.race_num
         LIMIT 1
        """,
        [driver],
    ).fetchone()
    if worst and (worst[4] or 0) >= 4:
        season_id, venue, race_num, position, penalty = worst
        pos_str = f"P{int(position)}" if position is not None else "DNS"
        out.append(
            Insight(
                category=InsightCategory.ANOMALY,
                kind="worst_penalty_race",
                subject=driver,
                headline=(
                    f"Heaviest single-race penalty: -{int(penalty)} pts "
                    f"at {venue} R{int(race_num)} ({season_id}, {pos_str})"
                ),
                payload={
                    "season": season_id,
                    "venue": venue,
                    "race": int(race_num),
                    "position": int(position) if position is not None else None,
                    "penalty": int(penalty),
                },
                sources=[season_id],
            )
        )

    # Worst penalty season (only if meaningfully large).
    worst_season = con.execute(
        """
        SELECT season_id, SUM(penalty) AS pen,
               SUM(CASE WHEN penalty > 0 THEN 1 ELSE 0 END) AS pen_races
          FROM race_results
         WHERE driver = ?
      GROUP BY season_id
      ORDER BY pen DESC
         LIMIT 1
        """,
        [driver],
    ).fetchone()
    if worst_season and (worst_season[1] or 0) >= 8:
        season_id, pen, pen_races_in_season = worst_season
        out.append(
            Insight(
                category=InsightCategory.ANOMALY,
                kind="worst_penalty_season",
                subject=driver,
                headline=(
                    f"Most-penalised season: {season_id} "
                    f"(-{int(pen)} pts across {int(pen_races_in_season)} races)"
                ),
                payload={
                    "season": season_id,
                    "penalty_total": int(pen),
                    "penalised_races": int(pen_races_in_season),
                },
                sources=[season_id],
            )
        )

    return out
