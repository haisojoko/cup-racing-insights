"""Season-card data shaping — a celebration of one season, for one driver.

Design intent (deliberately different from the analytical cards):

  * Celebration, not comparison. We never render "P14 of 22" — only absolute
    achievements (positions reached, counts, rates). A mid-pack or back-marker
    driver should feel their season was worth completing.
  * Inflate impressiveness honestly. Lead with the strongest true fact. The
    hero auto-picks between best-finish and best-rate so there is always a
    strong headline, even for a winless season.
  * Always something to celebrate. Even a pointless season yields "N races
    completed" and an attendance rate.

All figures come from the existing schema scoped to one season.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from duckdb import DuckDBPyConnection


# Ordinal-position medal tiers. P1–P3 read as podium metal; P4+ is a clean
# numbered badge (no medal styling) so the celebration stays honest.
_MEDAL = {1: "gold", 2: "silver", 3: "bronze"}

_TIER_COPY = {
    "champion": "Championship Season",
    "winning":  "A Winning Season",
    "podium":   "A Podium Season",
    "points":   "A Points-Scoring Season",
    "completed": "Season Completed",
}


@dataclass
class SeasonSummary:
    driver: str
    season_id: str
    season_num: int
    type: str                 # "Formula" | "Sports"
    car: str

    scheduled: int            # races on the season calendar
    starts: int               # races the driver contested
    attendance_pct: float

    points: int
    points_rate: float | None
    points_per_race: float
    scoring_races: int
    scoring_pct: float

    wins: int
    win_rate: float
    podiums: int
    podium_rate: float
    top5: int
    top5_rate: float
    poles: int
    pole_rate: float
    fastest_laps: int
    fastest_lap_rate: float

    best_finish: int | None
    best_finish_count: int
    best_finish_medal: str | None

    is_wdc: bool
    celebration_tier: str
    # Granular-dataset stats (None when the season has no telemetry loaded).
    lap_consistency_cv: float | None = None   # mean per-race lap-time CV %
    season_overtakes: int | None = None       # on-track passes made
    season_contacts: int | None = None        # collisions involved in
    # --all analytical stats (None unless include_all and data present).
    avg_finish: float | None = None           # mean finishing position (started races)
    pace_vs_field_pct: float | None = None     # mean % vs the race field average (− = faster)
    times_overtaken: int | None = None        # on-track passes suffered
    is_wcc: bool = False               # on the WCC-winning team this season
    wcc_team: str | None = None        # winning roster label, e.g. "A + B + C"
    wcc_teammates: list[str] = field(default_factory=list)  # co-winners (not this driver)
    hero: dict[str, Any] = field(default_factory=dict)
    gauges: list[dict[str, Any]] = field(default_factory=list)
    rate_tiles: list[dict[str, Any]] = field(default_factory=list)
    stat_tiles: list[dict[str, Any]] = field(default_factory=list)


def _and_join(names: list[str]) -> str:
    """Human list join: [] → "", [A] → "A", [A,B] → "A & B", [A,B,C] → "A, B & C"."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} & {names[-1]}"


def _wcc_membership(
    con: DuckDBPyConnection, driver: str, season_id: str
) -> tuple[bool, str | None, list[str]]:
    """Was `driver` on the season's WCC-winning team?

    Reads the winning roster from `seasons.wcc` (a "A + B + C" label) and
    checks membership. Returns (is_wcc, roster_label, teammates).

    Defensive by design: minimal in-memory schemas (used in tests) omit the
    `wcc` column, so a lookup failure degrades to "no WCC" rather than raising.
    """
    try:
        row = con.execute(
            "SELECT wcc FROM seasons WHERE season_id = ?", [season_id]
        ).fetchone()
    except Exception:
        return False, None, []
    if not row or not row[0]:
        return False, None, []
    roster = str(row[0]).strip()
    members = [m.strip() for m in roster.split(" + ") if m.strip()]
    dl = driver.lower()
    if not any(m.lower() == dl for m in members):
        return False, None, []
    teammates = [m for m in members if m.lower() != dl]
    return True, roster, teammates


def _race_dataset_stats(
    con: DuckDBPyConnection, driver: str, season_id: str
) -> tuple[float | None, int | None, int | None]:
    """Season lap-consistency (mean CV%), overtakes made, and contacts.

    Reads the granular tables loaded from the JSON dataset. Defensive by design:
    a Markdown-only build (or the minimal in-memory schemas used in tests) omits
    these tables, so any failure degrades to (None, None, None) — no tiles.
    """
    try:
        cv = con.execute(
            "SELECT AVG(cv_pct) FROM race_pace "
            "WHERE driver = ? AND season_id = ? AND laps_used >= 2",
            [driver, season_id],
        ).fetchone()[0]
        ot = con.execute(
            "SELECT COALESCE(SUM(made), 0) FROM race_overtakes "
            "WHERE driver = ? AND season_id = ?",
            [driver, season_id],
        ).fetchone()[0]
        contacts = con.execute(
            "SELECT COALESCE(SUM(contacts), 0) FROM race_contacts "
            "WHERE driver = ? AND season_id = ?",
            [driver, season_id],
        ).fetchone()[0]
    except Exception:  # noqa: BLE001 — tables absent on Markdown-only builds
        return None, None, None
    if cv is None:  # no pace rows for this driver/season
        return None, None, None
    return float(cv), int(ot), int(contacts)


def _all_stats(
    con: DuckDBPyConnection, driver: str, season_id: str
) -> tuple[float | None, float | None, int | None]:
    """`--all` analytical stats: average finish, pace vs the field, times
    overtaken. Discouraging-by-nature, so opt-in. Defensive like the others."""
    try:
        avg_finish = con.execute(
            "SELECT AVG(position) FROM race_results "
            "WHERE driver = ? AND season_id = ? AND NOT dns AND position IS NOT NULL",
            [driver, season_id],
        ).fetchone()[0]
        pace_vs_field = con.execute(
            """
            WITH rep AS (
                SELECT * FROM race_pace WHERE season_id = ? AND laps_used >= 2
            ),
            field AS (
                SELECT venue_order, race_num, AVG(avg_ms) AS field_avg
                  FROM rep GROUP BY venue_order, race_num
            )
            SELECT AVG((r.avg_ms - f.field_avg) / f.field_avg) * 100
              FROM rep r JOIN field f USING (venue_order, race_num)
             WHERE r.driver = ?
            """,
            [season_id, driver],
        ).fetchone()[0]
        overtaken = con.execute(
            "SELECT COALESCE(SUM(suffered), 0) FROM race_overtakes "
            "WHERE driver = ? AND season_id = ?",
            [driver, season_id],
        ).fetchone()[0]
    except Exception:  # noqa: BLE001
        return None, None, None
    return (
        float(avg_finish) if avg_finish is not None else None,
        float(pace_vs_field) if pace_vs_field is not None else None,
        int(overtaken) if overtaken is not None else None,
    )


def _celebration_tier(wins: int, podiums: int, points: int, is_wdc: bool) -> str:
    if is_wdc:
        return "champion"
    if wins > 0:
        return "winning"
    if podiums > 0:
        return "podium"
    if points > 0:
        return "points"
    return "completed"


def build_season_summary(
    con: DuckDBPyConnection, driver: str, season_id: str, include_all: bool = False
) -> SeasonSummary | None:
    """Aggregate one driver's season into a celebration-ready summary.

    Returns None if the season doesn't exist or the driver never appeared.
    Callers should treat None as "nothing to celebrate / bad input".
    """
    season = con.execute(
        "SELECT season_num, type, car, wdc FROM seasons WHERE season_id = ?",
        [season_id],
    ).fetchone()
    if not season:
        return None
    season_num, stype, car, wdc = season

    scheduled = con.execute(
        "SELECT COUNT(DISTINCT (venue_order, race_num)) "
        "FROM race_results WHERE season_id = ?",
        [season_id],
    ).fetchone()[0]

    agg = con.execute(
        """
        SELECT
            COUNT(*) FILTER (WHERE NOT dns)                    AS starts,
            COALESCE(SUM(points), 0)                           AS pts,
            COUNT(*) FILTER (WHERE NOT dns AND points > 0)     AS scoring,
            COUNT(*) FILTER (WHERE position = 1)               AS wins,
            COUNT(*) FILTER (WHERE position BETWEEN 1 AND 3)   AS podiums,
            COUNT(*) FILTER (WHERE position BETWEEN 1 AND 5)   AS top5,
            COALESCE(SUM(CAST(is_pole AS INT)), 0)             AS poles,
            COALESCE(SUM(CAST(is_fastest_lap AS INT)), 0)      AS fls,
            MIN(position) FILTER (WHERE NOT dns)               AS best
        FROM race_results
        WHERE driver = ? AND season_id = ?
        """,
        [driver, season_id],
    ).fetchone()
    starts, pts, scoring, wins, podiums, top5, poles, fls, best = agg
    if (starts or 0) == 0:
        return None  # driver never started a race this season

    best_count = 0
    if best is not None:
        best_count = con.execute(
            "SELECT COUNT(*) FROM race_results "
            "WHERE driver = ? AND season_id = ? AND position = ?",
            [driver, season_id, best],
        ).fetchone()[0]

    attendance_pct = (starts / scheduled) if scheduled else 0.0
    scoring_pct = (scoring / starts) if starts else 0.0
    ppr = (pts / starts) if starts else 0.0
    is_wdc = (wdc or "").strip().lower() == driver.lower()
    is_wcc, wcc_team, wcc_teammates = _wcc_membership(con, driver, season_id)
    lap_cv, season_ot, season_contacts = _race_dataset_stats(con, driver, season_id)
    avg_finish = pace_vs_field = times_overtaken = None
    if include_all:
        avg_finish, pace_vs_field, times_overtaken = _all_stats(con, driver, season_id)

    weighted = con.execute(
        """
        SELECT win_pct, pod_pct, top5_pct, fl_pct, pole_pct, pts_rate
        FROM weighted_scores
        WHERE driver = ? AND season_id = ?
        """,
        [driver, season_id],
    ).fetchone()

    win_rate = wins / starts if starts else 0.0
    podium_rate = podiums / starts if starts else 0.0
    top5_rate = top5 / starts if starts else 0.0
    fastest_lap_rate = fls / starts if starts else 0.0
    pole_rate = poles / starts if starts else 0.0
    points_rate: float | None = None
    if weighted:
        w_win, w_podium, w_top5, w_fl, w_pole, w_points = weighted
        win_rate = float(w_win) if w_win is not None else win_rate
        podium_rate = float(w_podium) if w_podium is not None else podium_rate
        top5_rate = float(w_top5) if w_top5 is not None else top5_rate
        fastest_lap_rate = float(w_fl) if w_fl is not None else fastest_lap_rate
        pole_rate = float(w_pole) if w_pole is not None else pole_rate
        points_rate = float(w_points) if w_points is not None else None

    summary = SeasonSummary(
        driver=driver,
        season_id=season_id,
        season_num=season_num,
        type=stype,
        car=car,
        scheduled=scheduled,
        starts=starts,
        attendance_pct=attendance_pct,
        points=pts,
        points_rate=points_rate,
        points_per_race=ppr,
        scoring_races=scoring,
        scoring_pct=scoring_pct,
        wins=wins,
        win_rate=win_rate,
        podiums=podiums,
        podium_rate=podium_rate,
        top5=top5,
        top5_rate=top5_rate,
        poles=poles,
        pole_rate=pole_rate,
        fastest_laps=fls,
        fastest_lap_rate=fastest_lap_rate,
        best_finish=best,
        best_finish_count=best_count,
        best_finish_medal=_MEDAL.get(best) if best else None,
        is_wdc=is_wdc,
        celebration_tier=_celebration_tier(wins, podiums, pts, is_wdc),
        lap_consistency_cv=lap_cv,
        season_overtakes=season_ot,
        season_contacts=season_contacts,
        avg_finish=avg_finish,
        pace_vs_field_pct=pace_vs_field,
        times_overtaken=times_overtaken,
        is_wcc=is_wcc,
        wcc_team=wcc_team,
        wcc_teammates=wcc_teammates,
    )
    _attach_presentation(summary)
    return summary


def _attach_presentation(s: SeasonSummary) -> None:
    """Build the hero (auto-picked), gauges, and glyph stat tiles."""
    # ---- Hero: auto-pick between best-finish and strongest rate ----------
    # Each candidate scored 0–1 on "impressiveness". A podium finish always
    # wins; for P4+ a strong rate (attendance / points-scoring) can take the
    # headline so a mid-pack driver still leads with something strong.
    finish_strength = 0.0
    if s.best_finish is not None:
        finish_strength = max(0.0, 1.0 - (s.best_finish - 1) * 0.07)

    rate_label, rate_val = ("Attendance", s.attendance_pct)
    if s.scoring_pct > s.attendance_pct:
        rate_label, rate_val = ("Points-scoring rate", s.scoring_pct)

    hero_finish = {
        "kind": "finish",
        "medal": s.best_finish_medal,
        "position": s.best_finish,
        "count": s.best_finish_count,
        "label": "Season-best finish",
    }
    hero_rate = {
        "kind": "rate",
        "label": rate_label,
        "pct": round(rate_val * 100),
    }

    if s.best_finish is None:
        s.hero = dict(hero_rate)
    elif finish_strength >= rate_val:
        s.hero = dict(hero_finish, secondary=hero_rate)
    else:
        s.hero = dict(hero_rate, secondary=hero_finish)

    s.hero["tier_copy"] = _TIER_COPY[s.celebration_tier]
    if s.is_wdc:
        s.hero["crown"] = True
    if s.is_wcc:
        s.hero["wcc"] = True
        s.hero["wcc_with"] = _and_join(s.wcc_teammates)
    # Gold, championship-grade theme for either title (drivers' or constructors').
    s.hero["gold"] = s.is_wdc or s.is_wcc

    # ---- Gauges (donut arcs) — always-positive framing -------------------
    s.gauges = [
        {
            "label": "Races completed",
            "pct": round(s.attendance_pct * 100),
            "center": f"{s.starts}/{s.scheduled}",
        },
        {
            "label": "Points-scoring rate",
            "pct": round(s.scoring_pct * 100),
            "center": f"{round(s.scoring_pct * 100)}%",
        },
    ]

    def pct_text(value: float) -> str:
        return f"{value * 100:.1f}%"

    rate_tiles: list[dict[str, Any]] = []
    if s.points_rate is not None:
        rate_tiles.append({
            "value": pct_text(s.points_rate),
            "label": "Points rate",
        })
    rate_tiles.extend([
        {"value": pct_text(s.win_rate), "label": "Win rate"},
        {"value": pct_text(s.podium_rate), "label": "Podium rate"},
        {"value": pct_text(s.top5_rate), "label": "Top-5 rate"},
    ])
    s.rate_tiles = rate_tiles

    # ---- Stat tiles with glyphs. Only show counts > 0 (no zeros staring
    # back at a back-marker), but always include points + points/race so the
    # card never looks bare.
    tiles: list[dict[str, Any]] = [
        {"glyph": "points", "value": s.points, "label": "Points"},
    ]
    if s.wins:
        tiles.append({"glyph": "trophy", "value": s.wins, "label": "Wins"})
    if s.podiums:
        tiles.append({"glyph": "podium", "value": s.podiums, "label": "Podiums"})
    if s.top5:
        tiles.append({"glyph": "top5", "value": s.top5, "label": "Top-5 finishes"})
    if s.poles:
        tiles.append({"glyph": "pole", "value": s.poles, "label": "Poles"})
    if s.fastest_laps:
        tiles.append({"glyph": "stopwatch", "value": s.fastest_laps, "label": "Fastest laps"})
    tiles.append({
        "glyph": "rate",
        "value": f"{s.points_per_race:.1f}",
        "label": "Points / race",
    })

    # ---- Granular-dataset tiles (only when telemetry exists for the season).
    if s.season_overtakes is not None:
        tiles.append({"glyph": "overtake", "value": s.season_overtakes, "label": "Overtakes"})
    if s.season_contacts:  # hide a clean zero on the celebration card
        tiles.append({"glyph": "contact", "value": s.season_contacts, "label": "Contacts"})
    if s.lap_consistency_cv is not None:
        tiles.append({
            "glyph": "consistency",
            "value": f"{s.lap_consistency_cv:.2f}%",
            "label": "Lap consistency",
        })

    # ---- --all analytical tiles (opt-in; can read as unflattering) --------
    if s.avg_finish is not None:
        tiles.append({"glyph": "finish", "value": f"P{s.avg_finish:.1f}", "label": "Avg finish"})
    if s.pace_vs_field_pct is not None:
        sign = "+" if s.pace_vs_field_pct >= 0 else "−"
        tiles.append({
            "glyph": "speed",
            "value": f"{sign}{abs(s.pace_vs_field_pct):.2f}%",
            "label": "Pace vs field",
        })
    if s.times_overtaken is not None:
        tiles.append({"glyph": "overtaken", "value": s.times_overtaken, "label": "Times overtaken"})
    s.stat_tiles = tiles
