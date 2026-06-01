# Cup Racing Insights

Deterministic insight generation for the Cup Racing League. Parses race-result
markdown into DuckDB, runs detector queries, and renders the output as
Discord-ready Markdown snippets or PNG infographics.

No LLM at runtime. Every fact is a SQL query you can audit.

For the detector catalogue and roadmap see [DETECTORS.md](DETECTORS.md).

---

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/playwright install chromium
```

The CLI is `cri`, installed at `.venv/bin/cri`. Either call it directly or
`source .venv/bin/activate` and use `cri` for the session.

---

## Workflow

1. `cri rebuild` — parse the markdown into DuckDB. Re-run after data changes.
2. `cri insights <Driver>` — preview the full ranked insight table.
3. `cri snippet <Driver>` — render a Discord-ready Markdown post.
4. `cri infographic <Driver>` — render a PNG card for upload.

Paste / upload manually. The tool does not post to Discord.

---

## Commands

Run any command with `--help` for full option lists.

### `cri rebuild`

Parses `data/Cup_Racing_Complete_Data.md` into `output/cup_racing.duckdb`.

| Flag | Default | Purpose |
|---|---|---|
| `--data`, `-d` | `data/Cup_Racing_Complete_Data.md` | Source markdown path |
| `--out`, `-o` | `output/cup_racing.duckdb` | DuckDB output path |

### `cri cards`

List available cards (themed groupings of insights). No flags.

### `cri insights <Driver>`

Print the full ranked insight table for a driver. Debug / discovery tool.

| Flag | Default | Purpose |
|---|---|---|
| `--top`, `-n` | `15` | Number of rows to display |
| `--recent`, `-r` | `S21 S22` | Season IDs to bump in notability scoring |

### `cri snippet <Driver>`

Render a Discord-ready Markdown post. Output flows through **cards** (themed
sections); see [Cards](#cards) below.

| Flag | Default | Purpose |
|---|---|---|
| `--card` | — | Render a single card (e.g. `--card streaks`); use `all` for every card |
| `--cards` | — | Comma-separated list of cards (`--cards streaks,venues`); use `all` for every card |
| `--per-card` | card-defined | Override max items per card |
| `--top`, `-n` | — | Legacy flat top-N (overrides cards) |
| `--recent`, `-r` | `S21 S22` | Recency bump for scoring |
| `--out`, `-o` | stdout | Write Markdown to file |

Default behaviour (no `--card` or `--top`) composes the default card bundle
into one post.

### `cri infographic <Driver>`

Render a 1200×1600 PNG card. HTML → headless Chromium → PNG.

Layout modes:
- **Season celebration** (`--season SXX`): one completed season, framed as a celebration — best finish (laurel/medal badge), compact completion + points-scoring gauges, rate tiles for points/wins/podiums/top-5s, and counted stats with iconography. Deliberately avoids any "out of N drivers" comparison so mid- and lower-pack drivers feel their season. Auto-picks the strongest hero (a podium leads with the medal badge; a non-podium season leads with its best rate). In-progress seasons are blocked (completed seasons only). Output defaults to `output/<driver>_<season>.png`.
- **Single-card hero layout** (default, or `--card NAME`): top-N insights in the classic stacked-row design.
- **Card-first grid** (`--cards NAMES`, or `--card all` / `--cards all`): every selected card becomes its own tile; related insight families collapse into **composite** blocks (see [`cri composites`](#cri-composites)).

| Flag | Default | Purpose |
|---|---|---|
| `--season` | — | Season celebration card (e.g. `--season S21`). Completed seasons only |
| `--card` | — | Single-card hero layout. Use `all` for the card-first grid |
| `--cards` | — | Card-first grid (e.g. `--cards streaks,venues` or `all`) |
| `--top`, `-n` | `10` | (Single-card mode) insights to feature; with `--card`, applied directly after card filtering |
| `--allow-grow` | off | (Card-first mode) let the canvas grow taller than `--height` to fit everything |
| `--no-composites` | off | (Card-first mode) disable composite tiles; render every insight as its own row |
| `--budget` | `40` | (Card-first mode) tile-weight budget before drop/grow kicks in |
| `--out`, `-o` | `output/{driver}_card.png` | Output path; `{driver}` is replaced |
| `--html` | off | Also save the intermediate HTML |
| `--recent`, `-r` | `S21 S22` | Recency bump for scoring |
| `--width` | `1200` | Output width |
| `--height` | `1600` | Output height |

### `cri composites`

List composite tile definitions used by the card-first infographic. Each
composite collapses a family of related insight kinds (e.g. `first_win` +
`first_podium` + `first_pole` + `first_fl` → one "Career Firsts" tile).

| Flag | Default | Purpose |
|---|---|---|
| `--driver`, `-D` | — | Driver to inspect for orphan detection |
| `--orphans` | off | (With `--driver`) list insight kinds the infographic can't surface |

`--orphans` is the safety net for future development: run it after adding a
new detector to confirm the kind is reachable from at least one card.

---

## Cards

Cards are themed sections that group related insights. Each card pulls from
a curated set of detectors; the same detector may feed multiple cards.

### `snapshot` — Snapshot
`detect_career_best_finish` · `detect_best_season` · `detect_personal_best_season_rank` · `detect_among_all_drivers`

### `firsts` — Firsts, Lasts & Milestones
`detect_career_firsts` · `detect_career_lasts`

### `streaks` — Streaks
`detect_top_n_streak` · `detect_consecutive_points_streak` · `detect_in_season_hot_streak` · `detect_consecutive_season_bests` · `detect_seasons_always_scoring` · `detect_consecutive_podium_seasons` · `detect_season_never_outside_top_n`

### `venues` — Venue Profile
`detect_distinct_venues_won` · `detect_venue_pole_sweep` · `detect_venue_repeat_wins` · `detect_best_avg_venue` · `detect_weekend_multi_podium` · `detect_venue_multi_season_podium`

### `records` — Records & Personal Bests
`detect_career_best_finish` · `detect_best_season` · `detect_best_venue_weekend` · `detect_concentrated_records` · `detect_highest_single_race_points` · `detect_largest_win_margin` · `detect_personal_best_season_rank` · `detect_hat_trick_races` · `detect_tightest_season_range`

### `trajectory` — Career Trajectory
`detect_best_vs_worst_season` · `detect_consecutive_podium_seasons` · `detect_personal_best_season_rank` · `detect_comeback_after_gap`

### `peer-rank` — League & Peer Standing
`detect_among_winless_peers` · `detect_among_all_drivers` · `detect_distinct_venues_won`

### `head-to-head` — Head-to-Head & Team
`detect_wcc_contribution` · `detect_decisive_wcc_year`

### `splits` — Splits & Specialisms
`detect_car_class_split` · `detect_specialist_car`

### `uniqueness` — League-Wide Uniqueness
`detect_only_to_pole_sweep` · `detect_only_winless_with_long_streak` · `detect_sole_venue_winner` · `detect_first_to_milestone` · `detect_wins_without_poles` · `detect_won_both_classes` · `detect_multiple_wcc_club` · `detect_multiple_wdc_club`

### `discipline` — Discipline
`detect_penalty_summary`

### `current-form` — Current Form
`detect_career_lasts`

Default bundle (in render order): `snapshot`, `firsts`, `streaks`, `venues`,
`records`, `trajectory`, `peer-rank`, `head-to-head`, `uniqueness`, `discipline`.

See [DETECTORS.md](DETECTORS.md) for the full catalogue (including planned
detectors pre-wired to each card).

---

## Examples

```sh
# One-time setup
python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/playwright install chromium
cri rebuild

# Multi-card editorial post (default)
cri snippet Allan --out output/allan.md

# Single themed card
cri snippet Allan --card streaks
cri snippet Josie --card venues

# Custom card subset
cri snippet Brie --cards venues,trajectory,records

# Every card in one post
cri snippet Allan --cards all

# Legacy flat top-N
cri snippet Allan --top 8

# Infographic, default driver-card layout
cri infographic Allan

# Infographic filtered to one theme
cri infographic Allan --card streaks -n 15 --html

# Card-first grid: every card on one image
cri infographic Allan --cards all

# Same, but let the canvas grow to fit every tile (for dense profiles)
cri infographic Josie --cards all --allow-grow

# Season celebration card (completed seasons only)
cri infographic Allan --season S21      # → output/allan_s21.png

# Audit: after adding a new detector, confirm the infographic can see it
cri composites --driver Josie --orphans
```

---

## Tech stack

| Layer | Tool |
|---|---|
| Storage | DuckDB (file-backed) |
| Models | Pydantic |
| Templates | Jinja2 |
| CLI | Typer + Rich |
| Infographic render | HTML/CSS + Playwright (Chromium) |
| Fonts | Google Fonts (Inter, JetBrains Mono) |

All open-source, offline-capable, zero runtime cost.

---

## Project layout

```
cup_racing_insights/
├── cli.py                # Typer entrypoint
├── cards.py              # Card registry
├── parser.py             # markdown → structured rows
├── db.py                 # DuckDB schema + loader
├── models.py             # Insight Pydantic model
├── scoring.py            # notability ranker
├── detectors/            # the insight library (see DETECTORS.md)
├── render/
│   ├── snippet.py        # card / bundle / flat Markdown rendering
│   └── infographic.py    # HTML/PNG
└── templates/
    ├── snippets/         # one .md.j2 per insight kind
    └── infographics/     # HTML/CSS card templates
```

---

## Extending

- **Add a detector:** new function in `detectors/`, register in
  `detectors/__init__.py::ALL_DETECTORS`, add a Jinja template at
  `templates/snippets/<insight.kind>.md.j2`, optionally tune `scoring.py`.
  Then update [DETECTORS.md](DETECTORS.md) status to ✅.
- **Add a card:** entry in `cards.py::CARDS` with the insight kinds it
  should surface. Card consumes whatever detectors already produce those
  kinds — no detector changes required.
- **Add an infographic composite:** new entry in `composites.py::COMPOSITES`
  + optional transformer in `TRANSFORMERS` + Jinja partial under
  `templates/infographics/composites/`. Run `cri composites --orphans
  --driver X` to verify coverage.
- **Add an infographic layout:** new template under
  `templates/infographics/`, wired through `render/infographic.py`.
