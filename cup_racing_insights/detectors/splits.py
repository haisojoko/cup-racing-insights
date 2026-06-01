"""Performance-split detectors.

Cross-segment splits often reveal where a driver actually shines. Cup Racing
alternates Formula and Sports car seasons, so a driver's class-by-class
profile is genuinely informative.
"""

from __future__ import annotations

from duckdb import DuckDBPyConnection

from ..models import Insight, InsightCategory


# Minimum starts per class to compare. Avoid cameos producing 100% rates.
_MIN_STARTS_PER_CLASS = 10


def detect_car_class_split(
    con: DuckDBPyConnection, driver: str
) -> list[Insight]:
    """Compare Formula vs Sports car results when the driver has enough of both."""
    rows = con.execute(
        """
        SELECT s.type AS class,
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

    by_class = {r[0]: r for r in rows}
    if "Formula" not in by_class or "Sports" not in by_class:
        return []

    f = by_class["Formula"]
    sp = by_class["Sports"]
    if f[1] < _MIN_STARTS_PER_CLASS or sp[1] < _MIN_STARTS_PER_CLASS:
        return []

    insights: list[Insight] = []

    def _rates(row):
        _cls, starts, wins, pods, top5, pts = row
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
                kind="class_split_podium",
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
                kind="class_split_ppr",
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
        """
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
               AVG(position)                                     AS avg_pos,
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
