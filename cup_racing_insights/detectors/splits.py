"""Performance-split detectors.

Cross-segment splits often reveal where a driver actually shines.

Two different things get called "class" in this league, and they are kept
apart here:

* **Division** — Formula vs Sports. Cup Racing alternates them season by
  season, so a driver's division profile says which half of the calendar
  suits them. See ``detect_division_split``.
* **Car class** — GT3 / Street / Hypercar *within* a single multi-class
  season, where two classes share one track at very different speeds. See
  ``detect_multi_class_split``.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import PENALTY_POSITION_MIN, Insight, InsightCategory


# Minimum starts per division to compare. Avoid cameos producing 100% rates.
_MIN_STARTS_PER_DIVISION = 10


def detect_division_split(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Compare Formula vs Sports results when the driver has enough of both.

    This is the *division* split — which half of the calendar suits a driver.
    Car class within a multi-class season is a different question; see
    detect_multi_class_split.
    """
    rows = con.execute(
        """
        SELECT s.type AS division,
               COUNT(*)                                          AS starts,
               SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END)   AS wins,
               SUM(CASE WHEN r.position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
               SUM(CASE WHEN r.position BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS top5,
               SUM(r.points)                                     AS pts
          FROM race_results r
          JOIN seasons s USING (season_id)
         WHERE r.driver = ? AND NOT r.dns
      GROUP BY s.type
        """,
        [driver],
    ).fetchall()
    if not rows or len(rows) < 2:
        return []

    by_division = {r[0]: r for r in rows}
    if "Formula" not in by_division or "Sports" not in by_division:
        return []

    f = by_division["Formula"]
    sp = by_division["Sports"]
    if f[1] < _MIN_STARTS_PER_DIVISION or sp[1] < _MIN_STARTS_PER_DIVISION:
        return []

    insights: list[Insight] = []

    def _rates(row):
        _div, starts, wins, pods, top5, pts = row
        return {
            "starts": int(starts),
            "wins": int(wins),
            "podiums": int(pods),
            "top5": int(top5),
            "points": int(pts),
            "pod_rate": pods / starts if starts else 0.0,
            "top5_rate": top5 / starts if starts else 0.0,
            "ppr": pts / starts if starts else 0.0,
        }

    f_r = _rates(f)
    s_r = _rates(sp)

    # Significant podium rate differential
    diff = abs(f_r["pod_rate"] - s_r["pod_rate"])
    if diff >= 0.05 and (f_r["podiums"] + s_r["podiums"]) >= 3:
        leader, other = ("Formula", "Sports") if f_r["pod_rate"] > s_r["pod_rate"] else ("Sports", "Formula")
        leader_pct = max(f_r["pod_rate"], s_r["pod_rate"]) * 100
        other_pct = min(f_r["pod_rate"], s_r["pod_rate"]) * 100
        ratio = (leader_pct / other_pct) if other_pct > 0 else None
        insights.append(
            Insight(
                category=InsightCategory.SPLIT,
                kind="division_split_podium",
                subject=driver,
                headline=(
                    f"{leader} podium rate {leader_pct:.1f}% "
                    f"vs {other} {other_pct:.1f}%"
                ),
                payload={
                    "leader": leader,
                    "other": other,
                    "leader_pct": leader_pct,
                    "other_pct": other_pct,
                    "ratio": ratio,
                    "formula": f_r,
                    "sports": s_r,
                },
            )
        )

    # Significant ppr differential
    if abs(f_r["ppr"] - s_r["ppr"]) >= 2.0:
        leader, other = ("Formula", "Sports") if f_r["ppr"] > s_r["ppr"] else ("Sports", "Formula")
        leader_v = max(f_r["ppr"], s_r["ppr"])
        other_v = min(f_r["ppr"], s_r["ppr"])
        insights.append(
            Insight(
                category=InsightCategory.SPLIT,
                kind="division_split_ppr",
                subject=driver,
                headline=(
                    f"{leader} pts/race {leader_v:.1f} vs {other} {other_v:.1f}"
                ),
                payload={
                    "leader": leader,
                    "other": other,
                    "leader_value": leader_v,
                    "other_value": other_v,
                    "formula": f_r,
                    "sports": s_r,
                },
            )
        )

    return insights


def detect_specialist_car(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Best-performing specific car the driver has driven (min 3 starts).

    Prefer the race-level car where a table lists one, but fall back to the
    season registry car for single-spec seasons whose result tables omit the
    car column.
    """
    rows = con.execute(
        f"""
        WITH raw_results AS (
            SELECT COALESCE(NULLIF(TRIM(r.car), ''), NULLIF(TRIM(s.car), '')) AS car,
                   r.position,
                   r.points
              FROM race_results r
              JOIN seasons s USING (season_id)
             WHERE r.driver = ?
               AND NOT r.dns
        ),
        results AS (
            SELECT car,
                   LOWER(car) AS car_key,
                   position,
                   points
              FROM raw_results
             WHERE car IS NOT NULL
        )
        SELECT MIN(car)                                         AS car,
               COUNT(*)                                          AS starts,
               SUM(CASE WHEN position = 1 THEN 1 ELSE 0 END)     AS wins,
               SUM(CASE WHEN position BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS podiums,
               SUM(CASE WHEN position BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS top5,
               -- A stewards' penalty placement is a start and keeps its points,
               -- but it is not a finishing position, so it is averaged out only.
               AVG(CASE WHEN position < {PENALTY_POSITION_MIN} THEN position END) AS avg_pos,
               SUM(points)                                       AS pts
          FROM results
         WHERE car_key NOT IN ('—', 'tbd', 'maybe')
      GROUP BY car_key
        HAVING starts >= 3
        """,
        [driver],
    ).fetchall()
    if not rows:
        return []

    # Rank by points-per-start as the headline criterion; ties broken by
    # raw podium count.
    ranked = sorted(
        rows,
        key=lambda r: (-(r[6] / r[1] if r[1] else 0), -(r[3] or 0)),
    )
    top = ranked[0]
    car, starts, wins, podiums, top5, avg_pos, pts = top
    ppr = pts / starts if starts else 0.0

    # Don't bother surfacing if there's no clear standout (e.g. driver only
    # ever drove one car at all).
    if len(ranked) < 2 and starts < 4:
        return []

    return [
        Insight(
            category=InsightCategory.SPLIT,
            kind="specialist_car",
            subject=driver,
            headline=(
                f"Strongest car: {car} ({ppr:.1f} pts/start across {int(starts)} races)"
            ),
            payload={
                "car": car,
                "starts": int(starts),
                "wins": int(wins),
                "podiums": int(podiums),
                "top5": int(top5),
                "avg_position": float(avg_pos) if avg_pos is not None else None,
                "points": int(pts),
                "points_per_start": ppr,
                "alternatives": [
                    {
                        "car": r[0],
                        "starts": int(r[1]),
                        "podiums": int(r[3]),
                        "points_per_start": (r[6] / r[1]) if r[1] else 0.0,
                    }
                    for r in ranked[1:4]
                ],
            },
        )
    ]


# A multi-class season is short — four venues — so the bar for "raced enough of
# it to say anything" has to be lower than the division split's. Below this the
# comparison is one bad weekend, not a pattern.
_MIN_STARTS_IN_CLASS = 4


def detect_multi_class_split(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """How the driver fared against their own class in a multi-class season.

    On a multi-class season the overall finishing order mixes cars that were
    never racing each other — at S14 Sachsenring the two classes were 16
    seconds a lap apart — so a raw finishing position understates a driver in
    the slower class. This recovers the reading that matters: where they came
    within their class, and whether their class was the quick one.

    Results come from the hand-audited Markdown archive (the truth source for
    standings, and complete even where server logs were lost). The class label
    comes from the race dataset, where it is declared per season by league
    rule. Seasons with no declared classes produce nothing.

    **What `position` means depends on the season.** The archive records the
    position that decided the championship, so on a split season (S14, S24a)
    that is the *class* position — S14 has exactly two P1s in all sixteen of
    its races — while on a combined season (S18a/b) it is the overall order.
    ``position_basis`` in the payload says which, and the two must never be
    compared across seasons without checking it.
    """
    rows = con.execute(
        f"""
        SELECT dc.season_id,
               dc.car_class,
               dc.championship,
               COUNT(*)                                                   AS starts,
               SUM(CASE WHEN r.position = 1 THEN 1 ELSE 0 END)            AS wins,
               SUM(r.points)                                              AS points,
               AVG(CASE WHEN r.position < {PENALTY_POSITION_MIN}
                        THEN CAST(r.position AS DOUBLE) END)              AS avg_finish
          FROM race_results r
          JOIN driver_classes dc
            ON dc.season_id = r.season_id AND dc.driver = r.driver
         WHERE r.driver = ? AND NOT r.dns AND r.position IS NOT NULL
      GROUP BY dc.season_id, dc.car_class, dc.championship
        HAVING COUNT(*) >= ?
        """,
        [driver, _MIN_STARTS_IN_CLASS],
    ).fetchall()
    if not rows:
        return []

    insights: list[Insight] = []
    for season_id, car_class, championship, starts, wins, points, avg_finish in rows:
        # See the docstring: a split season's archive positions are already
        # class positions, so "P1" there means "won the class", not the race.
        basis = "class" if championship == "split" else "overall"
        # Size of each class that season, and how the driver's class compares
        # on pace. Both come from the same season so they are directly
        # comparable; a class of one is not a field and is reported as such.
        field = con.execute(
            """
            SELECT car_class, COUNT(*) AS drivers
              FROM driver_classes
             WHERE season_id = ?
          GROUP BY car_class
            """,
            [season_id],
        ).fetchall()
        sizes = {c: int(n) for c, n in field}
        if len(sizes) < 2:
            continue

        others = {c: n for c, n in sizes.items() if c != car_class}
        rival_class = max(others, key=lambda c: others[c]) if others else ""

        insights.append(
            Insight(
                category=InsightCategory.SPLIT,
                kind="multi_class_split",
                subject=driver,
                headline=(
                    f"{season_id}: ran {car_class} against {sizes[car_class] - 1} "
                    f"class rival{'s' if sizes[car_class] != 2 else ''}"
                ),
                body=(
                    f"{season_id} ran {car_class} and {rival_class} together"
                    f"{' with a title in each class' if championship == 'split' else ' under one championship'}. "
                    f"Positions are {basis} positions."
                ),
                payload={
                    "season_id": season_id,
                    "car_class": car_class,
                    "championship": championship,
                    "position_basis": basis,
                    "class_size": sizes[car_class],
                    "rival_class": rival_class,
                    "rival_class_size": sizes.get(rival_class, 0),
                    "starts": int(starts),
                    "wins": int(wins),
                    "points": int(points),
                    "avg_finish": round(float(avg_finish), 2),
                    "class_sizes": sizes,
                },
            )
        )

    return insights
