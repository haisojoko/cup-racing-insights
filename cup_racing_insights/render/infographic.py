"""Infographic rendering: data → HTML → PNG via Playwright.

The pattern (used by The Athletic, FiveThirtyEight, and most data-journalism
shops): design once in HTML/CSS, bind data with Jinja, snapshot with a
headless browser. Easy to iterate on visuals — they're just CSS.

Two layout paths:
  - `driver_card.html.j2`  — original top-N hero-row layout, used by
    `cri infographic Driver` and `cri infographic Driver --card streaks`.
  - `all_cards.html.j2`    — card-first grid that absorbs every card via
    composites + budget. Used by `cri infographic Driver --cards all` (and
    can be opted into for any card selection).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any, Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import cards as cards_mod
from .. import composites as comp_mod
from ..composites import (
    DEFAULT_FALLBACK_WEIGHT,
    LayoutBudget,
    Tile,
    build_composite_context,
    find_composites_for_card,
)
from ..models import Insight


_TEMPLATE_DIR = files("cup_racing_insights").joinpath("templates/infographics")
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
)


@dataclass
class CareerSummary:
    races: int
    wins: int
    podiums: int
    poles: int
    points: int
    top5: int
    top5_pct: float


def _summary_chips(ins: Insight) -> list[dict[str, Any]]:
    """Turn an insight's payload into 1–3 little 'tag' chips for the card.

    Each branch should land 1–3 chips. A primary chip uses the accent style;
    secondary chips use the 'muted' style. Chips repeat the most-quotable
    fact from the payload so a glance gives both the headline and the gist.
    """
    p = ins.payload
    chips: list[dict[str, Any]] = []
    k = ins.kind

    # Streak family — both inter-season ("top5_streak") and in-season variants.
    if k.endswith("_streak") and "length" in p:
        chips.append({"text": f"{p['length']} races"})
        if "season" in p:
            chips.append({"text": p["season"], "muted": True})
        elif "start" in p and "end" in p:
            chips.append({"text": f"{p['start']['season']} → {p['end']['season']}", "muted": True})

    elif k == "career_best_finish":
        chips.append({"text": f"P{p.get('position')}"})
        chips.append({"text": f"×{p.get('count', 1)}", "muted": True})

    elif k in ("career_best_season", "best_season_rank"):
        if "season" in p:
            chips.append({"text": p.get("season", "")})
        if "weighted_score" in p:
            chips.append({"text": f"ws {p['weighted_score']:.3f}", "muted": True})
        elif "wdc" in p:
            chips.append({"text": f"P{p['wdc']} WDC", "muted": True})

    elif k == "best_venue_weekend":
        chips.append({"text": p.get("venue", "")})
        chips.append({"text": p.get("season", ""), "muted": True})

    elif k.startswith("concentrated_") or k.startswith("majority_"):
        chips.append({"text": p.get("season", "")})
        if "total" in p:
            chips.append({"text": f"×{p['total']}", "muted": True})

    elif k.startswith("winless_rank_"):
        chips.append({"text": f"#{p.get('rank')}"})
        chips.append({"text": "winless cohort", "muted": True})

    elif k.startswith("league_rank_"):
        chips.append({"text": f"#{p.get('rank')}"})
        chips.append({"text": "all-time", "muted": True})

    # Firsts / lasts — pin season + venue
    elif k in ("first_win", "first_podium", "first_pole", "first_fl",
               "most_recent_win", "most_recent_podium", "most_recent_pole"):
        if "season" in p:
            chips.append({"text": p["season"]})
        if "venue" in p:
            chips.append({"text": p["venue"], "muted": True})

    # Venue stories
    elif k == "venue_pole_sweep_career":
        chips.append({"text": f"×{p.get('sweep_count', 0)}"})
        chips.append({"text": f"{p.get('season_count', 0)} seasons", "muted": True})
    elif k == "venue_repeat_wins_career":
        chips.append({"text": f"{p.get('venue_count', 0)} venues"})
        chips.append({"text": f"{p.get('total_repeat_wins', 0)} repeat wins", "muted": True})
    elif k == "weekend_multi_podium_career":
        chips.append({"text": f"{p.get('weekend_count', 0)} weekends"})
        if p.get("four_podium_count", 0):
            chips.append({"text": f"{p['four_podium_count']} sweeps", "muted": True})
    elif k == "venue_multi_season_podium_career":
        chips.append({"text": f"{p.get('venue_count', 0)} venues"})
        chips.append({"text": f"{p.get('season_span', 0)} seasons", "muted": True})
    elif k == "venue_pole_sweep":
        chips.append({"text": p.get("venue", "")})
        chips.append({"text": p.get("season", ""), "muted": True})
    elif k == "venue_repeat_wins":
        chips.append({"text": f"{p.get('wins', 0)} wins"})
        chips.append({"text": p.get("venue", ""), "muted": True})
    elif k == "venue_multi_season_podium":
        chips.append({"text": p.get("venue", "")})
        chips.append({"text": f"{p.get('season_count', 0)} seasons", "muted": True})
    elif k == "best_avg_venue":
        chips.append({"text": p.get("venue", "")})
        if "avg_position" in p:
            chips.append({"text": f"avg P{p['avg_position']:.1f}", "muted": True})
    elif k == "weekend_multi_podium":
        chips.append({"text": p.get("venue", "")})
        chips.append({"text": p.get("season", ""), "muted": True})
    elif k == "sole_venue_winner":
        chips.append({"text": f"{p.get('venue_count', 0)} venues"})
        chips.append({"text": "only winner", "muted": True})
    elif k == "distinct_winning_venues":
        chips.append({"text": f"#{p.get('rank')}"})
        chips.append({"text": f"{p.get('venues', 0)} venues", "muted": True})

    # Uniqueness club tiles
    elif k in ("multiple_wcc_club", "multiple_wdc_club"):
        titles = p.get("wcc_titles") or p.get("wdc_titles", 0)
        chips.append({"text": f"×{titles}"})
        chips.append({"text": f"cohort of {p.get('cohort_size', 0)}", "muted": True})
    elif k == "wins_without_poles":
        chips.append({"text": f"{p.get('wins', 0)} wins"})
        chips.append({"text": "0 poles", "muted": True})
    elif k == "won_both_classes":
        chips.append({"text": f"{p.get('formula_wins', 0)}F / {p.get('sports_wins', 0)}S"})
        chips.append({"text": f"cohort of {p.get('cohort_size', 0)}", "muted": True})
    elif k == "only_to_pole_sweep":
        chips.append({"text": f"×{p.get('sweep_count', 0)}"})
        chips.append({"text": "league-only", "muted": True})
    elif k == "only_winless_with_long_streak":
        chips.append({"text": f"{p.get('length', 0)} races"})
        chips.append({"text": "winless leader", "muted": True})
    elif k.startswith("first_to_milestone_"):
        chips.append({"text": f"first to {p.get('threshold', 0)}"})
        chips.append({"text": p.get("season", ""), "muted": True})

    # Records / personal bests
    elif k == "largest_win_margin":
        chips.append({"text": f"+{p.get('margin', 0)} pts"})
        chips.append({"text": p.get("season", ""), "muted": True})
    elif k == "highest_single_race_pts":
        chips.append({"text": f"{p.get('points', 0)} pts"})
        chips.append({"text": f"{p.get('venue', '')} {p.get('season', '')}", "muted": True})
    elif k == "triple_crown_weekends":
        chips.append({"text": f"×{p.get('total', 0)}"})
    elif k == "tightest_season_range":
        chips.append({"text": p.get("season", "")})
        if "range" in p:
            chips.append({"text": f"P-range {p['range']}", "muted": True})

    # Trajectory
    elif k == "best_vs_worst_season":
        best = p.get("best_rank")
        worst = p.get("worst_rank")
        if best is not None and worst is not None:
            chips.append({"text": f"P{best}→P{worst}"})
        if "spread" in p:
            chips.append({"text": f"spread {p['spread']}", "muted": True})
    elif k == "consecutive_podium_seasons":
        chips.append({"text": f"{p.get('length', 0)} seasons"})

    # Splits
    elif k == "specialist_car":
        chips.append({"text": p.get("car", "")})
        if "points_per_start" in p:
            chips.append({"text": f"{p['points_per_start']:.1f} ppr", "muted": True})
    elif k.startswith("class_split_"):
        chips.append({"text": p.get("leader", "")})

    # Penalty / discipline
    elif k == "clean_career":
        chips.append({"text": f"{p.get('pen_races', 0)}/{p.get('starts', 0)} penalised"})
    elif k == "worst_penalty_race":
        chips.append({"text": f"-{p.get('penalty', 0)} pts"})
        chips.append({"text": p.get("season", ""), "muted": True})
    elif k == "worst_penalty_season":
        chips.append({"text": p.get("season", "")})
        chips.append({"text": f"-{p.get('penalty_total', 0)} pts", "muted": True})

    # Margins / team
    elif k == "wcc_contribution":
        if "pct" in p:
            chips.append({"text": f"{p['pct']:.0f}%"})
        chips.append({"text": p.get("season", ""), "muted": True})
    elif k == "decisive_wcc_year":
        chips.append({"text": p.get("season", "")})

    # Consistency / season-shape
    elif k == "season_never_outside_top_n":
        chips.append({"text": p.get("season", "")})
        chips.append({"text": f"top-{p.get('threshold', 0)}", "muted": True})
    elif k == "seasons_always_scoring":
        chips.append({"text": f"{p.get('season_count', 0)} seasons"})

    return chips


def _tile_span(headline: str, chips: list[dict[str, Any]]) -> int:
    """Bento-grid sizing heuristic: long headlines or chip-rich tiles take
    a full row; short, compact tiles share a row with a sibling.

    The exact thresholds are calibrated for the current font-size + tile-
    padding combo. Tune in concert with `.insight` CSS in driver_card.html.j2.
    """
    # Long headlines wrap awkwardly in half-width tiles.
    if len(headline) >= 48:
        return 2
    # Three-or-more chips need horizontal room.
    if len(chips) >= 3:
        return 2
    return 1


def build_card_payload(
    driver: str,
    insights: list[Insight],
    career: CareerSummary,
    *,
    subtitle: str = "",
    deck_tag: str = "Driver Deep Cuts",
    footnote: str = "",
    top: int = 10,
    diversify_output: bool = True,
) -> dict[str, Any]:
    from .snippet import diversify
    chosen = (diversify(insights) if diversify_output else insights)[:top]
    rendered = []
    for i in chosen:
        chips = _summary_chips(i)
        rendered.append(
            {
                "headline": i.headline,
                "category": i.category.value,
                "chips": chips,
                "span": _tile_span(i.headline, chips),
            }
        )
    return {
        "driver": driver,
        "subtitle": subtitle or _default_subtitle(career),
        "deck_tag": deck_tag,
        "footnote": footnote,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "career": {
            "races": career.races,
            "wins": career.wins,
            "podiums": career.podiums,
            "poles": career.poles,
            "points": career.points,
            "top5": career.top5,
            "top5_pct": career.top5_pct,
        },
        "insights": rendered,
    }


def _default_subtitle(c: CareerSummary) -> str:
    bits = []
    if c.podiums:
        bits.append(f"{c.podiums} career podium{'s' if c.podiums != 1 else ''}")
    if c.poles:
        bits.append(f"{c.poles} pole{'s' if c.poles != 1 else ''}")
    if c.points:
        bits.append(f"{c.points} pts")
    return " · ".join(bits) if bits else "Cup Racing League"


def render_html(
    payload: dict[str, Any],
    template: str = "driver_card.html.j2",
    *,
    extra: dict[str, Any] | None = None,
) -> str:
    tpl = _env.get_template(template)
    return tpl.render(driver=payload["driver"], data=payload, **(extra or {}))


def render_season_html(summary: Any, template: str = "season_card.html.j2") -> str:
    """Render the season-celebration card. `summary` is a SeasonSummary; the
    template references it as `s`."""
    tpl = _env.get_template(template)
    return tpl.render(s=summary)


# ---------------------------------------------------------------------------
# Card-first layout: insights → card sections → composites + fallback tiles
# ---------------------------------------------------------------------------

def _assign_insights_to_cards(
    insights: list[Insight], cards: Sequence[cards_mod.Card]
) -> dict[str, list[Insight]]:
    """Each insight goes to the first card (in supplied order) whose
    include_kinds claims its kind. Insights with no card go unrendered."""
    by_card: dict[str, list[Insight]] = {c.name: [] for c in cards}
    for ins in insights:
        for c in cards:
            if ins.kind in c.include_kinds:
                by_card[c.name].append(ins)
                break
    return by_card


def _build_card_tiles(
    card: cards_mod.Card,
    insights: list[Insight],
    *,
    use_composites: bool = True,
) -> list[Tile]:
    """Apply composites to a card's insights, then emit fallback tiles
    for whatever's left. Tiles come back in score order (high → low)."""
    remaining = list(insights)
    tiles: list[Tile] = []

    if use_composites:
        for composite in find_composites_for_card(card.name):
            matched = [i for i in remaining if composite.matches(i.kind)]
            if len(matched) < composite.min_present:
                continue
            ctx = build_composite_context(composite, matched)
            top_score = max((i.score for i in matched), default=0.0)
            tiles.append(
                Tile(
                    template=composite.template,
                    weight=composite.weight,
                    score=top_score,
                    card=card.name,
                    title=composite.title,
                    context=ctx,
                    span=2,  # composites always need full width for tables/charts
                )
            )
            consumed = {(i.kind, i.headline) for i in matched}
            remaining = [
                i for i in remaining if (i.kind, i.headline) not in consumed
            ]

    for ins in remaining:
        tiles.append(
            Tile(
                template="_fallback.html.j2",
                weight=DEFAULT_FALLBACK_WEIGHT,
                score=ins.score,
                card=card.name,
                title=None,
                context={
                    "headline": ins.headline,
                    "meta": ins.category.value.replace("_", " ").title(),
                },
                span=2 if len(ins.headline) >= 52 else 1,
            )
        )

    tiles.sort(key=lambda t: t.score, reverse=True)
    return tiles


def _apply_budget(
    card_tiles: list[tuple[cards_mod.Card, list[Tile]]],
    budget: LayoutBudget,
    *,
    hero_weight: int = 3,
) -> list[tuple[cards_mod.Card, list[Tile]]]:
    """Drop the lowest-scoring tiles until total weight ≤ budget.

    Caller has already reserved space for the hero (hero_weight). The
    fixed-cost regions (header/strip/footer) are assumed already accounted
    for in `budget.units`. With overflow='grow' the budget is treated as
    soft — every tile stays and the canvas height expands.
    """
    if budget.overflow == "grow":
        return card_tiles

    # Flatten with (card_idx, tile_idx, tile) for stable identity.
    flat = [
        (ci, ti, t)
        for ci, (_, tiles) in enumerate(card_tiles)
        for ti, t in enumerate(tiles)
    ]
    total_weight = sum(t.weight for _, _, t in flat) + hero_weight
    if total_weight <= budget.units:
        return card_tiles

    # Drop lowest-score tiles until under budget. Stable for ties via
    # original index.
    flat_sorted_for_drop = sorted(
        flat, key=lambda x: (x[2].score, -x[0], -x[1])
    )
    to_drop: set[tuple[int, int]] = set()
    for ci, ti, t in flat_sorted_for_drop:
        if total_weight <= budget.units:
            break
        to_drop.add((ci, ti))
        total_weight -= t.weight

    filtered: list[tuple[cards_mod.Card, list[Tile]]] = []
    for ci, (card, tiles) in enumerate(card_tiles):
        kept = [t for ti, t in enumerate(tiles) if (ci, ti) not in to_drop]
        filtered.append((card, kept))
    return filtered


def build_all_cards_payload(
    driver: str,
    insights: list[Insight],
    career: CareerSummary,
    cards: Sequence[cards_mod.Card],
    *,
    budget: LayoutBudget | None = None,
    use_composites: bool = True,
    deck_tag: str = "All-Cards Profile",
) -> dict[str, Any]:
    """Build the payload for the card-first `all_cards.html.j2` template."""
    budget = budget or LayoutBudget()
    by_card = _assign_insights_to_cards(insights, cards)

    card_tiles: list[tuple[cards_mod.Card, list[Tile]]] = []
    for card in cards:
        tiles = _build_card_tiles(card, by_card[card.name], use_composites=use_composites)
        if tiles:
            card_tiles.append((card, tiles))

    card_tiles = _apply_budget(card_tiles, budget)

    # Hero = highest-scoring tile across the whole layout. Remove it from
    # its card so it doesn't render twice.
    hero = None
    best: tuple[float, int, int] | None = None
    for ci, (_, tiles) in enumerate(card_tiles):
        for ti, t in enumerate(tiles):
            # Only fallback tiles make good hero material — composite tiles
            # already have rich internal layout.
            if t.template != "_fallback.html.j2":
                continue
            key = (t.score, -ci, -ti)
            if best is None or key > best:
                best = key
                hero = (ci, ti, t)
    if hero is not None:
        ci, ti, t = hero
        card, tiles = card_tiles[ci]
        card_tiles[ci] = (card, [x for x in tiles if x is not t])
        # Drop empty cards.
        card_tiles = [(c, ts) for c, ts in card_tiles if ts]
        hero_payload = {"headline": t.context["headline"]}
    else:
        hero_payload = None

    return {
        "driver": driver,
        "subtitle": _default_subtitle(career),
        "deck_tag": deck_tag,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "career": {
            "races": career.races,
            "wins": career.wins,
            "podiums": career.podiums,
            "poles": career.poles,
            "points": career.points,
            "top5": career.top5,
            "top5_pct": career.top5_pct,
        },
        "hero": hero_payload,
        "card_tiles": [
            {
                "name": card.name,
                "title": card.title,
                "span": 2 if len(tiles) >= 5 else 1,
                "tiles": [
                    {
                        "template": t.template,
                        "title": t.title,
                        "weight": t.weight,
                        "context": t.context,
                        "span": t.span,
                    }
                    for t in tiles
                ],
            }
            for card, tiles in card_tiles
        ],
    }


def render_png(
    html: str,
    out_path: Path,
    *,
    width: int = 1200,
    height: int = 1600,
    full_page: bool = False,
    trim_to_content: bool = False,
    trim_max_height: int | None = None,
) -> Path:
    """Render HTML to PNG with Playwright. Lazy-import to keep CLI snappy.

    Capture modes:
      * default (`full_page=False, trim_to_content=False`) — exactly
        `width × height` viewport.
      * `full_page=True` — grows the screenshot when content is taller than
        viewport; for shorter content, still captures the full viewport.
      * `trim_to_content=True` — measures the body's actual height and
        resizes the viewport to match. Use `trim_max_height` to clamp
        (e.g. cap at `height`); omit to let any taller content come through.
    """
    from playwright.sync_api import sync_playwright

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(html, wait_until="networkidle")
        if trim_to_content:
            body_h = int(page.evaluate("document.body.scrollHeight"))
            target = body_h if trim_max_height is None else min(body_h, trim_max_height)
            # Playwright requires at least a few px; guard against absurd shrink.
            target = max(target, 100)
            page.set_viewport_size({"width": width, "height": target})
            page.screenshot(path=str(out_path), full_page=False, omit_background=False)
        else:
            page.screenshot(path=str(out_path), full_page=full_page, omit_background=False)
        browser.close()
    return out_path
