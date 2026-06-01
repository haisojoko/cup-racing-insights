"""Championship-margin detectors.

These reason about WCC outcomes by joining the parsed `team_standings`
table with race-result point sums. They surface two angles:

  D-074 wcc_contribution — driver's share of a WCC-winning team's points
  D-075 decisive_wcc_year — seasons where the driver's points exceeded
                            the team's margin of victory over P2

Both run on every season where the driver was on the WCC-winning roster.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def _wcc_seasons_for_driver(
    con: DuckDBPyConnection, driver: str
) -> list[tuple]:
    """Return rows for every season where `driver` was on the WCC-winning team.

    Each row: (season_id, winning_team_label, winning_pts, runnerup_pts,
               margin, driver_pts).
    """
    return con.execute(
        """
        WITH wcc_teams AS (
          SELECT season_id, team_label, members, points AS winning_pts
            FROM team_standings
           WHERE season_rank = 1
        ),
        runnerup AS (
          SELECT season_id, points AS runnerup_pts
            FROM team_standings
           WHERE season_rank = 2
        ),
        driver_season_pts AS (
          SELECT season_id, SUM(points) AS driver_pts
            FROM race_results
           WHERE driver = ?
        GROUP BY season_id
        )
        SELECT w.season_id, w.team_label,
               w.winning_pts,
               COALESCE(r.runnerup_pts, 0)             AS runnerup_pts,
               w.winning_pts - COALESCE(r.runnerup_pts, 0) AS margin,
               COALESCE(d.driver_pts, 0)               AS driver_pts
          FROM wcc_teams w
          LEFT JOIN runnerup r USING (season_id)
          LEFT JOIN driver_season_pts d USING (season_id)
         WHERE list_contains(w.members, ?)
        """,
        [driver, driver],
    ).fetchall()


def detect_wcc_contribution(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver's percentage share of their WCC-winning team's points.

    Aggregates across all WCC-winning seasons. For drivers with multiple
    WCC titles, the aggregate is more useful than per-season rows.
    """
    rows = _wcc_seasons_for_driver(con, driver)
    if not rows:
        return []

    out: list[Insight] = []
    # Per-season detail
    for season_id, team_label, winning_pts, _runner, _margin, driver_pts in rows:
        if winning_pts <= 0:
            continue
        pct = (driver_pts / winning_pts) * 100
        out.append(
            Insight(
                category=InsightCategory.MARGIN,
                kind="wcc_contribution",
                subject=driver,
                headline=(
                    f"{pct:.1f}% of {season_id} WCC team points "
                    f"({int(driver_pts)} of {int(winning_pts)})"
                ),
                payload={
                    "season": season_id,
                    "team": team_label,
                    "team_points": int(winning_pts),
                    "driver_points": int(driver_pts),
                    "pct": float(pct),
                },
                sources=[season_id],
            )
        )
    return out


def detect_decisive_wcc_year(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Seasons where the driver's points exceeded the team's WCC margin.

    A driver was decisive if, removing all their points, the team would
    have finished behind P2. Captures the "without X, no title" story.
    """
    rows = _wcc_seasons_for_driver(con, driver)
    if not rows:
        return []

    out: list[Insight] = []
    for season_id, team_label, winning_pts, runnerup_pts, margin, driver_pts in rows:
        if margin <= 0:
            continue
        if driver_pts <= margin:
            continue
        out.append(
            Insight(
                category=InsightCategory.MARGIN,
                kind="decisive_wcc_year",
                subject=driver,
                headline=(
                    f"Decisive {season_id} WCC: team won by {int(margin)} pts; "
                    f"{driver} delivered {int(driver_pts)}"
                ),
                payload={
                    "season": season_id,
                    "team": team_label,
                    "team_points": int(winning_pts),
                    "runner_up_points": int(runnerup_pts),
                    "margin": int(margin),
                    "driver_points": int(driver_pts),
                },
                sources=[season_id],
            )
        )
    return out
