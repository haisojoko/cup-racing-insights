"""Pace / qualifying detectors — powered by the granular race dataset.

These read the tables loaded by ``races.py`` (race_pace, qual_times), which
only exist once the JSON dataset has been ingested. Every detector degrades to
an empty list when its table is missing or empty, so a Markdown-only build (or
seasons without telemetry) simply produces nothing here.

  D-089 pole_margin           — driver's widest qualifying pole margin (gap to P2)
  D-108 dominant_fastest_lap  — race where the driver's fastest lap was furthest
                                clear of the next-fastest lap
  D-109 avg_pace_gap          — seasons where the driver set the fastest average
                                race pace, plus their closest gap to the pace-setter
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory

# Minimum field size for a gap to be meaningful (avoid 2-car sessions).
_MIN_FIELD = 3
# Minimum races in a season before an average-pace ranking is trustworthy.
_MIN_SEASON_RACES = 3
# Fraction of the season's rounds a driver must have raced (with representative
# pace) to be ranked against peers — stops a driver who only ran the rounds they
# were quick at from being crowned pace-setter over a full-season regular.
_MIN_PARTICIPATION = 0.6
# A driver must set at least this many clean laps to count as having a
# representative pace / best lap (filters out one-lap DNFs and outlap-only runs
# whose "best" time would otherwise define a garbage P2 gap).
_MIN_CLEAN_LAPS = 2
# Sanity ceiling for a pole / fastest-lap margin, as a fraction of the reference
# time. Real dominant margins are well under this; anything larger is almost
# always a non-representative lap by the comparison driver, not a real gap.
_MAX_GAP_FRACTION = 0.03


def _has_table(con: DuckDBPyConnection, name: str) -> bool:
    try:
        con.execute(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except Exception:  # noqa: BLE001 — missing table on Markdown-only builds
        return False


def _fmt_gap(ms: float) -> str:
    """Seconds with 3 decimals, e.g. 812.0 → '0.812s'."""
    return f"{ms / 1000:.3f}s"


def detect_pole_margin(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """D-089 — the driver's biggest qualifying pole margin over P2."""
    if not _has_table(con, "qual_times"):
        return []
    row = con.execute(
        """
        WITH ranked AS (
            SELECT season_id, venue, venue_order, session, driver, best_ms,
                   ROW_NUMBER() OVER (PARTITION BY season_id, venue_order, session
                                      ORDER BY best_ms) AS pos,
                   COUNT(*) OVER (PARTITION BY season_id, venue_order, session) AS field
              FROM qual_times
        ),
        poles AS (
            SELECT p.season_id, p.venue, p.driver, p.field,
                   p.best_ms AS pole_ms, s.best_ms AS second_ms,
                   s.best_ms - p.best_ms AS gap_ms
              FROM ranked p
              JOIN ranked s USING (season_id, venue_order, session)
             WHERE p.pos = 1 AND s.pos = 2 AND p.field >= ?
               AND s.best_ms - p.best_ms <= p.best_ms * ?
        )
        SELECT season_id, venue, gap_ms, field
          FROM poles
         WHERE driver = ?
         ORDER BY gap_ms DESC
         LIMIT 1
        """,
        [_MIN_FIELD, _MAX_GAP_FRACTION, driver],
    ).fetchone()
    if not row:
        return []
    season_id, venue, gap_ms, field = row
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="pole_margin",
            subject=driver,
            headline=f"Widest pole: {_fmt_gap(gap_ms)} clear at {venue} ({season_id})",
            payload={
                "season": season_id,
                "venue": venue,
                "gap_ms": float(gap_ms),
                "gap_s": round(gap_ms / 1000, 3),
                "field": int(field),
            },
            sources=[season_id],
        )
    ]


def detect_dominant_fastest_lap(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """D-108 — race where the driver's fastest lap was furthest clear of the
    next-quickest lap set by anyone else."""
    if not _has_table(con, "race_pace"):
        return []
    row = con.execute(
        """
        WITH representative AS (
            SELECT * FROM race_pace WHERE laps_used >= ?
        ),
        ranked AS (
            SELECT season_id, venue, venue_order, race_num, driver, best_ms,
                   ROW_NUMBER() OVER (PARTITION BY season_id, venue_order, race_num
                                      ORDER BY best_ms) AS pos,
                   COUNT(*) OVER (PARTITION BY season_id, venue_order, race_num) AS field
              FROM representative
        ),
        margins AS (
            SELECT a.season_id, a.venue, a.race_num, a.driver, a.field,
                   b.best_ms - a.best_ms AS gap_ms
              FROM ranked a
              JOIN ranked b USING (season_id, venue_order, race_num)
             WHERE a.pos = 1 AND b.pos = 2 AND a.field >= ?
               AND b.best_ms - a.best_ms <= a.best_ms * ?
        )
        SELECT season_id, venue, race_num, gap_ms, field
          FROM margins
         WHERE driver = ?
         ORDER BY gap_ms DESC
         LIMIT 1
        """,
        [_MIN_CLEAN_LAPS, _MIN_FIELD, _MAX_GAP_FRACTION, driver],
    ).fetchone()
    if not row:
        return []
    season_id, venue, race_num, gap_ms, field = row
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="dominant_fastest_lap",
            subject=driver,
            headline=f"Fastest lap {_fmt_gap(gap_ms)} clear of the field at {venue} ({season_id})",
            payload={
                "season": season_id,
                "venue": venue,
                "race_num": int(race_num),
                "gap_ms": float(gap_ms),
                "gap_s": round(gap_ms / 1000, 3),
                "field": int(field),
            },
            sources=[season_id],
        )
    ]


def detect_avg_pace_gap(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """D-109 — average race-pace gap to the season's pace-setter.

    Each race's gap is normalised as a percentage over the fastest average that
    race (so tracks of different lengths compare fairly), then averaged across
    the season. Emits a `pace_setter_season` for every season the driver had the
    fastest average pace, and a single `pace_gap_to_leader` for their closest
    non-leading season.
    """
    if not _has_table(con, "race_pace"):
        return []
    rows = con.execute(
        """
        WITH representative AS (
            SELECT * FROM race_pace WHERE laps_used >= ?
        ),
        season_rounds AS (
            SELECT season_id, COUNT(DISTINCT (venue_order, race_num)) AS rounds
              FROM representative
          GROUP BY season_id
        ),
        race_best AS (
            SELECT season_id, venue_order, race_num, MIN(avg_ms) AS best_avg
              FROM representative
          GROUP BY season_id, venue_order, race_num
        ),
        gaps AS (
            SELECT p.season_id, p.driver,
                   AVG((p.avg_ms - rb.best_avg) / rb.best_avg) AS gap_pct,
                   COUNT(*) AS races
              FROM representative p
              JOIN race_best rb USING (season_id, venue_order, race_num)
          GROUP BY p.season_id, p.driver
        ),
        eligible AS (
            SELECT g.*, sr.rounds
              FROM gaps g
              JOIN season_rounds sr USING (season_id)
             WHERE g.races >= GREATEST(?, CEIL(? * sr.rounds))
        ),
        ranked AS (
            SELECT season_id, driver, gap_pct, races,
                   RANK() OVER (PARTITION BY season_id ORDER BY gap_pct) AS pace_rank,
                   COUNT(*) OVER (PARTITION BY season_id) AS cohort,
                   LEAD(gap_pct) OVER (PARTITION BY season_id ORDER BY gap_pct) AS next_gap_pct
              FROM eligible
        )
        SELECT season_id, gap_pct, races, pace_rank, cohort, next_gap_pct
          FROM ranked
         WHERE driver = ?
         ORDER BY gap_pct
        """,
        [_MIN_CLEAN_LAPS, _MIN_SEASON_RACES, _MIN_PARTICIPATION, driver],
    ).fetchall()
    if not rows:
        return []

    out: list[Insight] = []
    best_follower: tuple | None = None
    for season_id, gap_pct, races, pace_rank, cohort, next_gap_pct in rows:
        if pace_rank == 1:
            # Margin over the next-fastest driver (gap to "P2" on pace).
            margin_pct = (next_gap_pct - gap_pct) if next_gap_pct is not None else None
            clear = f" — {margin_pct * 100:.2f}% clear of the next driver" if margin_pct else ""
            out.append(
                Insight(
                    category=InsightCategory.PEER_RANK,
                    kind="pace_setter_season",
                    subject=driver,
                    headline=(
                        f"Fastest average race pace of {season_id}"
                        f"{clear} ({int(cohort)} drivers)"
                    ),
                    payload={
                        "season": season_id,
                        "cohort_size": int(cohort),
                        "rank": int(pace_rank),
                        "races": int(races),
                        "margin_pct": round(margin_pct * 100, 3) if margin_pct else None,
                    },
                    sources=[season_id],
                )
            )
        elif best_follower is None:
            best_follower = (season_id, gap_pct, races, pace_rank, cohort)

    if best_follower is not None:
        season_id, gap_pct, races, pace_rank, cohort = best_follower
        out.append(
            Insight(
                category=InsightCategory.MARGIN,
                kind="pace_gap_to_leader",
                subject=driver,
                headline=(
                    f"{gap_pct * 100:.2f}% off the pace-setter's average in {season_id} "
                    f"(P{int(pace_rank)} on race pace)"
                ),
                payload={
                    "season": season_id,
                    "gap_pct": round(float(gap_pct) * 100, 3),
                    "pace_rank": int(pace_rank),
                    "cohort_size": int(cohort),
                    "races": int(races),
                },
                sources=[season_id],
            )
        )
    return out
