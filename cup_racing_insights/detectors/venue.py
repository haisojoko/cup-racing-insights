"""Venue-anchored detectors.

These bind stories to a specific circuit. Pro shops use this constantly —
"X always goes well at Y" is one of the most repeated broadcast hooks.

Detectors here cover both single-trip patterns (a perfect pole sweep at one
venue weekend) and across-trip patterns (multiple wins at the same circuit
over several seasons).
"""

from __future__ import annotations

import re

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def _season_sort_key(sid: str) -> tuple:
    """Return a numeric sort key for season IDs like 'S1', 'S18a', 'S18b'."""
    m = re.match(r"^S(\d+)([a-z]?)$", sid or "")
    if not m:
        return (9999, sid)
    return (int(m.group(1)), m.group(2))


def detect_venue_pole_sweep(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Driver took every pole at a venue weekend.

    Requires races_per_venue >= 3 so a one-race fluke can't qualify.
    """
    rows = con.execute(
        """
        SELECT r.season_id, r.venue, s.races_per_venue,
               SUM(CASE WHEN r.is_pole THEN 1 ELSE 0 END) AS poles,
               COUNT(*) AS slots
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ?
      GROUP BY r.season_id, r.venue, r.venue_order, s.races_per_venue,
               s.season_num, s.season_sub
        HAVING poles = s.races_per_venue
           AND s.races_per_venue >= 3
      ORDER BY s.season_num, s.season_sub, r.venue_order
        """,
        [driver],
    ).fetchall()
    # Once a driver has crossed the aggregate threshold, the headline IS
    # the count — individual sweep callouts only add noise. Return just the
    # aggregate; its payload carries example venues for any template that
    # wants to name one.
    AGGREGATE_THRESHOLD = 4

    if len(rows) >= AGGREGATE_THRESHOLD:
        seasons = sorted({r[0] for r in rows}, key=_season_sort_key)
        most_recent = rows[-1]
        return [
            Insight(
                category=InsightCategory.FIRST_ONLY_LAST,
                kind="venue_pole_sweep_career",
                subject=driver,
                headline=(
                    f"{len(rows)} venue pole sweeps across {len(seasons)} seasons"
                ),
                payload={
                    "sweep_count": len(rows),
                    "season_count": len(seasons),
                    "seasons": seasons,
                    "most_recent": {
                        "season": most_recent[0],
                        "venue": most_recent[1],
                        "races": int(most_recent[4]),
                    },
                    "examples": [
                        {"season": r[0], "venue": r[1], "races": int(r[4])}
                        for r in rows[-3:]
                    ],
                },
                sources=seasons,
            )
        ]

    return [
        Insight(
            category=InsightCategory.FIRST_ONLY_LAST,
            kind="venue_pole_sweep",
            subject=driver,
            headline=f"{poles}/{slots} pole sweep at {venue} ({season})",
            payload={
                "season": season,
                "venue": venue,
                "poles": int(poles),
                "races": int(slots),
            },
            sources=[season],
        )
        for season, venue, _rpv, poles, slots in rows
    ]


def detect_venue_repeat_wins(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Multiple wins at the same circuit (across any number of seasons).

    For dominant drivers (many venues won at multiple times), collapse into
    a single aggregate plus the most-prolific example.
    """
    rows = con.execute(
        """
        SELECT r.venue,
               COUNT(*) AS wins,
               LIST(r.season_id ORDER BY s.season_num, s.season_sub) AS seasons
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND r.position = 1
      GROUP BY r.venue
        HAVING COUNT(*) >= 2
      ORDER BY wins DESC, r.venue
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    AGGREGATE_THRESHOLD = 5
    if len(rows) >= AGGREGATE_THRESHOLD:
        total_repeat_wins = sum(int(r[1]) for r in rows)
        top = rows[0]
        return [
            Insight(
                category=InsightCategory.RECORD,
                kind="venue_repeat_wins_career",
                subject=driver,
                headline=(
                    f"Multiple career wins at {len(rows)} different venues"
                ),
                payload={
                    "venue_count": len(rows),
                    "total_repeat_wins": total_repeat_wins,
                    "top": {
                        "venue": top[0],
                        "wins": int(top[1]),
                        "seasons": [str(s) for s in top[2]],
                    },
                },
            )
        ]

    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="venue_repeat_wins",
            subject=driver,
            headline=f"{wins} career wins at {venue}",
            payload={
                "venue": venue,
                "wins": int(wins),
                "seasons": list(seasons),
            },
            sources=sorted({str(s) for s in seasons}, key=_season_sort_key),
        )
        for venue, wins, seasons in rows
    ]


def detect_best_avg_venue(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Best average finishing position at a venue (min 4 starts to qualify)."""
    row = con.execute(
        """
        SELECT venue, AVG(position) AS avg_pos, COUNT(*) AS starts,
               LIST(DISTINCT season_id) AS seasons
          FROM race_results
         WHERE driver = ? AND NOT dns AND position IS NOT NULL
      GROUP BY venue
        HAVING COUNT(*) >= 4
      ORDER BY avg_pos ASC, starts DESC
         LIMIT 1
        """,
        [driver],
    ).fetchone()
    if not row:
        return []
    venue, avg_pos, starts, seasons = row
    if avg_pos is None:
        return []
    # Only interesting when the avg is actually good (<= 8 means at least
    # consistently a points finish).
    if avg_pos > 8.0:
        return []
    return [
        Insight(
            category=InsightCategory.SPLIT,
            kind="best_avg_venue",
            subject=driver,
            headline=f"Best venue: {venue} (avg P{avg_pos:.1f} over {int(starts)} starts)",
            payload={
                "venue": venue,
                "avg_position": float(avg_pos),
                "starts": int(starts),
                "seasons": sorted([str(s) for s in seasons], key=_season_sort_key),
            },
            sources=sorted([str(s) for s in seasons], key=_season_sort_key),
        )
    ]


def detect_weekend_multi_podium(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """3+ podiums in a single venue weekend (one set of consecutive races).

    For dominant drivers who do this routinely, fold all but the very best
    weekend into a single aggregate.
    """
    rows = con.execute(
        """
        SELECT season_id, venue,
               COUNT(*) AS podiums,
               SUM(points) AS pts
          FROM race_results
         WHERE driver = ? AND position BETWEEN 1 AND 3
      GROUP BY season_id, venue, venue_order
        HAVING COUNT(*) >= 3
      ORDER BY podiums DESC, pts DESC
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    AGGREGATE_THRESHOLD = 5
    if len(rows) >= AGGREGATE_THRESHOLD:
        seasons = sorted({r[0] for r in rows}, key=_season_sort_key)
        sweep_4 = sum(1 for r in rows if int(r[2]) >= 4)
        best = rows[0]
        return [
            Insight(
                category=InsightCategory.RECORD,
                kind="weekend_multi_podium_career",
                subject=driver,
                headline=(
                    f"{len(rows)} multi-podium weekends "
                    f"({sweep_4} of them four-podium sweeps)"
                ),
                payload={
                    "weekend_count": len(rows),
                    "four_podium_count": sweep_4,
                    "season_count": len(seasons),
                    "seasons": seasons,
                    "best": {
                        "season": best[0],
                        "venue": best[1],
                        "podiums": int(best[2]),
                        "points": int(best[3]),
                    },
                },
                sources=seasons,
            )
        ]

    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="weekend_multi_podium",
            subject=driver,
            headline=f"{int(podiums)} podiums in one weekend at {venue} ({season})",
            payload={
                "season": season,
                "venue": venue,
                "podiums": int(podiums),
                "points": int(pts),
            },
            sources=[season],
        )
        for season, venue, podiums, pts in rows
    ]


def detect_venue_multi_season_podium(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Venues where the driver podiumed in 2+ different seasons.

    A multi-year consistency stat — distinct from `venue_repeat_wins` (which
    counts wins regardless of season) and from `weekend_multi_podium`
    (which is a single-weekend story). For drivers who podium broadly,
    fold into an aggregate plus the most-loaded venue.
    """
    rows = con.execute(
        """
        SELECT venue,
               COUNT(DISTINCT season_id) AS season_count,
               COUNT(*)                  AS podium_count,
               LIST(DISTINCT season_id)  AS seasons
          FROM race_results
         WHERE driver = ? AND position BETWEEN 1 AND 3
      GROUP BY venue
        HAVING COUNT(DISTINCT season_id) >= 2
      ORDER BY season_count DESC, podium_count DESC, venue
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []
    # Sort each venue's season list with the canonical season-ID order.
    rows = [
        (v, sc, pc, sorted([str(s) for s in seasons], key=_season_sort_key))
        for v, sc, pc, seasons in rows
    ]

    AGGREGATE_THRESHOLD = 6
    if len(rows) >= AGGREGATE_THRESHOLD:
        top = rows[0]
        seasons_spanning = sorted(
            {sid for r in rows for sid in r[3]}, key=_season_sort_key
        )
        return [
            Insight(
                category=InsightCategory.RECORD,
                kind="venue_multi_season_podium_career",
                subject=driver,
                headline=(
                    f"Multi-season podium presence at {len(rows)} different venues"
                ),
                payload={
                    "venue_count": len(rows),
                    "season_span": len(seasons_spanning),
                    "top": {
                        "venue": top[0],
                        "season_count": int(top[1]),
                        "podium_count": int(top[2]),
                        "seasons": [str(s) for s in top[3]],
                    },
                    "examples": [
                        {
                            "venue": r[0],
                            "season_count": int(r[1]),
                            "podium_count": int(r[2]),
                        }
                        for r in rows[:3]
                    ],
                },
            )
        ]

    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="venue_multi_season_podium",
            subject=driver,
            headline=(
                f"Podium at {venue} across {int(season_count)} seasons "
                f"({int(podium_count)} podiums total)"
            ),
            payload={
                "venue": venue,
                "season_count": int(season_count),
                "podium_count": int(podium_count),
                "seasons": [str(s) for s in seasons],
            },
            sources=sorted([str(s) for s in seasons], key=_season_sort_key),
        )
        for venue, season_count, podium_count, seasons in rows
    ]
