"""Infographic composites — condense related insight kinds into one tile.

The snippet renderer treats every insight as its own paragraph; that's right
for Discord copy but wastes space in a fixed-canvas infographic. Composites
solve that by declaring "these N kinds belong together — collapse them into
one denser visual block."

Composites live here (not in detectors/) because they are a *presentation*
concern. Detectors keep emitting granular insights; the snippet keeps
showing every one. Only the infographic groups them.

---------------------------------------------------------------------------
When adding a new detector
---------------------------------------------------------------------------
1. Does the new insight kind fit an existing prefix composite? (e.g. any
   `first_to_milestone_*` is auto-picked up by `first_to_milestones`.)
   If yes — no work needed here.
2. If no, decide whether the kind warrants a new composite (because it has
   sibling kinds telling one story) or a fallback single tile is fine.
3. Run `cri composites --orphans Allan` to confirm the kind is reachable.

When adding a new card
---------------------------------------------------------------------------
1. Add the card to `cards.CARDS`. The infographic auto-picks it up — each
   card becomes its own tile region in the grid.
2. If the card's kinds overlap with an existing card, the insight goes to
   whichever card appears first in `DEFAULT_BUNDLE` order (avoids dupes).
3. Optionally add card-scoped composites by setting `card=<card-name>`.

When adding a CLI flag that affects volume
---------------------------------------------------------------------------
1. Test with --cards all + the new flag on a high-data driver (Josie).
2. If output overflows the budget, the renderer drops lowest-score tiles
   (overflow="drop") or grows the canvas (overflow="grow", via
   --allow-grow). Decide which default makes sense for the flag.

---------------------------------------------------------------------------
The budget model
---------------------------------------------------------------------------
The infographic has a finite vertical budget. Each tile declares a `weight`
(roughly: vertical units). The renderer greedily fills tiles in score order
until the budget is exhausted. Fallback (single-insight) tiles cost
`DEFAULT_FALLBACK_WEIGHT`. Composites declare their own weight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .models import Insight


# Budget units roughly approximate "rendered rows of content". A fallback
# tile (one insight headline) costs 1 unit; composite tiles declare their
# own weight (typically 3–4 because they pack a small table). At the
# default 1600px canvas, ~40 units fits across the 2-column grid below
# the header/strip/hero/footer chrome.
DEFAULT_BUDGET_UNITS = 40
DEFAULT_FALLBACK_WEIGHT = 1


@dataclass(frozen=True)
class Composite:
    """Rule for collapsing related insight kinds into one tile.

    Match in this order:
      1. `kinds` — exact list (use for tight families like first_win/podium/pole/fl).
      2. `kind_prefix` — single prefix string (use for open-ended families
         like first_to_milestone_*).
      3. `kind_pattern` — compiled regex (use when prefix isn't enough).
    `card` says which card section the composite tile renders inside;
    `min_present` filters out half-empty composites.
    """

    name: str
    title: str
    template: str               # filename under templates/infographics/composites/
    weight: int
    card: str                   # home card name (must exist in cards.CARDS)
    kinds: tuple[str, ...] = ()
    kind_prefix: str | None = None
    kind_pattern: str | None = None  # regex string
    min_present: int = 2

    def matches(self, kind: str) -> bool:
        if self.kinds and kind in self.kinds:
            return True
        if self.kind_prefix and kind.startswith(self.kind_prefix):
            return True
        if self.kind_pattern and re.match(self.kind_pattern, kind):
            return True
        return False


@dataclass(frozen=True)
class LayoutBudget:
    """How much fits on the infographic, and what to do when over.

    overflow:
      "drop" — sort tiles by score, drop lowest until under budget.
      "grow" — let the canvas height expand to fit everything.
    """

    units: int = DEFAULT_BUDGET_UNITS
    overflow: str = "drop"


@dataclass
class Tile:
    """A renderable block produced by either a composite or a single insight."""

    template: str
    weight: int
    score: float
    card: str
    title: str | None = None     # composite title (None for fallback tiles)
    context: dict = field(default_factory=dict)  # data the template needs
    span: int = 1                # 1 = half-width, 2 = full-width in sub-grid


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

COMPOSITES: tuple[Composite, ...] = (
    Composite(
        name="career_firsts",
        title="Career Firsts",
        template="career_firsts.html.j2",
        weight=4,
        card="firsts",
        kinds=("first_win", "first_podium", "first_pole", "first_fl"),
        min_present=2,
    ),
    Composite(
        name="recent_form",
        title="Most Recent",
        template="recent_form.html.j2",
        weight=3,
        card="firsts",
        kinds=("most_recent_win", "most_recent_podium", "most_recent_pole"),
        min_present=2,
    ),
    Composite(
        name="streak_ladder",
        title="Best Streaks",
        template="streak_ladder.html.j2",
        weight=4,
        card="streaks",
        kinds=("top3_streak", "top5_streak", "top10_streak", "points_streak"),
        min_present=2,
    ),
    Composite(
        name="league_rank_table",
        title="League Rankings",
        template="league_rank_table.html.j2",
        weight=4,
        card="peer-rank",
        kind_prefix="league_rank_",
        min_present=2,
    ),
    Composite(
        name="first_to_milestone_wins",
        title="First to Career Win Milestones",
        template="milestone_ladder.html.j2",
        weight=3,
        card="uniqueness",
        kind_prefix="first_to_milestone_wins",
        min_present=2,
    ),
    Composite(
        name="first_to_milestone_podiums",
        title="First to Career Podium Milestones",
        template="milestone_ladder.html.j2",
        weight=3,
        card="uniqueness",
        kind_prefix="first_to_milestone_podiums",
        min_present=2,
    ),
    Composite(
        name="first_to_milestone_poles",
        title="First to Career Pole Milestones",
        template="milestone_ladder.html.j2",
        weight=3,
        card="uniqueness",
        kind_prefix="first_to_milestone_poles",
        min_present=2,
    ),
)


def find_composites_for_card(card_name: str) -> list[Composite]:
    return [c for c in COMPOSITES if c.card == card_name]


def matching_composite(kind: str) -> Composite | None:
    """Return the first composite that claims this kind, or None."""
    for c in COMPOSITES:
        if c.matches(kind):
            return c
    return None


def all_composite_names() -> list[str]:
    return [c.name for c in COMPOSITES]


# ---------------------------------------------------------------------------
# Composite transformers: insights → tile context dict
#
# Each transformer takes the matched Insights (in score order) and returns
# the context that the composite's Jinja template expects. A composite
# without a registered transformer falls back to a generic list shape.
# ---------------------------------------------------------------------------

_FIRSTS_LABELS = {
    "first_win": "Win",
    "first_podium": "Podium",
    "first_pole": "Pole",
    "first_fl": "Fastest Lap",
    "most_recent_win": "Win",
    "most_recent_podium": "Podium",
    "most_recent_pole": "Pole",
}

# Canonical display order for sibling-kind composites.
_FIRSTS_ORDER = ["first_win", "first_podium", "first_pole", "first_fl"]
_RECENT_ORDER = ["most_recent_win", "most_recent_podium", "most_recent_pole"]


def _firsts_context(insights: list[Insight]) -> dict:
    by_kind = {i.kind: i for i in insights}
    rows = []
    for kind in _FIRSTS_ORDER:
        ins = by_kind.get(kind)
        if not ins:
            continue
        p = ins.payload
        where = f"{p.get('venue', '')} R{p.get('race', '')}".strip(" R")
        rows.append(
            {
                "label": _FIRSTS_LABELS[kind],
                "where": where or "—",
                "season": p.get("season", ""),
            }
        )
    return {"rows": rows}


def _recent_form_context(insights: list[Insight]) -> dict:
    by_kind = {i.kind: i for i in insights}
    rows = []
    for kind in _RECENT_ORDER:
        ins = by_kind.get(kind)
        if not ins:
            continue
        p = ins.payload
        where = f"{p.get('venue', '')} R{p.get('race', '')}".strip(" R")
        rows.append(
            {
                "label": _FIRSTS_LABELS[kind],
                "where": where or "—",
                "season": p.get("season", ""),
            }
        )
    return {"rows": rows}


_STREAK_LABELS = {
    "top3_streak": "Top 3",
    "top5_streak": "Top 5",
    "top10_streak": "Top 10",
    "points_streak": "Points",
}
_STREAK_ORDER = ["top3_streak", "top5_streak", "top10_streak", "points_streak"]


def _streak_ladder_context(insights: list[Insight]) -> dict:
    by_kind = {i.kind: i for i in insights}
    steps = []
    lengths = [int(i.payload.get("length", 0)) for i in insights]
    max_len = max(lengths) if lengths else 1
    for kind in _STREAK_ORDER:
        ins = by_kind.get(kind)
        if not ins:
            continue
        length = int(ins.payload.get("length", 0))
        steps.append(
            {
                "label": _STREAK_LABELS[kind],
                "length": length,
                "bar_pct": round(100 * length / max_len) if max_len else 0,
            }
        )
    return {"steps": steps}


def _league_rank_context(insights: list[Insight]) -> dict:
    rows = []
    # Sort by rank ascending so the leaderboard reads top-down.
    by_rank = sorted(insights, key=lambda i: int(i.payload.get("rank", 999)))
    for ins in by_rank:
        p = ins.payload
        # Recover the metric name from the kind suffix.
        metric = ins.kind.removeprefix("league_rank_").replace("_", " ")
        value = p.get("value")
        try:
            value_str = f"{int(value):,}" if value is not None else ""
        except (TypeError, ValueError):
            value_str = str(value) if value is not None else ""
        rows.append(
            {
                "rank": int(p.get("rank", 0)),
                "metric": metric.title(),
                "detail": value_str,
            }
        )
    return {"rows": rows}


def _milestone_ladder_context(insights: list[Insight]) -> dict:
    by_threshold = sorted(
        insights, key=lambda i: int(i.payload.get("threshold", 0))
    )
    steps = [
        {
            "threshold": int(i.payload.get("threshold", 0)),
            "season": i.payload.get("season", ""),
        }
        for i in by_threshold
    ]
    return {"steps": steps}


# Registry of composite-name → transformer.
TRANSFORMERS: dict[str, callable] = {
    "career_firsts": _firsts_context,
    "recent_form": _recent_form_context,
    "streak_ladder": _streak_ladder_context,
    "league_rank_table": _league_rank_context,
    "first_to_milestone_wins": _milestone_ladder_context,
    "first_to_milestone_podiums": _milestone_ladder_context,
    "first_to_milestone_poles": _milestone_ladder_context,
}


def build_composite_context(composite: Composite, insights: list[Insight]) -> dict:
    """Build the template context for a composite from its matched insights."""
    fn = TRANSFORMERS.get(composite.name)
    if fn is None:
        # Generic shape: just a list of headlines.
        return {
            "rows": [{"label": i.kind, "where": i.headline, "season": ""} for i in insights]
        }
    return fn(insights)


__all__ = [
    "Composite",
    "Tile",
    "LayoutBudget",
    "COMPOSITES",
    "TRANSFORMERS",
    "DEFAULT_BUDGET_UNITS",
    "DEFAULT_FALLBACK_WEIGHT",
    "build_composite_context",
    "find_composites_for_card",
    "matching_composite",
    "all_composite_names",
]
