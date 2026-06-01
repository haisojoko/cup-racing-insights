"""Render Insight objects to Discord-friendly Markdown.

Three rendering modes:
    render_card        — one themed section (used by single-card mode)
    render_card_bundle — multiple themed sections composed into one post
    render_flat        — legacy mixed-bag top-N (kept for --top fallback)
"""

from __future__ import annotations

from dataclasses import replace
from importlib.resources import files
from typing import Sequence

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..cards import Card
from ..models import Insight


_TEMPLATE_DIR = files("cup_racing_insights").joinpath("templates/snippets")
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(disabled_extensions=("md", "j2")),
    # Both off: predictable, exact whitespace. Templates use {%- and -%}
    # for explicit whitespace control when needed.
    trim_blocks=False,
    lstrip_blocks=False,
    keep_trailing_newline=False,
)


# ---------------------------------------------------------------------------
# Per-insight rendering
# ---------------------------------------------------------------------------

def render_insight(insight: Insight) -> str:
    """Render a single Insight to a short Markdown snippet."""
    template_name = f"{insight.kind}.md.j2"
    try:
        template = _env.get_template(template_name)
    except Exception:
        template = _env.get_template("_default.md.j2")
    return template.render(ins=insight, p=insight.payload).strip()


# ---------------------------------------------------------------------------
# Diversification (used inside cards and by legacy flat rendering)
# ---------------------------------------------------------------------------

def diversify(
    insights: list[Insight], *, per_kind: int = 2, per_category: int = 4
) -> list[Insight]:
    """Cap repetition so a single kind/category does not monopolise output.

    Preserves existing (score-sorted) order.
    """
    out: list[Insight] = []
    kind_counts: dict[str, int] = {}
    cat_counts: dict[str, int] = {}
    for ins in insights:
        if kind_counts.get(ins.kind, 0) >= per_kind:
            continue
        if cat_counts.get(ins.category.value, 0) >= per_category:
            continue
        out.append(ins)
        kind_counts[ins.kind] = kind_counts.get(ins.kind, 0) + 1
        cat_counts[ins.category.value] = cat_counts.get(ins.category.value, 0) + 1
    return out


# ---------------------------------------------------------------------------
# Card-based rendering
# ---------------------------------------------------------------------------

def _filter_for_card(insights: list[Insight], card: Card) -> list[Insight]:
    return [i for i in insights if i.kind in card.include_kinds]


def _insight_id(ins: Insight) -> tuple[str, str]:
    """Cheap identity for dedupe: kind + headline."""
    return (ins.kind, ins.headline)


def render_card(
    insights: list[Insight],
    card: Card,
    *,
    diversify_output: bool = True,
    include_header: bool = True,
    exclude_ids: set[tuple[str, str]] | None = None,
) -> tuple[str, set[tuple[str, str]]] | None:
    """Render a single card's section.

    Returns (rendered_text, set_of_ids_used), or None if nothing matched.
    `exclude_ids` lets the bundle skip insights already rendered earlier.
    Diversification caps come from the card itself (`per_kind`, `per_category`)
    so cards like uniqueness can opt into showing more repetition.
    """
    exclude_ids = exclude_ids or set()
    filtered = [
        i for i in _filter_for_card(insights, card)
        if _insight_id(i) not in exclude_ids
    ]
    if not filtered:
        return None
    if diversify_output:
        filtered = diversify(
            filtered,
            per_kind=card.per_kind,
            per_category=card.per_category,
        )
    selected = filtered[: card.max_items]
    if not selected:
        return None
    parts: list[str] = []
    if include_header:
        parts.append(f"### {card.title}")
        parts.append("")
    used: set[tuple[str, str]] = set()
    for ins in selected:
        rendered = render_insight(ins)
        if rendered:
            parts.append(rendered)
            parts.append("")
            used.add(_insight_id(ins))
    return "\n".join(parts).rstrip(), used


def render_card_bundle(
    driver: str,
    insights: list[Insight],
    cards: Sequence[Card],
    *,
    per_card_override: int | None = None,
    diversify_output: bool = True,
    dedupe_across_cards: bool = True,
) -> str:
    """Compose multiple cards into one Markdown post with a header.

    When `dedupe_across_cards` is True (default), an insight that appears
    in an earlier card section is suppressed from later sections in the
    same post. This avoids the case where Snapshot, Records, and Trajectory
    all reprint the same career-best fact.

    When `per_card_override` is set, diversification is skipped so the user
    receives exactly up to N items ranked purely by score.
    """
    parts: list[str] = [
        f"## {driver}",
        "_Cup Racing Insights — statistical profile_",
        "",
    ]
    rendered_any = False
    already: set[tuple[str, str]] = set()
    # Explicit --per-card means "give me N items, no restrictions" — bypass
    # diversification so score alone decides what surfaces.
    effective_diversify = diversify_output and (per_card_override is None)
    for card in cards:
        c = replace(card, max_items=per_card_override) if per_card_override else card
        result = render_card(
            insights, c,
            diversify_output=effective_diversify,
            exclude_ids=already if dedupe_across_cards else None,
        )
        if result is None:
            continue
        section, used = result
        parts.append(section)
        parts.append("")
        already |= used
        rendered_any = True
    if not rendered_any:
        parts.append("_No insights matched the selected cards._")
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Legacy flat rendering — kept for `--top` callers
# ---------------------------------------------------------------------------

def render_bundle(
    driver: str,
    insights: list[Insight],
    *,
    top: int = 8,
    diversify_output: bool = True,
) -> str:
    """Flat (non-card) mixed top-N post. Used when --top is passed."""
    chosen = diversify(insights) if diversify_output else insights
    parts = [
        f"## {driver}",
        "_Cup Racing Insights — statistical profile_",
        "",
    ]
    for ins in chosen[:top]:
        rendered = render_insight(ins)
        if rendered:
            parts.append(rendered)
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"
