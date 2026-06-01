"""Notability scoring — emotionally-grounded ranker.

The goal is *emotional resonance*, not analytical novelty: insights that
make a driver feel seen, remembered, or singular outrank insights that are
merely clever stats. Five universal axes drive the score:

  1. Identity / belonging  — "I'm one of N to ___"
  2. Memory anchors        — recent races you watched, specific venues
  3. Singularity           — first in league history, sole leader
  4. Narrative tension     — conveyed via recency (we update between seasons)
  5. Resolved struggle     — comebacks, breakthroughs

Five contributors compose the final score additively:

  * `_CATEGORY_BASE`      — emotional weight by InsightCategory
  * `_magnitude_bonus`    — bigger value = bigger story (scale-calibrated)
  * `_rarity_bonus`       — smaller cohort = bigger story
  * `_recency_bonus`      — happened this season or last
  * `_FLAT_BONUSES`       — leader / singular / historic-first framing flags

Per-kind tuning lives in `_RULES`, a declarative table. Adding a new
detector means: write the detector, add ONE row to `_RULES` (or omit and
take the category base), done. No new formulas.

Negative-valence kinds (anything that frames the driver as worst-at /
best-of-the-worst) take a hard `_NEGATIVE_PENALTY` so they only ever
surface when a driver has no positive content.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Insight, InsightCategory


# ---------------------------------------------------------------------------
# Axis 1 — Category emotional weights
# ---------------------------------------------------------------------------
# Rebalanced from the original analytical bases. Categories that anchor
# identity (FIRST_ONLY_LAST), arc-of-career (TRAJECTORY), and memory
# (MILESTONE) get higher bases than analytical splits.

_CATEGORY_BASE: dict[InsightCategory, float] = {
    InsightCategory.FIRST_ONLY_LAST: 0.92,  # identity / singularity
    InsightCategory.HEAD_TO_HEAD:    0.75,  # rivalry = core sports drama
    InsightCategory.ANOMALY:         0.72,  # counter-intuition lands hard
    InsightCategory.TRAJECTORY:      0.55,  # career arcs are personal but can read as decline for mid-pack drivers — kept moderate
    InsightCategory.MILESTONE:       0.70,  # memory anchors
    InsightCategory.RECORD:          0.65,  # strong but impersonal
    InsightCategory.STREAK:          0.60,  # tension peaks mid-streak
    InsightCategory.MARGIN:          0.55,  # comparative, cool
    InsightCategory.PEER_RANK:       0.50,  # only top-3 emotional; leader bonus picks up the slack
    InsightCategory.SPLIT:           0.35,  # analytical, "fun fact" tier
}


# ---------------------------------------------------------------------------
# Axis helpers (reused across kinds)
# ---------------------------------------------------------------------------

def _magnitude_bonus(value: float | int | None, scale: float, cap: float = 0.20) -> float:
    """Bigger value = bigger story.

    Semantic: `value == scale` earns the full `cap` bonus. Smaller values
    scale linearly down; larger values clip at `cap`. So a "30-race streak"
    and a "30-venue sweep career" are comparable on the same notability
    axis if both use `scale=30`. Tune by changing `scale` (and `cap` for
    kinds that should never dominate), not by inventing a new formula.
    """
    if value is None:
        return 0.0
    return min(cap, max(0.0, cap * float(value) / scale))


def _rarity_bonus(cohort_size: int | None, max_bonus: float = 0.20) -> float:
    """Smaller club = bigger story. Stepped — sole-membership earns full bonus.

    The steps reflect how the framing changes: "only driver" reads
    differently from "one of three" reads differently from "one of twelve".
    """
    if cohort_size is None:
        return 0.0
    if cohort_size <= 1:  return max_bonus
    if cohort_size <= 3:  return max_bonus * 0.70
    if cohort_size <= 6:  return max_bonus * 0.40
    if cohort_size <= 12: return max_bonus * 0.20
    return 0.0


def _recency_bonus(sources: list[str] | None, *, current: str, previous: str) -> float:
    """Gradient bonus for recently-occurring insights.

    Current season → +0.15 ("you watched this last week").
    Previous season → +0.08 ("still in recent memory").
    Asymmetric because emotional vividness fades fast.
    """
    if not sources:
        return 0.0
    src = set(sources)
    if current in src:
        return 0.15
    if previous in src:
        return 0.08
    return 0.0


# Story-strength flat bonuses — narrative framing the magnitude/rarity axes
# don't capture on their own.
_FLAT_BONUSES: dict[str, float] = {
    "leader":              0.12,  # sole leader of any cohort
    "singular":            0.15,  # only one driver in the cohort
    "historic_first":      0.12,  # first in league history (milestones)
    "personal_first":      0.08,  # first career win/podium/pole/FL
    "signature_p1":        0.20,  # career-best result is a win
    "signature_p2":        0.10,
    "signature_p3":        0.05,
}


# Negative-valence kinds get this applied as a single hard subtraction.
# Tunable — making it less aggressive lets the worst-X stats surface more
# often. -0.50 puts them well below every positive insight under normal
# conditions; they only appear for drivers with thin positive content.
_NEGATIVE_PENALTY = -0.50
_NEGATIVE_KINDS: frozenset[str] = frozenset({
    "worst_penalty_race",
    "worst_penalty_season",
    "only_winless_with_long_streak",
    "winless_rank_pod_pct",
    "winless_rank_top5_pct",
    "winless_rank_pts_per_race",
})


# ---------------------------------------------------------------------------
# Per-kind scoring rules — the spec lives in this table
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoringRule:
    """Declarative scoring contribution for one insight kind.

    All fields optional — omit what doesn't apply. A kind without an entry
    falls back to its category base + recency bonus only.

    magnitude     -- (payload_field, scale, cap)
    rarity_field  -- payload field containing `cohort_size`
    leader_field  -- payload field containing rank-in-cohort; +0.12 if == 1
    position_field-- payload field containing P-result; signature_pN bonus
    flat_bonuses  -- names from _FLAT_BONUSES to add unconditionally
    """
    magnitude: tuple[str, float, float] | None = None
    rarity_field: str | None = None
    leader_field: str | None = None
    position_field: str | None = None
    flat_bonuses: tuple[str, ...] = ()


_RULES: dict[str, ScoringRule] = {
    # Recalibrated for the new magnitude semantic — "scale" is the value
    # that earns the FULL bonus. Roughly: pick the value at which "this is
    # elite-tier" and use it as scale.

    # --- Streaks
    "top3_streak":              ScoringRule(magnitude=("length", 25, 0.20)),
    "top5_streak":              ScoringRule(magnitude=("length", 35, 0.20)),
    "top10_streak":             ScoringRule(magnitude=("length", 60, 0.20)),
    "points_streak":            ScoringRule(magnitude=("length", 60, 0.20)),
    "in_season_hot_streak":     ScoringRule(magnitude=("length", 12, 0.18)),
    "consecutive_season_bests": ScoringRule(magnitude=("length", 5, 0.15)),
    "seasons_always_scoring":   ScoringRule(magnitude=("season_count", 6, 0.18)),
    "fastest_lap_streak":       ScoringRule(magnitude=("length", 10, 0.18)),
    "consecutive_podium_weekends": ScoringRule(magnitude=("length", 8, 0.18)),

    # --- Records & personal bests
    "career_best_finish":       ScoringRule(position_field="position"),
    "career_best_season":       ScoringRule(),
    "best_season_rank":         ScoringRule(position_field="wdc"),
    "best_venue_weekend":       ScoringRule(),
    "highest_single_race_pts":  ScoringRule(magnitude=("points", 80, 0.15)),
    "largest_win_margin":       ScoringRule(magnitude=("margin", 40, 0.15)),
    "hat_trick_races":          ScoringRule(magnitude=("total", 8, 0.15)),
    "tightest_season_range":    ScoringRule(),
    "season_never_outside_top_n": ScoringRule(),  # tightness encoded in headline; magnitude here would invert awkwardly
    # League records — holding an all-time mark is a top-tier story; the
    # magnitude bump keeps a bigger record (more wins) slightly ahead.
    "league_record_wins_season":     ScoringRule(magnitude=("record", 12, 0.18),
                                                 flat_bonuses=("historic_first",)),
    "league_record_weighted_score":  ScoringRule(flat_bonuses=("historic_first", "singular")),

    # --- Concentrated / majority (ANOMALY: "all in one season")
    "concentrated_poles":   ScoringRule(magnitude=("total", 6, 0.18)),
    "concentrated_fls":     ScoringRule(magnitude=("total", 6, 0.18)),
    "concentrated_wins":    ScoringRule(magnitude=("total", 6, 0.18)),
    "concentrated_podiums": ScoringRule(magnitude=("total", 8, 0.18)),
    "majority_poles":       ScoringRule(magnitude=("total", 10, 0.15)),
    "majority_fls":         ScoringRule(magnitude=("total", 10, 0.15)),
    "majority_wins":        ScoringRule(magnitude=("total", 10, 0.15)),
    "majority_podiums":     ScoringRule(magnitude=("total", 12, 0.15)),

    # --- Firsts (career-defining moments)
    "first_win":            ScoringRule(flat_bonuses=("personal_first",)),
    "first_podium":         ScoringRule(flat_bonuses=("personal_first",)),
    "first_pole":           ScoringRule(flat_bonuses=("personal_first",)),
    "first_fl":             ScoringRule(flat_bonuses=("personal_first",)),
    "most_recent_win":      ScoringRule(),
    "most_recent_podium":   ScoringRule(),
    "most_recent_pole":     ScoringRule(),

    # --- Peer rankings (leader bonus does the work)
    "league_rank_podiums":     ScoringRule(leader_field="rank"),
    "league_rank_poles":       ScoringRule(leader_field="rank"),
    "league_rank_points":      ScoringRule(leader_field="rank"),
    "league_rank_races":       ScoringRule(leader_field="rank"),
    "league_rank_top5":        ScoringRule(leader_field="rank"),
    "distinct_winning_venues": ScoringRule(leader_field="rank"),

    # --- Venues (single-event vs career-aggregate scales differ)
    "venue_pole_sweep":              ScoringRule(magnitude=("poles", 4, 0.15)),
    "venue_pole_sweep_career":       ScoringRule(magnitude=("sweep_count", 20, 0.20)),
    "venue_repeat_wins":             ScoringRule(magnitude=("wins", 5, 0.15)),
    "venue_repeat_wins_career":      ScoringRule(magnitude=("venue_count", 15, 0.20)),
    "best_avg_venue":                ScoringRule(),
    "weekend_multi_podium":          ScoringRule(magnitude=("podiums", 4, 0.15)),
    "weekend_multi_podium_career":   ScoringRule(magnitude=("weekend_count", 20, 0.20)),
    "venue_multi_season_podium":     ScoringRule(magnitude=("season_count", 4, 0.12)),
    "venue_multi_season_podium_career": ScoringRule(magnitude=("venue_count", 15, 0.18)),

    # --- Trajectory
    "best_vs_worst_season":       ScoringRule(magnitude=("spread", 8, 0.12)),
    "consecutive_podium_seasons": ScoringRule(magnitude=("length", 5, 0.18)),

    # --- Splits
    "class_split_podium": ScoringRule(),
    "class_split_ppr":    ScoringRule(),
    "specialist_car":     ScoringRule(magnitude=("starts", 30, 0.10)),

    # --- Uniqueness — rarity + magnitude + leadership combos
    "only_to_pole_sweep":         ScoringRule(magnitude=("sweep_count", 8, 0.15),
                                              rarity_field="cohort_size"),
    "only_race_week_sweep":       ScoringRule(magnitude=("sweep_count", 8, 0.15),
                                              rarity_field="cohort_size"),
    "only_perfect_podium_venue":  ScoringRule(magnitude=("venue_count", 4, 0.15),
                                              rarity_field="cohort_size"),
    "sole_venue_winner":          ScoringRule(magnitude=("venue_count", 4, 0.15)),
    "wins_without_poles":         ScoringRule(magnitude=("wins", 8, 0.15),
                                              rarity_field="cohort_size"),
    "won_both_classes":           ScoringRule(rarity_field="cohort_size"),
    "multiple_wcc_club":          ScoringRule(magnitude=("wcc_titles", 7, 0.20),
                                              rarity_field="cohort_size",
                                              leader_field="rank_in_cohort"),
    "multiple_wdc_club":          ScoringRule(magnitude=("wdc_titles", 5, 0.20),
                                              rarity_field="cohort_size",
                                              leader_field="rank_in_cohort"),
    "first_to_milestone_wins":    ScoringRule(magnitude=("threshold", 100, 0.15),
                                              flat_bonuses=("historic_first",)),
    "first_to_milestone_podiums": ScoringRule(magnitude=("threshold", 200, 0.15),
                                              flat_bonuses=("historic_first",)),
    "first_to_milestone_poles":   ScoringRule(magnitude=("threshold", 100, 0.15),
                                              flat_bonuses=("historic_first",)),

    # --- Penalty (positive only — negatives in _NEGATIVE_KINDS)
    "clean_career": ScoringRule(magnitude=("starts", 100, 0.18)),

    # --- Championship margins / team
    "wcc_contribution":  ScoringRule(magnitude=("pct", 50, 0.20)),
    "decisive_wcc_year": ScoringRule(),
}


# ---------------------------------------------------------------------------
# Scoring entry point
# ---------------------------------------------------------------------------

def _apply_position_bonus(payload: dict, field: str) -> float:
    pos = payload.get(field)
    if pos == 1: return _FLAT_BONUSES["signature_p1"]
    if pos == 2: return _FLAT_BONUSES["signature_p2"]
    if pos == 3: return _FLAT_BONUSES["signature_p3"]
    return 0.0


def score(
    insight: Insight,
    *,
    recent_seasons: set[str] | None = None,
    current_season: str = "S22",
    previous_season: str = "S21",
) -> float:
    """Compute and assign the notability score for one insight.

    `recent_seasons` kept for backwards compatibility — if provided, all
    seasons in it earn the +0.08 (previous) bonus and the latest one earns
    +0.15. Otherwise `current_season` / `previous_season` are used directly.
    """
    base = _CATEGORY_BASE.get(insight.category, 0.40)
    bonus = 0.0

    # Negative valence dominates everything — nothing else matters.
    if insight.kind in _NEGATIVE_KINDS:
        insight.score = round(base + _NEGATIVE_PENALTY, 3)
        return insight.score

    rule = _RULES.get(insight.kind)
    if rule is not None:
        p = insight.payload
        if rule.magnitude:
            field, scale, cap = rule.magnitude
            bonus += _magnitude_bonus(p.get(field), scale, cap)
        if rule.rarity_field:
            bonus += _rarity_bonus(p.get(rule.rarity_field))
        if rule.leader_field and p.get(rule.leader_field) == 1:
            bonus += _FLAT_BONUSES["leader"]
        if rule.position_field:
            bonus += _apply_position_bonus(p, rule.position_field)
        for flag in rule.flat_bonuses:
            bonus += _FLAT_BONUSES.get(flag, 0.0)
        # Note: _rarity_bonus(cohort_size=1) already returns max_bonus,
        # which is greater than the "singular" flat bonus — so cohort=1
        # cases land at the right top-tier weight without extra logic.

    # Recency — use the more recent of provided values if recent_seasons given.
    if recent_seasons:
        # Pick the latest season in the set as "current"; the rest count as
        # previous-tier recency.
        sorted_recent = sorted(recent_seasons, reverse=True)
        cur = sorted_recent[0] if sorted_recent else current_season
        prev = sorted_recent[1] if len(sorted_recent) > 1 else previous_season
        bonus += _recency_bonus(insight.sources, current=cur, previous=prev)
    else:
        bonus += _recency_bonus(insight.sources, current=current_season, previous=previous_season)

    insight.score = round(base + bonus, 3)
    return insight.score


def score_all(
    insights: list[Insight],
    *,
    recent_seasons: set[str] | None = None,
) -> list[Insight]:
    for ins in insights:
        score(ins, recent_seasons=recent_seasons)
    insights.sort(key=lambda i: i.score, reverse=True)
    return insights
