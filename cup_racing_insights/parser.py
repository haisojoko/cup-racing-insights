"""Markdown → structured records.

Parses the Cup Racing complete-data markdown into three tables:
  - seasons       (season registry)
  - career_stats  (full career statistics)
  - race_results  (every individual race finish for every driver)

The race-results parser is the heavy lift. Tables have varying shapes:
  - S1–S9: 3 races/venue
  - S10+:  4 races/venue
  - Some venues include a "Car" column (multi-class seasons)
  - Position cells encode flags: "8 (P,FL,-3pen)" → pos=8, pole, FL, -3pt penalty
  - "DNS" means did-not-start (no position, no points)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Row-level dataclasses (lightweight; DuckDB does typing on insert)
# ---------------------------------------------------------------------------

@dataclass
class SeasonRow:
    season_id: str
    season_num: int          # for ordering; S18a=18, S18b=18 (use sub for tie-break)
    season_sub: str          # "" or "a"/"b"
    type: str                # Formula | Sports
    car: str
    venues: list[str]
    races_per_venue: int
    wdc: str
    wcc: str


@dataclass
class CareerStatRow:
    driver: str
    wdc: int
    wcc: int
    wins: int
    podiums: int
    poles: int
    fls: int
    points: int
    races: int
    win_pct: float
    pod_pct: float
    pts_per_race: float
    fl_pct: float
    top5: int
    top5_pct: float


@dataclass
class WeightedScoreRow:
    """A driver's weighted score for a single season, parsed from the
    'All-Time Weighted Score Rankings' table.
    """
    driver: str
    season_id: str
    rank: int                  # rank within the all-time table
    weighted_score: float
    win_pct: float
    pod_pct: float
    top5_pct: float
    pts_per_race: float
    fl_pct: float
    pole_pct: float
    pts_rate: float
    participation: float
    has_wdc: bool
    has_wcc: bool


@dataclass
class TeamStandingRow:
    """A team's WCC standing in one season, parsed from each season's
    '### Team Standings (WCC)' subsection.
    """
    season_id: str
    team_label: str            # original markdown string, e.g. "Allan + Walnut"
    team_name: str             # optional name prefix, "" if none
    members: list[str]         # individual driver names
    points: int
    season_rank: int           # 1 = WCC-winning team


@dataclass
class RaceResultRow:
    season_id: str
    venue: str
    venue_order: int          # 1..N within season
    race_num: int             # 1..races_per_venue
    driver: str
    car: str = ""             # may be empty for single-class seasons
    position: int | None = None    # None when DNS
    points: int = 0
    is_pole: bool = False
    is_fastest_lap: bool = False
    penalty: int = 0          # positive number of penalty points deducted
    dns: bool = False


# ---------------------------------------------------------------------------
# Cell-level parsers
# ---------------------------------------------------------------------------

_POS_RE = re.compile(r"^\s*(\d+)\s*(?:\((.*?)\))?\s*$")
_DNS_RE = re.compile(r"^\s*DNS\s*(?:\((.*?)\))?\s*$", re.IGNORECASE)
_PEN_RE = re.compile(r"-\s*(\d+)\s*pen", re.IGNORECASE)


def _parse_position_flags(flags: str) -> tuple[bool, bool, int]:
    flags = (flags or "").upper()
    is_pole = bool(re.search(r"\bP\b", flags))
    is_fl = "FL" in flags
    pen_match = _PEN_RE.search(flags)
    penalty = int(pen_match.group(1)) if pen_match else 0
    return is_pole, is_fl, penalty


def parse_position_cell(cell: str) -> dict:
    """Parse a position cell like '8 (P,FL,-3pen)' or 'DNS' or '5 (-2pen)'.

    Returns a dict with keys: position, is_pole, is_fastest_lap, penalty, dns.
    Unparseable cells return position=None, dns=False (we treat them as
    "no data" rather than DNS so the markdown stays the source of truth).
    """
    s = (cell or "").strip()
    if not s:
        return {"position": None, "is_pole": False, "is_fastest_lap": False, "penalty": 0, "dns": False}

    dns_match = _DNS_RE.match(s)
    if dns_match:
        is_pole, is_fl, penalty = _parse_position_flags(dns_match.group(1) or "")
        return {"position": None, "is_pole": is_pole, "is_fastest_lap": is_fl, "penalty": penalty, "dns": True}

    m = _POS_RE.match(s)
    if not m:
        return {"position": None, "is_pole": False, "is_fastest_lap": False, "penalty": 0, "dns": False}

    pos = int(m.group(1))
    is_pole, is_fl, penalty = _parse_position_flags(m.group(2) or "")
    return {
        "position": pos,
        "is_pole": is_pole,
        "is_fastest_lap": is_fl,
        "penalty": penalty,
        "dns": False,
    }


def _split_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cell strings."""
    # rows look like "| a | b | c |"
    parts = [p.strip() for p in line.strip().strip("|").split("|")]
    return parts


def _is_table_separator(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    body = s.strip("|").strip()
    return all(set(seg.strip()) <= set("- :") and seg.strip() for seg in body.split("|"))


def _parse_int(s: str, default: int = 0) -> int:
    s = s.strip().replace(",", "")
    if not s:
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def _parse_float(s: str, default: float = 0.0) -> float:
    s = s.strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1].strip()
        try:
            return float(s) / 100.0
        except ValueError:
            return default
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Document parser
# ---------------------------------------------------------------------------

@dataclass
class ParsedDataset:
    seasons: list[SeasonRow] = field(default_factory=list)
    career_stats: list[CareerStatRow] = field(default_factory=list)
    race_results: list[RaceResultRow] = field(default_factory=list)
    weighted_scores: list[WeightedScoreRow] = field(default_factory=list)
    team_standings: list[TeamStandingRow] = field(default_factory=list)


def parse_markdown(path: Path) -> ParsedDataset:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    ds = ParsedDataset()

    _parse_season_registry(lines, ds)
    _parse_career_stats(lines, ds)
    _parse_all_season_results(lines, ds)
    _parse_weighted_scores(lines, ds)
    return ds


# ---- Season registry ------------------------------------------------------

def _parse_season_registry(lines: list[str], ds: ParsedDataset) -> None:
    """Parse the '## Season Registry' table."""
    start = _find_section(lines, "## Season Registry")
    if start is None:
        return
    rows = _read_table_rows(lines, start)
    # header order: Season | Type | Car | Venues | Races/Venue | WDC | WCC
    for cells in rows:
        if len(cells) < 7:
            continue
        sid = cells[0].strip()
        if not sid.startswith("S"):
            continue
        season_num, season_sub = _parse_season_id(sid)
        venues = [v.strip() for v in cells[3].split(",") if v.strip()]
        ds.seasons.append(
            SeasonRow(
                season_id=sid,
                season_num=season_num,
                season_sub=season_sub,
                type=cells[1].strip(),
                car=cells[2].strip(),
                venues=venues,
                races_per_venue=_parse_int(cells[4], 0),
                wdc=cells[5].strip(),
                wcc=cells[6].strip(),
            )
        )


def _parse_season_id(sid: str) -> tuple[int, str]:
    """'S18a' → (18, 'a'); 'S5' → (5, '')."""
    m = re.match(r"^S(\d+)([a-z]?)$", sid)
    if not m:
        return (0, "")
    return (int(m.group(1)), m.group(2))


# ---- Career stats ---------------------------------------------------------

def _parse_career_stats(lines: list[str], ds: ParsedDataset) -> None:
    start = _find_section(lines, "## Full Career Statistics")
    if start is None:
        return
    rows = _read_table_rows(lines, start)
    # Driver | WDC | WCC | Wins | Podiums | Poles | FLs | Points | Races | Win% | Pod% | Pts/Race | FL% | Top5 | Top5%
    for cells in rows:
        if len(cells) < 15:
            continue
        driver = cells[0].strip()
        if not driver or driver.lower() == "driver":
            continue
        ds.career_stats.append(
            CareerStatRow(
                driver=driver,
                wdc=_parse_int(cells[1]),
                wcc=_parse_int(cells[2]),
                wins=_parse_int(cells[3]),
                podiums=_parse_int(cells[4]),
                poles=_parse_int(cells[5]),
                fls=_parse_int(cells[6]),
                points=_parse_int(cells[7]),
                races=_parse_int(cells[8]),
                win_pct=_parse_float(cells[9]),
                pod_pct=_parse_float(cells[10]),
                pts_per_race=_parse_float(cells[11]),
                fl_pct=_parse_float(cells[12]),
                top5=_parse_int(cells[13]),
                top5_pct=_parse_float(cells[14]),
            )
        )


# ---- Weighted scores ------------------------------------------------------

def _parse_weighted_scores(lines: list[str], ds: ParsedDataset) -> None:
    """Parse the '## All-Time Weighted Score Rankings' table.

    Columns are resolved by HEADER NAME rather than fixed index so the parser
    tolerates added/reordered columns (the data file has grown 'Field' and 'Pen.'
    columns between PtsRate and Part.). Unrecognised columns are ignored.
    """
    start = _find_section(lines, "## All-Time Weighted Score Rankings")
    if start is None:
        return
    header, rows = _read_table_header_rows(lines, start)
    if not header:
        return
    # normalized-header -> column index
    idx = {_norm_header(h): i for i, h in enumerate(header)}

    def cell(cells: list[str], *names: str, default: str = "") -> str:
        for n in names:
            j = idx.get(n)
            if j is not None and j < len(cells):
                return cells[j]
        return default

    for cells in rows:
        rank_s = cell(cells, "rank").strip()
        if not rank_s or not rank_s[0].isdigit():
            continue
        driver = cell(cells, "driver").strip()
        season_id = cell(cells, "season").strip()
        if not driver or not season_id.startswith("S"):
            continue
        ds.weighted_scores.append(
            WeightedScoreRow(
                driver=driver,
                season_id=season_id,
                rank=_parse_int(rank_s),
                weighted_score=_parse_float(cell(cells, "wscore", "weightedscore")),
                win_pct=_parse_float(cell(cells, "win")),
                pod_pct=_parse_float(cell(cells, "pod")),
                top5_pct=_parse_float(cell(cells, "top5")),
                pts_per_race=_parse_float(cell(cells, "ptsrace")),
                fl_pct=_parse_float(cell(cells, "fl")),
                pole_pct=_parse_float(cell(cells, "pole")),
                pts_rate=_parse_float(cell(cells, "ptsrate")),
                participation=_parse_float(cell(cells, "part", "participation")),
                has_wdc="yes" in cell(cells, "wdc").strip().lower(),
                has_wcc="yes" in cell(cells, "wcc").strip().lower(),
            )
        )


# ---- Race results ---------------------------------------------------------

_SEASON_HEADER_RE = re.compile(r"^##\s+Season\s+(\d+[a-z]?)\s+Results\b", re.IGNORECASE)
_VENUE_HEADER_RE = re.compile(r"^####\s+Venue\s+(\d+):\s*(.+?)\s*$", re.IGNORECASE)


def _parse_all_season_results(lines: list[str], ds: ParsedDataset) -> None:
    """Walk every '## Season N Results' block and pull every venue table."""
    i = 0
    while i < len(lines):
        m = _SEASON_HEADER_RE.match(lines[i])
        if not m:
            i += 1
            continue
        sid = "S" + m.group(1)
        # find end of this season (next '## ' header at same level, or eof)
        j = i + 1
        while j < len(lines) and not (lines[j].startswith("## ") and not lines[j].startswith("### ")):
            j += 1
        _parse_one_season_block(lines[i:j], sid, ds)
        i = j


_TEAM_STANDINGS_RE = re.compile(r"^###\s+Team\s+Standings", re.IGNORECASE)


def parse_team_roster(team_str: str) -> tuple[str, list[str]]:
    """Parse a team roster string from the markdown.

    Handles two formats:
        "Allan + Walnut"                  -> ("", ["Allan", "Walnut"])
        "Tyuap - Brie + Tawm + Mike"      -> ("Tyuap", ["Brie", "Tawm", "Mike"])

    Driver names containing spaces (e.g. "Allen Q", "Big Mike") survive
    because we split on " + " not on whitespace.
    """
    s = (team_str or "").strip()
    name = ""
    roster_str = s
    if " - " in s:
        name, _, roster_str = s.partition(" - ")
        name = name.strip()
    members = [m.strip() for m in roster_str.split(" + ") if m.strip()]
    return (name, members)


def _parse_team_standings(block: list[str], start: int, sid: str, ds: ParsedDataset) -> int:
    """Parse a '### Team Standings (WCC)' subsection starting at `start`.

    Returns the index after the parsed table.
    """
    k = start + 1
    while k < len(block) and not block[k].lstrip().startswith("|"):
        k += 1
    if k >= len(block):
        return start + 1
    # skip header + separator
    k += 1
    if k < len(block) and _is_table_separator(block[k]):
        k += 1
    rank = 0
    while k < len(block):
        line = block[k]
        if not line.lstrip().startswith("|"):
            break
        cells = _split_row(line)
        if len(cells) >= 2 and cells[0].strip() and cells[1].strip():
            label = cells[0].strip()
            pts = _parse_int(cells[1], 0)
            name, members = parse_team_roster(label)
            if members:
                rank += 1
                ds.team_standings.append(
                    TeamStandingRow(
                        season_id=sid,
                        team_label=label,
                        team_name=name,
                        members=members,
                        points=pts,
                        season_rank=rank,
                    )
                )
        k += 1
    return k


def _parse_one_season_block(block: list[str], sid: str, ds: ParsedDataset) -> None:
    """Parse all venue subtables within one season block."""
    i = 0
    while i < len(block):
        # Branch: team standings subsection
        if _TEAM_STANDINGS_RE.match(block[i]):
            i = _parse_team_standings(block, i, sid, ds)
            continue
        vm = _VENUE_HEADER_RE.match(block[i])
        if not vm:
            i += 1
            continue
        venue_order = int(vm.group(1))
        venue = vm.group(2).strip()
        # find the table start (first '|')
        k = i + 1
        while k < len(block) and not block[k].lstrip().startswith("|"):
            k += 1
        if k >= len(block):
            i += 1
            continue
        # Read header + rows
        header_cells = _split_row(block[k])
        # next line is separator
        rows_start = k + 1
        if rows_start < len(block) and _is_table_separator(block[rows_start]):
            rows_start += 1
        # Read rows until non-pipe line
        rr = rows_start
        rows: list[list[str]] = []
        while rr < len(block):
            line = block[rr]
            if not line.lstrip().startswith("|"):
                break
            rows.append(_split_row(line))
            rr += 1

        layout = _detect_venue_table_layout(header_cells)
        for cells in rows:
            if not cells or not cells[0].strip():
                continue
            driver = cells[0].strip()
            car = cells[layout["car_col"]].strip() if layout["car_col"] is not None else ""
            for race_num, col_idx in enumerate(layout["pos_cols"], start=1):
                if col_idx >= len(cells):
                    continue
                pos_cell = cells[col_idx]
                pts_cell = cells[col_idx + 1] if col_idx + 1 < len(cells) else ""
                parsed = parse_position_cell(pos_cell)
                pts = _parse_int(pts_cell, 0)
                # skip totally empty cells where driver wasn't listed
                if parsed["position"] is None and not parsed["dns"] and pts == 0:
                    # Could be a true empty cell — still record as DNS so we
                    # know they were on the entry list. Easier downstream.
                    parsed["dns"] = True
                ds.race_results.append(
                    RaceResultRow(
                        season_id=sid,
                        venue=venue,
                        venue_order=venue_order,
                        race_num=race_num,
                        driver=driver,
                        car=car,
                        position=parsed["position"],
                        points=pts,
                        is_pole=parsed["is_pole"],
                        is_fastest_lap=parsed["is_fastest_lap"],
                        penalty=parsed["penalty"],
                        dns=parsed["dns"],
                    )
                )
        i = rr


def _detect_venue_table_layout(header_cells: list[str]) -> dict:
    """Locate the position columns and (optional) car column.

    Headers we expect:
      | Driver | R1 Pos | R1 Pts | R2 Pos | R2 Pts | ... | Day Total |
    Or with a car col:
      | Driver | Car | R1 Pos | R1 Pts | ... | Day Total |
    """
    lower = [h.lower() for h in header_cells]
    car_col: int | None = None
    if len(lower) > 1 and lower[1] == "car":
        car_col = 1
    pos_cols: list[int] = []
    for idx, h in enumerate(lower):
        if re.match(r"^r\d+\s+pos$", h):
            pos_cols.append(idx)
    return {"car_col": car_col, "pos_cols": pos_cols}


# ---- Section/table helpers ------------------------------------------------

def _find_section(lines: list[str], header: str) -> int | None:
    needle = header.strip().lower()
    for i, line in enumerate(lines):
        if line.strip().lower().startswith(needle):
            return i
    return None


def _norm_header(h: str) -> str:
    """Normalize a column header for name-based lookup: lowercase, drop everything
    but letters and digits. e.g. 'W.Score' -> 'wscore', 'Pts/Race' -> 'ptsrace'."""
    return "".join(ch for ch in h.lower() if ch.isalnum())


def _read_table_header_rows(lines: list[str], start: int) -> tuple[list[str], list[list[str]]]:
    """Like `_read_table_rows`, but also return the header cells so callers can map
    columns by name."""
    i = start
    while i < len(lines) and not lines[i].lstrip().startswith("|"):
        i += 1
    if i >= len(lines):
        return [], []
    header = _split_row(lines[i])
    i += 1
    if i < len(lines) and _is_table_separator(lines[i]):
        i += 1
    rows: list[list[str]] = []
    while i < len(lines):
        line = lines[i]
        if not line.lstrip().startswith("|"):
            break
        rows.append(_split_row(line))
        i += 1
    return header, rows


def _read_table_rows(lines: list[str], start: int) -> list[list[str]]:
    """Find the next markdown table after `start` and return data rows (cells)."""
    return _read_table_header_rows(lines, start)[1]


__all__ = [
    "parse_markdown",
    "parse_position_cell",
    "parse_team_roster",
    "ParsedDataset",
    "SeasonRow",
    "CareerStatRow",
    "RaceResultRow",
    "WeightedScoreRow",
    "TeamStandingRow",
]
