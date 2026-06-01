"""League-wide uniqueness detectors.

These look across every driver in the database to find facts that are true
only of the subject. "Only driver to..." statements carry weight because
they're verifiable claims of singularity.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def detect_only_to_pole_sweep(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver swept all poles at any venue weekend, AND is the only driver
    in league history to have done so at any venue."""
    sweeps = con.execute(
        """
        WITH per_venue AS (
          SELECT r.driver, r.season_id, r.venue,
                 SUM(CASE WHEN r.is_pole THEN 1 ELSE 0 END) AS poles,
                 s.races_per_venue                          AS slots
            FROM race_results r
            JOIN seasons s USING (season_id)
        GROUP BY r.driver, r.season_id, r.venue, r.venue_order, s.races_per_venue
        )
        SELECT driver, COUNT(*) AS sweeps
          FROM per_venue
         WHERE poles = slots AND slots >= 3
      GROUP BY driver
        """
    ).fetchall()
    by_driver = {d: s for d, s in sweeps}
    if driver not in by_driver:
        return []
    if len(by_driver) > 1:
        return []
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="only_to_pole_sweep",
            subject=driver,
            headline=(
                f"Only driver in league history to sweep every pole at a venue "
                f"({by_driver[driver]} venue weekend{'s' if by_driver[driver] != 1 else ''})"
            ),
            payload={
                "sweep_count": int(by_driver[driver]),
                "cohort_size": len(by_driver),
            },
        )
    ]


def detect_sole_venue_winner(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Venues where the named driver is the only winner in league history.

    Filters to venues that have been visited at least once. For dominant
    drivers, collapses into an aggregate; for niche cases lists the venues.
    """
    rows = con.execute(
        """
        WITH winners_per_venue AS (
          SELECT venue,
                 COUNT(DISTINCT driver) AS distinct_winners,
                 MAX(driver)            AS sample_winner
            FROM race_results
           WHERE position = 1
        GROUP BY venue
        )
        SELECT venue
          FROM winners_per_venue
         WHERE distinct_winners = 1
           AND sample_winner = ?
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    venues = sorted([r[0] for r in rows])
    if len(venues) >= 4:
        return [
            Insight(
                category=InsightCategory.FIRST_ONLY_LAST,
                kind="sole_venue_winner",
                subject=driver,
                headline=(
                    f"Sole winner at {len(venues)} different circuits"
                ),
                payload={
                    "venue_count": len(venues),
                    "examples": venues[:3],
                },
            )
        ]
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="sole_venue_winner",
            subject=driver,
            headline=(
                f"Only winner ever at {len(venues)} circuit{'s' if len(venues) != 1 else ''}: "
                f"{', '.join(venues)}"
            ),
            payload={
                "venue_count": len(venues),
                "venues": venues,
            },
        )
    ]


def detect_first_to_milestone(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """League-wide chronological firsts at career milestones.

    Computes a running per-driver count of wins / podiums / poles across
    the full race history, then identifies who reached each threshold
    first. Reports any milestones the named driver was first to.
    """
    out: list[Insight] = []
    thresholds = {
        "wins":    [5, 10, 25, 50, 100, 150, 200, 250, 300],
        "podiums": [10, 25, 50, 100, 200, 300, 400, 500],
        "poles":   [5, 10, 25, 50, 100, 150, 200, 250, 300, 350],
    }
    cols = {
        "wins":    "position = 1",
        "podiums": "position BETWEEN 1 AND 3",
        "poles":   "is_pole",
    }
    for metric, predicate in cols.items():
        # Stream every relevant result in chronological order; track per-
        # driver running counts; remember the first driver to hit each
        # threshold.
        rows = con.execute(
            f"""
            SELECT r.driver, r.season_id, r.venue, r.race_num
              FROM race_results r
              JOIN seasons s USING (season_id)
             WHERE ({predicate})
          ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
            """,
        ).fetchall()
        running: dict[str, int] = {}
        first_to: dict[int, tuple] = {}  # threshold -> (driver, season, venue, race)
        for d, season_id, venue, race_num in rows:
            running[d] = running.get(d, 0) + 1
            n = running[d]
            for t in thresholds[metric]:
                if n == t and t not in first_to:
                    first_to[t] = (d, season_id, venue, race_num)
        for t in thresholds[metric]:
            entry = first_to.get(t)
            if entry and entry[0] == driver:
                _, season_id, venue, race_num = entry
                out.append(
                    Insight(
                        category=InsightCategory.FIRST_ONLY_LAST,
                        kind=f"first_to_milestone_{metric}",
                        subject=driver,
                        headline=(
                            f"First driver in league history to {t} career {metric}"
                        ),
                        payload={
                            "metric": metric,
                            "threshold": t,
                            "season": season_id,
                            "venue": venue,
                            "race": int(race_num),
                        },
                        sources=[season_id],
                    )
                )
    return out


def detect_only_winless_with_long_streak(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver has 0 career wins AND a long top-5 streak that no other
    winless driver matches. Uses ≥10 consecutive top-5 finishes as the
    bar; tunable as the dataset grows.
    """
    me = con.execute(
        "SELECT wins FROM career_stats WHERE driver = ?",
        [driver],
    ).fetchone()
    if not me or me[0] != 0:
        return []

    # Compute each winless driver's longest top-5 streak via Python (DuckDB
    # window-based gap-detection is also valid but harder to read).
    winless = [
        r[0]
        for r in con.execute(
            "SELECT driver FROM career_stats WHERE wins = 0 AND races >= 30"
        ).fetchall()
    ]
    if driver not in winless:
        return []

    longest = {}
    for d in winless:
        rows = con.execute(
            """
            SELECT r.position, r.dns
              FROM race_results r
              JOIN seasons s USING (season_id)
             WHERE r.driver = ?
          ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
            """,
            [d],
        ).fetchall()
        best = cur = 0
        for pos, dns in rows:
            if (not dns) and pos is not None and pos <= 5:
                cur += 1
                best = max(best, cur)
            else:
                cur = 0
        longest[d] = best

    me_len = longest[driver]
    if me_len < 10:
        return []
    leaders = [d for d, n in longest.items() if n == me_len]
    if leaders != [driver]:
        # Not uniquely the leader.
        return []
    runner_up = max((n for d, n in longest.items() if d != driver), default=0)
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="only_winless_with_long_streak",
            subject=driver,
            headline=(
                f"Longest top-5 streak of any winless driver ({me_len} races)"
            ),
            payload={
                "length": me_len,
                "runner_up": runner_up,
                "cohort_size": len(winless),
            },
        )
    ]


def detect_wins_without_poles(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Drivers with multiple career wins but zero career poles.

    A small-club stat: they get to the front on race day without ever doing
    it in qualifying. Requires >= 2 wins so a single fluke win doesn't qualify.
    """
    rows = con.execute(
        """
        SELECT driver, wins
          FROM career_stats
         WHERE poles = 0 AND wins >= 2
      ORDER BY wins DESC, driver
        """
    ).fetchall()
    if not rows:
        return []
    cohort = {d: int(w) for d, w in rows}
    if driver not in cohort:
        return []

    wins = cohort[driver]
    # Rank within the cohort (1 = most wins).
    rank = 1 + sum(1 for d, w in cohort.items() if w > wins)
    cohort_size = len(cohort)

    if cohort_size == 1:
        headline = (
            f"Only driver in league history with multiple career wins "
            f"and zero career poles ({wins} wins)"
        )
    else:
        headline = (
            f"{wins} career wins, zero career poles — "
            f"one of {cohort_size} drivers ever to do that"
        )
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="wins_without_poles",
            subject=driver,
            headline=headline,
            payload={
                "wins": wins,
                "cohort_size": cohort_size,
                "rank_in_cohort": rank,
            },
        )
    ]


def detect_won_both_classes(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver has won races in both Formula and Sports car seasons.

    Cup Racing alternates classes; winning in both is a versatility marker
    that not every race winner achieves.
    """
    cohort_rows = con.execute(
        """
        WITH wins_by_class AS (
            SELECT r.driver, s.type AS class, COUNT(*) AS wins
              FROM race_results r
              JOIN seasons s USING (season_id)
             WHERE r.position = 1
          GROUP BY r.driver, s.type
        )
        SELECT driver
          FROM wins_by_class
      GROUP BY driver
        HAVING COUNT(DISTINCT class) = 2
        """
    ).fetchall()
    cohort = {d for (d,) in cohort_rows}
    if driver not in cohort:
        return []

    per_class = con.execute(
        """
        SELECT s.type, COUNT(*)
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND r.position = 1
      GROUP BY s.type
        """,
        [driver],
    ).fetchall()
    by_class = {t: int(c) for t, c in per_class}
    f_wins = by_class.get("Formula", 0)
    s_wins = by_class.get("Sports", 0)
    cohort_size = len(cohort)

    if cohort_size == 1:
        headline = (
            f"Only driver to win races in both Formula and Sports car formats "
            f"({f_wins}F / {s_wins}S)"
        )
    else:
        headline = (
            f"Race winner in both Formula and Sports formats "
            f"({f_wins}F / {s_wins}S) — one of {cohort_size} drivers"
        )
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="won_both_classes",
            subject=driver,
            headline=headline,
            payload={
                "formula_wins": f_wins,
                "sports_wins": s_wins,
                "cohort_size": cohort_size,
            },
        )
    ]


def detect_multiple_wcc_club(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver is a multiple WCC title-holder."""
    me = con.execute(
        "SELECT wcc FROM career_stats WHERE driver = ?", [driver]
    ).fetchone()
    if not me or (me[0] or 0) < 2:
        return []
    wcc = int(me[0])

    cohort = con.execute(
        "SELECT driver, wcc FROM career_stats WHERE wcc >= 2 ORDER BY wcc DESC"
    ).fetchall()
    cohort_size = len(cohort)
    leader_wcc = int(cohort[0][1])
    rank = 1 + sum(1 for _, c in cohort if int(c) > wcc)

    if rank == 1 and sum(1 for _, c in cohort if int(c) == wcc) == 1:
        headline = f"League-leading {wcc} WCC titles"
    else:
        headline = (
            f"{wcc}-time WCC winner — "
            f"one of {cohort_size} multi-WCC drivers in league history"
        )
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="multiple_wcc_club",
            subject=driver,
            headline=headline,
            payload={
                "wcc_titles": wcc,
                "cohort_size": cohort_size,
                "leader_titles": leader_wcc,
                "rank_in_cohort": rank,
            },
        )
    ]


def detect_multiple_wdc_club(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver is a multiple WDC title-holder."""
    me = con.execute(
        "SELECT wdc FROM career_stats WHERE driver = ?", [driver]
    ).fetchone()
    if not me or (me[0] or 0) < 2:
        return []
    wdc = int(me[0])

    cohort = con.execute(
        "SELECT driver, wdc FROM career_stats WHERE wdc >= 2 ORDER BY wdc DESC"
    ).fetchall()
    cohort_size = len(cohort)
    leader_wdc = int(cohort[0][1])
    rank = 1 + sum(1 for _, c in cohort if int(c) > wdc)

    if rank == 1 and sum(1 for _, c in cohort if int(c) == wdc) == 1:
        headline = f"League-leading {wdc} WDC titles"
    else:
        headline = (
            f"{wdc}-time WDC champion — "
            f"one of {cohort_size} multi-WDC drivers in league history"
        )
    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="multiple_wdc_club",
            subject=driver,
            headline=headline,
            payload={
                "wdc_titles": wdc,
                "cohort_size": cohort_size,
                "leader_titles": leader_wdc,
                "rank_in_cohort": rank,
            },
        )
    ]
