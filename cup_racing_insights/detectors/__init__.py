"""Insight detectors. Each module exports detector functions that take a
DuckDB connection + a driver name and return a list of Insight objects.

Add new detectors by:
  1. Writing a function with signature `(con, driver) -> list[Insight]`.
  2. Registering it in ALL_DETECTORS below.
"""

from __future__ import annotations

from typing import Callable

from duckdb import DuckDBPyConnection

from ..models import Insight
from . import (
    consistency,
    firsts,
    margins,
    peer_rank,
    penalty,
    personal_best,
    splits,
    streak,
    trajectory,
    uniqueness,
    venue,
)

DetectorFn = Callable[[DuckDBPyConnection, str], list[Insight]]

ALL_DETECTORS: list[DetectorFn] = [
    # Streaks
    streak.detect_top_n_streak,
    streak.detect_consecutive_points_streak,
    streak.detect_in_season_hot_streak,
    streak.detect_consecutive_season_bests,
    streak.detect_seasons_always_scoring,
    streak.detect_fastest_lap_streak,
    streak.detect_consecutive_podium_weekends,
    # Personal bests / records
    personal_best.detect_career_best_finish,
    personal_best.detect_best_season,
    personal_best.detect_best_venue_weekend,
    personal_best.detect_highest_single_race_points,
    personal_best.detect_largest_win_margin,
    personal_best.detect_hat_trick_races,
    personal_best.detect_concentrated_records,
    personal_best.detect_league_record_wins_season,
    personal_best.detect_league_record_weighted_score,
    # Firsts / lasts
    firsts.detect_career_firsts,
    firsts.detect_career_lasts,
    # Peer rankings
    peer_rank.detect_among_winless_peers,
    peer_rank.detect_distinct_venues_won,
    peer_rank.detect_among_all_drivers,
    # Venue dominance
    venue.detect_venue_pole_sweep,
    venue.detect_venue_repeat_wins,
    venue.detect_best_avg_venue,
    venue.detect_weekend_multi_podium,
    venue.detect_venue_multi_season_podium,
    # Trajectory
    trajectory.detect_best_vs_worst_season,
    trajectory.detect_consecutive_podium_seasons,
    trajectory.detect_personal_best_season_rank,
    # Splits
    splits.detect_car_class_split,
    splits.detect_specialist_car,
    # Consistency
    consistency.detect_tightest_season_range,
    consistency.detect_season_never_outside_top_n,
    # Uniqueness (league-wide)
    uniqueness.detect_only_to_pole_sweep,
    uniqueness.detect_only_winless_with_long_streak,
    uniqueness.detect_sole_venue_winner,
    uniqueness.detect_first_to_milestone,
    uniqueness.detect_wins_without_poles,
    uniqueness.detect_won_both_classes,
    uniqueness.detect_multiple_wcc_club,
    uniqueness.detect_multiple_wdc_club,
    uniqueness.detect_only_race_week_sweep,
    uniqueness.detect_only_perfect_podium_venue,
    # Penalties
    penalty.detect_penalty_summary,
    # Championship margins
    margins.detect_wcc_contribution,
    margins.detect_decisive_wcc_year,
]


def run_all(con: DuckDBPyConnection, driver: str) -> list[Insight]:
    out: list[Insight] = []
    for fn in ALL_DETECTORS:
        try:
            out.extend(fn(con, driver))
        except Exception as e:  # noqa: BLE001
            print(f"[detector {fn.__name__} failed for {driver}]: {e}")
    return out


__all__ = ["ALL_DETECTORS", "run_all", "DetectorFn"]
