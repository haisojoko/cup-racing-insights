"""Cup Racing Insights — command-line interface.

Examples
--------
$ cri rebuild
$ cri cards
$ cri insights Allan
$ cri snippet Allan                        # default multi-card bundle
$ cri snippet Allan --card streaks         # single card
$ cri snippet Allan --cards streaks,venues # specific cards
$ cri snippet Allan --top 10               # legacy flat top-N
$ cri infographic Allan --card streaks     # filter by card
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import cards as cards_mod
from . import composites as composites_mod
from . import db as dbmod
from .composites import LayoutBudget
from .detectors import ALL_DETECTORS, run_all
from .render.infographic import (
    CareerSummary,
    build_all_cards_payload,
    build_card_payload,
    render_html,
    render_png,
    render_season_html,
)
from .render.season import build_season_summary
from .render.snippet import (
    diversify,
    render_bundle,
    render_card_bundle,
)
from .scoring import score_all

app = typer.Typer(
    add_completion=False,
    help="Cup Racing Insights — insights, snippets, and infographics.",
    no_args_is_help=True,
)
console = Console()


# ---------------------------------------------------------------------------

@app.command()
def rebuild(
    data: Path = typer.Option(
        dbmod.DEFAULT_DATA_PATH, "--data", "-d", help="Markdown source file."
    ),
    out: Path = typer.Option(
        dbmod.DEFAULT_DB_PATH, "--out", "-o", help="DuckDB output file."
    ),
):
    """Re-parse the markdown and rebuild the DuckDB database."""
    counts = dbmod.rebuild(data_path=data, db_path=out)
    console.print(f"[green]ok[/green] rebuilt [bold]{out}[/bold]")
    for k, v in counts.items():
        console.print(f"  {k:>16}  {v:>6}")


# ---------------------------------------------------------------------------

@app.command()
def cards():
    """List available cards. Each card is a themed section of insights."""
    tbl = Table(show_lines=False)
    tbl.add_column("Name", style="cyan", no_wrap=True)
    tbl.add_column("Title", no_wrap=True)
    tbl.add_column("Description")
    tbl.add_column("Kinds", justify="right", style="dim", no_wrap=True)
    for name in cards_mod.names():
        c = cards_mod.CARDS[name]
        tbl.add_row(c.name, c.title, c.description, str(len(c.include_kinds)))
    console.print(tbl)
    console.print(
        f"\n[dim]Default bundle: {', '.join(cards_mod.DEFAULT_BUNDLE)}[/dim]"
    )


# ---------------------------------------------------------------------------

@app.command()
def insights(
    driver: str = typer.Argument(..., help="Driver name (e.g. Allan)."),
    top: int = typer.Option(15, "--top", "-n", help="Number of insights to display."),
    recent: list[str] = typer.Option(
        ["S21", "S22"], "--recent", "-r", help="Season IDs to bump in scoring."
    ),
):
    """Run all detectors and print the full ranked insight table."""
    with dbmod.open_db() as con:
        results = run_all(con, driver)
    if not results:
        console.print(f"[yellow]No insights found for {driver}.[/yellow]")
        raise typer.Exit(0)
    score_all(results, recent_seasons=set(recent))

    tbl = Table(title=f"{driver} — Top {top} Insights", show_lines=False)
    tbl.add_column("#", justify="right", style="dim", width=3)
    tbl.add_column("Score", justify="right", width=6)
    tbl.add_column("Category", style="cyan", width=18)
    tbl.add_column("Kind", style="dim", width=28)
    tbl.add_column("Headline")
    for idx, ins in enumerate(results[:top], start=1):
        tbl.add_row(str(idx), f"{ins.score:.2f}", ins.category.value, ins.kind, ins.headline)
    console.print(tbl)


# ---------------------------------------------------------------------------

def _parse_cards_flag(cards_str: str | None) -> list[str] | None:
    if not cards_str:
        return None
    return [s.strip() for s in cards_str.split(",") if s.strip()]


def _expand_all(names: list[str]) -> list[str]:
    """Expand the wildcard token to every registered card name.

    Pulls directly from the registry, so any card added to `cards.CARDS`
    is included automatically — no separate list to keep in sync.
    """
    if cards_mod.ALL_CARDS_TOKEN in names:
        return cards_mod.names()
    return names


def _select_cards(card: str | None, cards_str: str | None) -> list[str]:
    if card:
        return _expand_all([card])
    parsed = _parse_cards_flag(cards_str)
    if parsed:
        return _expand_all(parsed)
    return list(cards_mod.DEFAULT_BUNDLE)


@app.command()
def snippet(
    driver: str = typer.Argument(..., help="Driver name (e.g. Allan)."),
    card: Optional[str] = typer.Option(
        None, "--card", help="Render a single card (e.g. 'streaks'). Use `cri cards` to list."
    ),
    cards_csv: Optional[str] = typer.Option(
        None, "--cards", help="Comma-separated card names to compose. Use 'all' for every card."
    ),
    per_card: Optional[int] = typer.Option(
        None, "--per-card", help="Override max items per card."
    ),
    top: Optional[int] = typer.Option(
        None, "--top", "-n", help="(Legacy) flat top-N across all kinds. Overrides cards."
    ),
    recent: list[str] = typer.Option(["S21", "S22"], "--recent", "-r"),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write to file instead of stdout."
    ),
):
    """Render a Discord-ready Markdown snippet.

    Default behaviour composes a multi-card bundle. Use --card for a single
    themed card, --cards for a custom subset, or --top for legacy flat output.
    """
    with dbmod.open_db() as con:
        results = run_all(con, driver)
    score_all(results, recent_seasons=set(recent))

    if top is not None:
        text = render_bundle(driver, results, top=top)
    else:
        names = _select_cards(card, cards_csv)
        unknown = [n for n in names if n not in cards_mod.CARDS]
        if unknown:
            console.print(
                f"[red]Unknown card(s): {', '.join(unknown)}.[/red] "
                f"Run `cri cards` to list available cards."
            )
            raise typer.Exit(1)
        chosen = cards_mod.resolve(names)
        text = render_card_bundle(driver, results, chosen, per_card_override=per_card)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        console.print(f"[green]ok[/green] wrote {out}")
    else:
        console.print(text)


# ---------------------------------------------------------------------------

def _render_season_card(
    driver: str,
    season: str,
    out: Path,
    save_html: bool,
    width: int,
    height: int,
) -> None:
    """Render the single-season celebration card.

    Blocks in-progress seasons (no champion declared yet) — the feature is a
    celebration of *completed* seasons for now.
    """
    season = season.upper()
    with dbmod.open_db() as con:
        meta = con.execute(
            "SELECT wdc FROM seasons WHERE season_id = ?", [season]
        ).fetchone()
        if meta is None:
            console.print(
                f"[red]Unknown season: {season}.[/red] "
                f"Use an ID like S21 (run `cri rebuild` if the data is new)."
            )
            raise typer.Exit(1)
        if (meta[0] or "").strip().upper() in ("", "TBD"):
            console.print(
                f"[yellow]{season} is still in progress[/yellow] — season "
                f"cards are for completed seasons only."
            )
            raise typer.Exit(1)
        summary = build_season_summary(con, driver, season)

    if summary is None:
        console.print(
            f"[red]No race data for {driver} in {season}.[/red] "
            f"Check the name and that the driver competed that season."
        )
        raise typer.Exit(1)

    # Default the output name to <driver>_<season> so it doesn't clobber the
    # career card. A user-supplied --out is respected (with {driver} filled in).
    if str(out) == "output/{driver}_card.png":
        out_str = f"output/{driver.lower().replace(' ', '_')}_{season.lower()}.png"
    else:
        out_str = str(out).replace("{driver}", driver.lower().replace(" ", "_"))
    out_path = Path(out_str)

    html = render_season_html(summary)
    if save_html:
        html_path = out_path.with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        console.print(f"[green]ok[/green] wrote {html_path}")

    render_png(html, out_path, width=width, height=height, trim_to_content=True)
    console.print(
        f"[green]ok[/green] wrote {out_path} "
        f"[dim]({summary.celebration_tier} season)[/dim]"
    )


@app.command()
def infographic(
    driver: str = typer.Argument(...),
    card: Optional[str] = typer.Option(
        None, "--card", help="Single-card hero layout (e.g. --card streaks). Use 'all' for the card-first grid."
    ),
    cards_csv: Optional[str] = typer.Option(
        None, "--cards", help="Comma-separated cards for the card-first grid layout. Use 'all' for every card."
    ),
    top: int = typer.Option(10, "--top", "-n", help="(Single-card mode) max insights to feature; fewer if the driver doesn't have that many."),
    out: Path = typer.Option(
        Path("output/{driver}_card.png"),
        "--out",
        "-o",
        help="Output PNG path. Use {driver} as a placeholder.",
    ),
    save_html: bool = typer.Option(
        False, "--html", help="Also save the intermediate HTML next to the PNG."
    ),
    recent: list[str] = typer.Option(["S21", "S22"], "--recent", "-r"),
    width: int = typer.Option(1200, "--width"),
    height: int = typer.Option(1600, "--height"),
    allow_grow: bool = typer.Option(
        False, "--allow-grow", help="(All-cards mode) let the canvas grow taller than --height to fit everything."
    ),
    trim_height: bool = typer.Option(
        False, "--trim-height", help="(All-cards mode) shrink the canvas if content is shorter than --height; combine with --allow-grow for exact-fit."
    ),
    no_composites: bool = typer.Option(
        False, "--no-composites", help="(All-cards mode) disable composite tiles; render every insight as its own row."
    ),
    budget: int = typer.Option(
        composites_mod.DEFAULT_BUDGET_UNITS,
        "--budget",
        help="(All-cards mode) tile-weight budget. Higher = denser canvas before drop/grow kicks in.",
    ),
    season: Optional[str] = typer.Option(
        None, "--season",
        help="Render a single-season celebration card (e.g. --season S21). Overrides card modes.",
    ),
):
    """Render a polished driver-card PNG infographic.

    Layout modes:
      • Season celebration (--season SXX): one completed season's achievements,
        framed as a celebration — best finish, rates, counted stats with
        iconography. No "out of N" comparisons.
      • Single-card hero layout (default, or --card NAME): top-N insights in the
        classic stacked-row design.
      • Card-first grid (--cards NAMES, or --card all / --cards all): every
        selected card becomes its own tile, with composite blocks condensing
        related insight families.
    """
    # --- Season celebration mode short-circuits the insight pipeline -------
    if season is not None:
        _render_season_card(driver, season, out, save_html, width, height)
        raise typer.Exit(0)

    with dbmod.open_db() as con:
        results = run_all(con, driver)
        row = con.execute(
            "SELECT races, wins, podiums, poles, points, top5, top5_pct "
            "FROM career_stats WHERE driver = ?",
            [driver],
        ).fetchone()

    if not row:
        console.print(f"[red]No career_stats row for {driver}.[/red]")
        raise typer.Exit(1)

    career = CareerSummary(
        races=row[0] or 0,
        wins=row[1] or 0,
        podiums=row[2] or 0,
        poles=row[3] or 0,
        points=row[4] or 0,
        top5=row[5] or 0,
        top5_pct=row[6] or 0.0,
    )

    score_all(results, recent_seasons=set(recent))

    # Decide layout mode. --cards (any value) and --card all → card-first grid.
    card_first = cards_csv is not None or (card == cards_mod.ALL_CARDS_TOKEN)

    out_str = str(out).replace("{driver}", driver.lower().replace(" ", "_"))
    out_path = Path(out_str)

    if card_first:
        names = _select_cards(card if card != cards_mod.ALL_CARDS_TOKEN else None, cards_csv)
        unknown = [n for n in names if n not in cards_mod.CARDS]
        if unknown:
            console.print(
                f"[red]Unknown card(s): {', '.join(unknown)}.[/red] Run `cri cards` to list."
            )
            raise typer.Exit(1)
        chosen = cards_mod.resolve(names)
        layout_budget = LayoutBudget(
            units=budget, overflow="grow" if allow_grow else "drop"
        )
        payload = build_all_cards_payload(
            driver,
            results,
            career,
            chosen,
            budget=layout_budget,
            use_composites=not no_composites,
        )
        html = render_html(
            payload,
            template="all_cards.html.j2",
            extra={"grow": allow_grow, "trim": trim_height},
        )
    else:
        deck_tag = "Driver Deep Cuts"
        diversify_output = True
        if card:
            c = cards_mod.get(card)
            if c is None:
                console.print(
                    f"[red]Unknown card: {card}.[/red] Run `cri cards` to list."
                )
                raise typer.Exit(1)
            results = [r for r in results if r.kind in c.include_kinds]
            deck_tag = c.title
            diversify_output = False
        payload = build_card_payload(
            driver,
            results,
            career,
            top=top,
            deck_tag=deck_tag,
            diversify_output=diversify_output,
        )
        html = render_html(payload)

    if save_html:
        html_path = out_path.with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        console.print(f"[green]ok[/green] wrote {html_path}")

    # Three capture modes:
    #   • single-card (always content-sized): trim_to_content with no cap
    #   • all-cards + --trim-height: trim_to_content, cap at `height` unless
    #     --allow-grow also given (then no cap → exact fit)
    #   • all-cards + --allow-grow only: full_page (grows past `height`)
    #   • all-cards default: fixed viewport
    if not card_first:
        render_png(
            html, out_path, width=width, height=height,
            trim_to_content=True,
        )
    elif trim_height:
        render_png(
            html, out_path, width=width, height=height,
            trim_to_content=True,
            trim_max_height=None if allow_grow else height,
        )
    elif allow_grow:
        render_png(html, out_path, width=width, height=height, full_page=True)
    else:
        render_png(html, out_path, width=width, height=height, full_page=False)
    console.print(f"[green]ok[/green] wrote {out_path}")


# ---------------------------------------------------------------------------

@app.command()
def composites(
    driver: Optional[str] = typer.Option(
        None, "--driver", "-D", help="Driver to use for orphan detection (otherwise just list composites)."
    ),
    orphans: bool = typer.Option(
        False, "--orphans", help="Show insight kinds the infographic can't surface (with --driver)."
    ),
):
    """List composite tile definitions and surface infographic-orphan kinds.

    A kind is orphaned for the infographic if it (a) is produced by a
    detector but no card claims it, or (b) belongs to no composite and only
    appears as a fallback (informational, not an error).
    """
    tbl = Table(show_lines=False)
    tbl.add_column("Composite", style="cyan", no_wrap=True)
    tbl.add_column("Card", no_wrap=True)
    tbl.add_column("Match", no_wrap=True)
    tbl.add_column("Weight", justify="right")
    tbl.add_column("Min", justify="right")
    for c in composites_mod.COMPOSITES:
        if c.kinds:
            match = ", ".join(c.kinds)
        elif c.kind_prefix:
            match = f"prefix '{c.kind_prefix}'"
        elif c.kind_pattern:
            match = f"regex '{c.kind_pattern}'"
        else:
            match = "—"
        tbl.add_row(c.name, c.card, match, str(c.weight), str(c.min_present))
    console.print(tbl)

    if not orphans:
        return
    if not driver:
        console.print(
            "[yellow]--orphans requires --driver to run detectors and inspect actual kinds.[/yellow]"
        )
        return

    with dbmod.open_db() as con:
        results = run_all(con, driver)

    observed_kinds = sorted({i.kind for i in results})
    all_card_kinds: set[str] = set()
    for c in cards_mod.CARDS.values():
        all_card_kinds.update(c.include_kinds)

    no_card = [k for k in observed_kinds if k not in all_card_kinds]
    composite_covered = {
        k for k in observed_kinds if composites_mod.matching_composite(k)
    }
    fallback_only = sorted(
        k for k in observed_kinds if k in all_card_kinds and k not in composite_covered
    )

    console.print(
        f"\n[bold]{driver}[/bold]: {len(observed_kinds)} distinct insight kinds observed."
    )
    if no_card:
        console.print(f"[red]NO CARD CLAIMS ({len(no_card)}):[/red] {', '.join(no_card)}")
        console.print(
            "[dim]→ Add these kinds to a card's include_kinds, or they won't appear on any infographic.[/dim]"
        )
    else:
        console.print("[green]All observed kinds are claimed by at least one card.[/green]")
    console.print(
        f"\n[dim]Composite-covered: {len(composite_covered)} · "
        f"Fallback-tile only: {len(fallback_only)}[/dim]"
    )
    if fallback_only:
        console.print(f"[dim]Fallback kinds: {', '.join(fallback_only)}[/dim]")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
