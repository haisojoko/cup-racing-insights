"""Personal-best / record-type detectors.

Surface the most "trophy-worthy" extremes for a single driver:
  - Best career race finish (with all ties so we don't lose the count)
  - Best single season (by points)
  - Best venue weekend (highest single-venue point total)
  - Concentrated records (stats compressed into a single season — e.g.
    "all 6 career poles came in S20")
"""

from __future__ import annotations

import re

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


def _season_sort_key(sid: str) -> tuple[int, str]:
    """Return a numeric sort key for season IDs like 'S1', 'S18a', 'S18b'."""
    m = re.match(r"^S(\d+)([a-z]?)$", sid or "")
    if not m:
        return (9999, sid)
    return (int(m.group(1)), m.group(2))


def detect_career_best_finish(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """The driver's best career finishing position (only meaningful if no win)."""
    row = con.execute(
        """
        SELECT MIN(position)
        FROM race_results
        WHERE driver = ? AND position IS NOT NULL AND NOT dns
        """,
        [driver],
    ).fetchone()
    if not row or row[0] is None:
        return []

    best = row[0]
    occurrences = con.execute(
        """
        SELECT r.season_id, r.venue, r.race_num, r.points,
               r.is_pole, r.is_fastest_lap
        FROM race_results r
        JOIN seasons s USING (season_id)
        WHERE r.driver = ? AND r.position = ?
        ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
        """,
        [driver, best],
    ).fetchall()

    # When a driver has dozens or hundreds of occurrences (e.g. wins),
    # listing them all bloats the snippet. Cap the shown occurrences and
    # keep the full count in the payload for the template to summarise.
    MAX_SHOWN = 5
    shown = occurrences[:MAX_SHOWN]
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="career_best_finish",
            subject=driver,
            headline=f"Career-best finish: P{best} (×{len(occurrences)})",
            payload={
                "position": best,
                "count": len(occurrences),
                "shown_count": len(shown),
                "occurrences": [
                    {
                        "season": o[0],
                        "venue": o[1],
                        "race": o[2],
                        "points": o[3],
                        "pole": o[4],
                        "fl": o[5],
                    }
                    for o in shown
                ],
                "first_occurrence": {
                    "season": occurrences[0][0],
                    "venue": occurrences[0][1],
                    "race": occurrences[0][2],
                },
                "latest_occurrence": {
                    "season": occurrences[-1][0],
                    "venue": occurrences[-1][1],
                    "race": occurrences[-1][2],
                },
            },
            sources=list({o[0] for o in occurrences}),
        )
    ]


def detect_best_season(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    """Best season by weighted score, joined with raw season totals.

    The weighted score blends win/podium/top-5 rate, points-per-race, and
    pole/FL rate — normalised against the best driver in that season — and
    is a much fairer "best campaign" measure than raw points (which favours
    longer seasons regardless of competitive quality).
    """
    row = con.execute(
        """
        WITH ws AS (
          SELECT season_id, weighted_score
            FROM weighted_scores
           WHERE driver = ?
        ORDER BY weighted_score DESC
           LIMIT 1
        ),
        season_totals AS (
          SELECT r.season_id,
                 SUM(r.points)                                      AS points,
                 SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END)    AS wins,
                 SUM(CASE WHEN r.position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
                 SUM(CASE WHEN r.position BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS top5,
                 SUM(CASE WHEN r.is_pole THEN 1 ELSE 0 END)         AS poles,
                 SUM(CASE WHEN r.is_fastest_lap THEN 1 ELSE 0 END)  AS fls,
                 SUM(CASE WHEN NOT r.dns THEN 1 ELSE 0 END)         AS starts
            FROM race_results r
           WHERE r.driver = ?
        GROUP BY r.season_id
        )
        SELECT ws.season_id, ws.weighted_score, st.points, st.wins, st.podiums,
               st.top5, st.poles, st.fls, st.starts
          FROM ws
          JOIN season_totals st USING (season_id)
        """,
        [driver, driver],
    ).fetchone()
    if not row:
        return []

    season_id, weighted_score, points, wins, podiums, top5, poles, fls, starts = row
    if starts == 0:
        return []
    top5_rate = top5 / starts if starts else 0.0
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="career_best_season",
            subject=driver,
            headline=(
                f"Career-best season: {season_id} "
                f"(weighted score {weighted_score:.3f})"
            ),
            payload={
                "season": season_id,
                "weighted_score": float(weighted_score),
                "points": int(points),
                "wins": int(wins),
                "podiums": int(podiums),
                "top5": int(top5),
                "poles": int(poles),
                "fls": int(fls),
                "starts": int(starts),
                "top5_rate": top5_rate,
            },
            sources=[season_id],
        )
    ]


def detect_best_venue_weekend(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Highest point haul in a single venue weekend."""
    row = con.execute(
        """
        SELECT r.season_id, r.venue, SUM(r.points) AS pts,
               SUM(CASE WHEN r.position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
               COUNT(*) AS races
          FROM race_results r
         WHERE r.driver = ?
      GROUP BY r.season_id, r.venue, r.venue_order
      ORDER BY pts DESC, podiums DESC
         LIMIT 1
        """,
        [driver],
    ).fetchone()
    if not row or (row[2] or 0) == 0:
        return []
    season_id, venue, pts, podiums, races = row
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="best_venue_weekend",
            subject=driver,
            headline=f"Best weekend: {int(pts)} pts at {venue} ({season_id})",
            payload={
                "season": season_id,
                "venue": venue,
                "points": int(pts),
                "podiums": int(podiums),
                "races": int(races),
            },
            sources=[season_id],
        )
    ]


def detect_highest_single_race_points(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Single race with the biggest point haul (P, FL bonuses included).

    Surfaces all ties on the same date order; uses the earliest occurrence
    for the headline.
    """
    row = con.execute(
        """
        SELECT r.season_id, r.venue, r.race_num, r.position, r.points,
               r.is_pole, r.is_fastest_lap
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND NOT r.dns
      ORDER BY r.points DESC, s.season_num, s.season_sub, r.venue_order, r.race_num
         LIMIT 1
        """,
        [driver],
    ).fetchone()
    if not row or (row[4] or 0) <= 0:
        return []
    season_id, venue, race_num, position, points, pole, fl = row
    if points < 25:
        return []  # too modest to be a "career-high points" story
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="highest_single_race_pts",
            subject=driver,
            headline=(
                f"Highest single-race haul: {int(points)} pts at "
                f"{venue} R{int(race_num)} ({season_id})"
            ),
            payload={
                "season": season_id,
                "venue": venue,
                "race": int(race_num),
                "position": int(position) if position is not None else None,
                "points": int(points),
                "pole": bool(pole),
                "fl": bool(fl),
            },
            sources=[season_id],
        )
    ]


def detect_largest_win_margin(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Biggest point gap between the driver's win and P2 in the same race.

    Naturally captures dominant lights-to-flag wins with bonuses.
    """
    row = con.execute(
        """
        WITH driver_wins AS (
          SELECT season_id, venue, venue_order, race_num, points AS win_points
            FROM race_results
           WHERE driver = ? AND position = 1
        ),
        p2_in_same_race AS (
          SELECT r.season_id, r.venue, r.venue_order, r.race_num,
                 MAX(r.points) AS p2_points
            FROM race_results r
            JOIN driver_wins w
              ON  r.season_id   = w.season_id
              AND r.venue       = w.venue
              AND r.venue_order = w.venue_order
              AND r.race_num    = w.race_num
           WHERE r.position = 2
        GROUP BY r.season_id, r.venue, r.venue_order, r.race_num
        )
        SELECT w.season_id, w.venue, w.race_num,
               w.win_points, p.p2_points,
               (w.win_points - p.p2_points) AS margin
          FROM driver_wins w
          JOIN p2_in_same_race p USING (season_id, venue, venue_order, race_num)
      ORDER BY margin DESC
         LIMIT 1
        """,
        [driver],
    ).fetchone()
    if not row:
        return []
    season_id, venue, race_num, win_pts, p2_pts, margin = row
    if margin < 5:
        return []
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="largest_win_margin",
            subject=driver,
            headline=(
                f"Biggest winning margin: {int(margin)} pts over P2 at "
                f"{venue} R{int(race_num)} ({season_id})"
            ),
            payload={
                "season": season_id,
                "venue": venue,
                "race": int(race_num),
                "win_points": int(win_pts),
                "p2_points": int(p2_pts),
                "margin": int(margin),
            },
            sources=[season_id],
        )
    ]


def detect_hat_trick_races(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Races where the driver took pole, fastest lap AND the win.

    This is F1's "hat-trick" (pole + fastest lap + win in the same race) —
    not to be confused with the triple crown (wins at three landmark events).

    For dominant drivers, returns a single aggregate; otherwise lists
    individual examples.
    """
    rows = con.execute(
        """
        SELECT r.season_id, r.venue, r.race_num
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ?
           AND r.position = 1
           AND r.is_pole
           AND r.is_fastest_lap
      ORDER BY s.season_num, s.season_sub, r.venue_order, r.race_num
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    if len(rows) >= 4:
        seasons = sorted({r[0] for r in rows}, key=_season_sort_key)
        return [
            Insight(
                category=InsightCategory.RECORD,
                kind="hat_trick_races",
                subject=driver,
                headline=(
                    f"{len(rows)} career hat-tricks "
                    f"(pole + FL + win in the same race)"
                ),
                payload={
                    "total": len(rows),
                    "season_count": len(seasons),
                    "first": {"season": rows[0][0], "venue": rows[0][1], "race": rows[0][2]},
                    "latest": {"season": rows[-1][0], "venue": rows[-1][1], "race": rows[-1][2]},
                },
                sources=seasons,
            )
        ]

    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="hat_trick_races",
            subject=driver,
            headline=(
                f"{len(rows)} hat-trick{'s' if len(rows) != 1 else ''} "
                f"(pole + FL + win)"
            ),
            payload={
                "total": len(rows),
                "races": [
                    {"season": r[0], "venue": r[1], "race": int(r[2])} for r in rows
                ],
            },
            sources=[r[0] for r in rows],
        )
    ]


def detect_concentrated_records(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Detect stats heavily concentrated in a single season.

    e.g. "All 6 career poles came in S20." This is the kind of thing that
    feels obvious in hindsight but is invisible at a glance.
    """
    out: list[Insight] = []
    targets = [
        ("poles", "is_pole", "pole"),
        ("fls", "is_fastest_lap", "fastest lap"),
        ("wins", "position = 1", "race win"),
        ("podiums", "position BETWEEN 1 AND 3", "podium"),
    ]
    for name, predicate, label in targets:
        total = con.execute(
            f"""
            SELECT COUNT(*) FROM race_results
            WHERE driver = ? AND ({predicate})
            """,
            [driver],
        ).fetchone()[0]
        if total < 3:
            continue
        # which season holds the most?
        row = con.execute(
            f"""
            SELECT r.season_id, COUNT(*) AS cnt
              FROM race_results r
             WHERE r.driver = ? AND ({predicate})
          GROUP BY r.season_id
          ORDER BY cnt DESC
             LIMIT 1
            """,
            [driver],
        ).fetchone()
        if not row:
            continue
        season_id, cnt = row
        if cnt == total:
            # Total concentration — all of them in one season
            out.append(
                Insight(
                    category=InsightCategory.FIRST_ONLY_LAST,
                    kind=f"concentrated_{name}",
                    subject=driver,
                    headline=f"All {total} career {label}s came in {season_id}",
                    payload={
                        "stat": name,
                        "label": label,
                        "total": int(total),
                        "season": season_id,
                    },
                    sources=[season_id],
                )
            )
        elif cnt / total >= 0.5 and total >= 4:
            # Heavy concentration — majority in one season
            out.append(
                Insight(
                    category=InsightCategory.SPLIT,
                    kind=f"majority_{name}",
                    subject=driver,
                    headline=f"{cnt}/{total} career {label}s came in {season_id}",
                    payload={
                        "stat": name,
                        "label": label,
                        "season_count": int(cnt),
                        "total": int(total),
                        "season": season_id,
                    },
                    sources=[season_id],
                )
            )
    return out


def detect_league_record_wins_season(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """League record for most race wins in a single season.

    Fires only for the driver(s) who hold (or tie) the all-time record, so
    it reads as a celebration of holding the mark rather than a ranking.
    """
    per_driver_season = con.execute(
        """
        SELECT driver, season_id, COUNT(*) AS wins
          FROM race_results
         WHERE position = 1
      GROUP BY driver, season_id
        """
    ).fetchall()
    if not per_driver_season:
        return []

    record = max(int(r[2]) for r in per_driver_season)
    if record <= 0:
        return []
    holders = {r[0] for r in per_driver_season if int(r[2]) == record}
    if driver not in holders:
        return []

    # The driver's own record-equalling season(s).
    mine = sorted(
        [r[1] for r in per_driver_season if r[0] == driver and int(r[2]) == record],
        key=_season_sort_key,
    )
    shared = len(holders) > 1
    headline = (
        f"League record: {record} race wins in a single season ({mine[0]})"
    )
    if shared:
        headline += f" — shared with {len(holders) - 1} other"
        headline += "s" if len(holders) - 1 != 1 else ""
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="league_record_wins_season",
            subject=driver,
            headline=headline,
            payload={
                "record": record,
                "seasons": mine,
                "shared_with": len(holders) - 1,
            },
            sources=mine,
        )
    ]


def detect_league_record_weighted_score(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """League record for the highest single-season weighted score ever.

    Fires only for the holder. The weighted score is the league's composite
    season-quality metric, so holding the all-time peak is a standout claim.
    """
    top = con.execute(
        """
        SELECT driver, season_id, weighted_score
          FROM weighted_scores
      ORDER BY weighted_score DESC
         LIMIT 1
        """
    ).fetchone()
    if not top:
        return []
    rec_driver, rec_season, rec_score = top
    if rec_driver != driver:
        return []
    return [
        Insight(
            category=InsightCategory.RECORD,
            kind="league_record_weighted_score",
            subject=driver,
            headline=(
                f"League record: highest single-season weighted score ever "
                f"({float(rec_score):.3f}, {rec_season})"
            ),
            payload={
                "weighted_score": float(rec_score),
                "season": rec_season,
            },
            sources=[rec_season],
        )
    ]
