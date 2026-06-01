"""Cards: themed groupings of insight kinds that drive rendered output.

A card is a named, editorial-angle collection of insight kinds with its own
per-section cap. Cards solve the cross-category competition problem: a
driver with strong content in every category no longer has to crowd-out
one category to fit another into a single ranked list.

Detectors stay unchanged — they still produce one big list, scored by
notability. Cards filter and group at the render layer.

Insight kinds may appear in multiple cards. An insight is rendered at most
once per card; diversification still runs within each card.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    """A named themed grouping of insight kinds.

    Attributes
    ----------
    name           CLI flag value (e.g. "streaks").
    title          Section header rendered above the card's items.
    description    Used by `cri cards` to list available cards.
    include_kinds  Insight `kind` values this card surfaces. Order does not
                   matter — items are scored by notability inside the card.
    max_items      Default per-card cap. Overridable via --per-card.
    per_kind       Diversification cap inside this card. Cards that genuinely
                   want repetition (uniqueness, firsts) can raise this above
                   the default of 2.
    per_category   Diversification cap by Insight category inside this card.
                   Single-category cards (uniqueness, firsts) need this
                   relaxed or they hit the cap with unrelated kinds.
    """

    name: str
    title: str
    description: str
    include_kinds: tuple[str, ...]
    max_items: int = 5
    per_kind: int = 2
    per_category: int = 4


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

CARDS: dict[str, Card] = {
    "snapshot": Card(
        name="snapshot",
        title="Snapshot",
        description="Quick overview of who the driver is.",
        include_kinds=(
            "career_best_finish",
            "career_best_season",
            "best_season_rank",
            "league_rank_podiums",
            "league_rank_points",
        ),
        max_items=3,
    ),
    "streaks": Card(
        name="streaks",
        title="Streaks",
        description="Longest consecutive runs of strong (or weak) results.",
        include_kinds=(
            "top3_streak",
            "top5_streak",
            "top10_streak",
            "points_streak",
            "consecutive_podium_seasons",
            "season_never_outside_top_n",
            # Reserved for future Tier 1 detectors:
            "winless_streak",
            "podiumless_streak",
            "poleless_streak",
            "in_season_hot_streak",
            "in_season_cold_streak",
            "consecutive_season_bests",
            "seasons_always_scoring",
        ),
        max_items=5,
    ),
    "records": Card(
        name="records",
        title="Records & Personal Bests",
        description="Career highs and standout single performances.",
        include_kinds=(
            "career_best_finish",
            "career_best_season",
            "best_venue_weekend",
            "best_season_rank",
            "tightest_season_range",
            "concentrated_poles",
            "concentrated_fls",
            "concentrated_wins",
            "concentrated_podiums",
            "majority_poles",
            "majority_fls",
            "majority_wins",
            "majority_podiums",
            # Reserved:
            "highest_single_race_pts",
            "largest_win_margin",
            "triple_crown_weekends",
            "career_high_finish",
            "career_low_finish",
        ),
        max_items=5,
    ),
    "venues": Card(
        name="venues",
        title="Venue Profile",
        description="Track-by-track strengths, sweeps, and weekend storylines.",
        include_kinds=(
            "venue_pole_sweep",
            "venue_pole_sweep_career",
            "venue_repeat_wins",
            "venue_repeat_wins_career",
            "best_avg_venue",
            "weekend_multi_podium",
            "weekend_multi_podium_career",
            "venue_multi_season_podium",
            "venue_multi_season_podium_career",
            # Reserved:
            "worst_avg_venue",
            "venue_career_podiums",
            "first_time_venue_performance",
            "pole_sweep_weekend_streak",
            "lowest_variance_venue",
            "distinct_winning_venues",
        ),
        max_items=5,
    ),
    "trajectory": Card(
        name="trajectory",
        title="Career Trajectory",
        description="The career-arc story: range, progression, longevity.",
        include_kinds=(
            "best_vs_worst_season",
            "consecutive_podium_seasons",
            "best_season_rank",
            # Reserved:
            "biggest_yoy_jump",
            "biggest_yoy_decline",
            "late_career_resurgence",
            "career_half_split",
            "career_tenure",
            "consecutive_improving_seasons",
            "outperformance_season",
            "underperformance_season",
            "career_peak_year",
            "wdc_margin_won",
            "wdc_margin_lost",
        ),
        max_items=4,
    ),
    "peer-rank": Card(
        name="peer-rank",
        title="League & Peer Standing",
        description="Where the driver sits relative to peers and the league.",
        include_kinds=(
            "winless_rank_pod_pct",
            "winless_rank_top5_pct",
            "winless_rank_pts_per_race",
            "league_rank_podiums",
            "league_rank_poles",
            "league_rank_points",
            "league_rank_races",
            "league_rank_top5",
            # Reserved:
            "league_rank_wins",
            "league_rank_fls",
            "league_rank_wdc",
            "league_rank_wcc",
            "active_rank_pod_pct",
            "active_rank_top5_pct",
            "active_rank_pts_per_race",
            "distinct_winning_venues",
        ),
        max_items=5,
    ),
    "firsts": Card(
        name="firsts",
        title="Firsts, Lasts & Milestones",
        description="Career debuts, recent firsts/lasts, round-number milestones.",
        include_kinds=(
            "first_win",
            "first_podium",
            "first_pole",
            "first_fl",
            "most_recent_win",
            "most_recent_podium",
            "most_recent_pole",
            "debut_race",
            "career_high_finish",
            "career_low_finish",
            # Milestone kinds (reserved for D-020–D-023):
            "race_milestone_50",
            "race_milestone_100",
            "race_milestone_200",
            "podium_milestone_25",
            "podium_milestone_50",
            "podium_milestone_100",
            "points_milestone_1000",
            "points_milestone_5000",
            "points_milestone_10000",
            "first_50pct_top5_season",
            "first_0_5_ws_season",
        ),
        max_items=8,
        # Firsts are mostly unique kinds; relax category cap so all four
        # firsts + all three lasts don't compete for the same 4 slots.
        per_category=20,
    ),
    "splits": Card(
        name="splits",
        title="Splits & Specialisms",
        description="Cross-segment comparisons (car class, era, race position).",
        include_kinds=(
            "class_split_podium",
            "class_split_ppr",
            # Reserved:
            "specialist_car",
            "multi_class_split",
            "recent_vs_early_split",
            "r1_vs_r4_split",
            "pole_to_win_rate",
            "pole_to_podium_rate",
            "wins_from_non_pole",
        ),
        max_items=4,
    ),
    "uniqueness": Card(
        name="uniqueness",
        title="League-Wide Uniqueness",
        description="\"Only driver to...\" facts; firsts in league history.",
        include_kinds=(
            "only_to_pole_sweep",
            "only_winless_with_long_streak",
            "sole_venue_winner",
            "first_to_milestone_wins",
            "first_to_milestone_podiums",
            "first_to_milestone_poles",
            "only_with_combination",
            "wins_without_poles",
            "won_both_classes",
            "multiple_wcc_club",
            "multiple_wdc_club",
        ),
        max_items=12,
        # Uniqueness produces many same-kind insights for dominant drivers
        # (e.g. Josie is first-to-milestone many times over). All are
        # genuinely interesting, so allow them all through.
        per_kind=10,
        per_category=20,
    ),
    "discipline": Card(
        name="discipline",
        title="Discipline",
        description="In-race penalties and clean-driver stats.",
        include_kinds=(
            "clean_career",
            "worst_penalty_race",
            "worst_penalty_season",
            # Reserved:
            "penalty_free_season",
            "high_penalty_venue",
        ),
        max_items=3,
    ),
    "current-form": Card(
        name="current-form",
        title="Current Form",
        description="In-progress season summary and latest results.",
        include_kinds=(
            # All reserved for upcoming detectors:
            "current_form",
            "current_standings",
            "current_season_best_result",
            "recent_form_summary",
            "most_recent_win",
            "most_recent_podium",
            "most_recent_pole",
        ),
        max_items=4,
    ),
    "head-to-head": Card(
        name="head-to-head",
        title="Head-to-Head & Team",
        description="Pairwise / teammate comparisons and championship-margin stories.",
        include_kinds=(
            # Team / WCC margins (now live):
            "wcc_contribution",
            "decisive_wcc_year",
            # Reserved (still schema-blocked):
            "teammate_h2h_record",
            "team_contribution_pct",
            "wcc_seasons_summary",
            "team_roster_history",
            "h2h_vs_champion",
            "h2h_vs_driver",
            "first_wcc_year",
            "only_constant_team_member",
        ),
        max_items=4,
    ),
}


# Default multi-card bundle when no specific cards are requested. Order
# matters — sections render in this order.
DEFAULT_BUNDLE: tuple[str, ...] = (
    "snapshot",
    "firsts",
    "streaks",
    "venues",
    "records",
    "trajectory",
    "peer-rank",
    "head-to-head",
    "uniqueness",
    "discipline",
)


def get(name: str) -> Card | None:
    """Look up a card by name. Returns None if unknown."""
    return CARDS.get(name)


def names() -> list[str]:
    """Return registered card names in registry order.

    Every entry in `CARDS` is included — adding a new card to the registry
    above automatically makes it available to consumers that iterate this
    list (including the CLI's `--cards all` expansion).
    """
    return list(CARDS.keys())


def resolve(card_names: list[str] | tuple[str, ...]) -> list[Card]:
    """Resolve a sequence of card names to Card objects, skipping unknowns."""
    out: list[Card] = []
    for n in card_names:
        c = CARDS.get(n)
        if c is not None:
            out.append(c)
    return out


# Reserved tokens that must not be used as card names. `all` is the CLI
# wildcard that expands to every registered card; if a future card were
# named "all", it would silently shadow the wildcard.
ALL_CARDS_TOKEN = "all"
_RESERVED_NAMES = frozenset({ALL_CARDS_TOKEN})

_collisions = _RESERVED_NAMES & CARDS.keys()
if _collisions:
    raise RuntimeError(
        f"Card name(s) {sorted(_collisions)} collide with reserved CLI tokens "
        f"({sorted(_RESERVED_NAMES)}). Rename the card in CARDS."
    )


__all__ = [
    "ALL_CARDS_TOKEN",
    "CARDS",
    "Card",
    "DEFAULT_BUNDLE",
    "get",
    "names",
    "resolve",
]
