"""Loader for the granular per-race dataset (results.json → DuckDB).

The Markdown archive only carries finishing positions + pole/FL flags. The
race-processor's JSON dataset (``data/races/index.json`` + ``seasons/*.json``)
adds lap times, sectors, qualifying times, overtakes, and contacts. This module
reads that dataset and populates aggregate tables keyed the same way as
``race_results`` (season_id, venue_order, race_num, driver) so detectors can
query — or join — it directly.

We deliberately store per-race *aggregates* (pace stats, overtake/contact
counts, qualifying best laps) rather than raw laps: it keeps the DB lean and
every requested detector/stat needs only these. Raw laps/sectors can be added
later for sector-level detectors.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

import duckdb

DEFAULT_RACES_DIR = Path("data/races")

# Lap-time validity, mirroring the portal/processor: a positive time under ten
# minutes. The standing-start lap 1 and off-track outliers are stripped before
# consistency is measured so it reflects racing pace, not incidents.
_MAX_LAP_MS = 600_000
_OUTLIER_FACTOR = 1.20  # drop laps slower than 120% of the median (pit/off)


RACES_SCHEMA_SQL = """
DROP TABLE IF EXISTS race_pace;
DROP TABLE IF EXISTS qual_times;
DROP TABLE IF EXISTS race_overtakes;
DROP TABLE IF EXISTS race_contacts;
DROP TABLE IF EXISTS grid_moves;

CREATE TABLE race_pace (
    season_id    VARCHAR NOT NULL,
    venue        VARCHAR NOT NULL,
    venue_order  INTEGER NOT NULL,
    race_num     INTEGER NOT NULL,
    driver       VARCHAR NOT NULL,
    avg_ms       DOUBLE  NOT NULL,   -- mean of clean laps
    best_ms      DOUBLE  NOT NULL,
    worst_ms     DOUBLE  NOT NULL,   -- slowest clean lap
    stdev_ms     DOUBLE,             -- population stdev; NULL with <2 clean laps
    cv_pct       DOUBLE,             -- stdev / mean * 100 (track-agnostic); NULL if <2
    laps_used    INTEGER NOT NULL
);

CREATE INDEX idx_pace_driver ON race_pace(driver);
CREATE INDEX idx_pace_season ON race_pace(season_id);

CREATE TABLE qual_times (
    season_id    VARCHAR NOT NULL,
    venue        VARCHAR NOT NULL,
    venue_order  INTEGER NOT NULL,
    session      VARCHAR NOT NULL,   -- qual1, qual2, …
    driver       VARCHAR NOT NULL,
    best_ms      DOUBLE  NOT NULL
);

CREATE INDEX idx_qual_driver ON qual_times(driver);

CREATE TABLE race_overtakes (
    season_id    VARCHAR NOT NULL,
    venue        VARCHAR NOT NULL,
    venue_order  INTEGER NOT NULL,
    race_num     INTEGER NOT NULL,
    driver       VARCHAR NOT NULL,
    made         INTEGER NOT NULL,   -- on-track passes made (incl. launch)
    suffered     INTEGER NOT NULL
);

CREATE INDEX idx_ot_driver ON race_overtakes(driver);

CREATE TABLE race_contacts (
    season_id    VARCHAR NOT NULL,
    venue        VARCHAR NOT NULL,
    venue_order  INTEGER NOT NULL,
    race_num     INTEGER NOT NULL,
    driver       VARCHAR NOT NULL,
    contacts     INTEGER NOT NULL    -- collisions this driver was involved in
);

CREATE INDEX idx_contact_driver ON race_contacts(driver);

CREATE TABLE grid_moves (
    season_id        VARCHAR NOT NULL,
    venue            VARCHAR NOT NULL,
    venue_order      INTEGER NOT NULL,
    race_num         INTEGER NOT NULL,
    driver           VARCHAR NOT NULL,
    positions_gained INTEGER NOT NULL  -- grid -> finish (positionChanges.net); + = up
);

CREATE INDEX idx_grid_driver ON grid_moves(driver);
"""


def _clean_laps(laps: list) -> list[float]:
    """Racing-pace laps: positive, in-range, minus the standing start and
    minus pit/off outliers (slower than 120% of the median)."""
    vals = [float(ms) for ms in laps if isinstance(ms, (int, float)) and 0 < ms < _MAX_LAP_MS]
    if len(vals) <= 1:
        return vals
    body = vals[1:]  # drop lap 1 (standing start)
    if not body:
        return vals
    median = statistics.median(body)
    clean = [ms for ms in body if ms <= median * _OUTLIER_FACTOR]
    return clean or body


def _pace_stats(laps: list) -> dict[str, float] | None:
    """avg/best/worst/stdev/cv over a driver's clean laps, or None if none."""
    clean = _clean_laps(laps)
    if not clean:
        return None
    avg = statistics.fmean(clean)
    # A single clean lap has no meaningful spread — leave stdev/cv NULL rather
    # than reporting a misleading 0 ("perfectly consistent").
    stdev = statistics.pstdev(clean) if len(clean) > 1 else None
    cv = (stdev / avg * 100.0) if (stdev is not None and avg) else None
    return {
        "avg_ms": avg,
        "best_ms": min(clean),
        "worst_ms": max(clean),
        "stdev_ms": stdev,
        "cv_pct": cv,
        "laps_used": len(clean),
    }


def _iter_season_files(races_dir: Path) -> list[Path]:
    index = races_dir / "index.json"
    if index.exists():
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
            files = [races_dir / s["file"] for s in data.get("seasons", {}).values() if s.get("file")]
            if files:
                return sorted(f for f in files if f.exists())
        except (ValueError, OSError, KeyError):
            pass
    return sorted((races_dir / "seasons").glob("*.json"))


def _extract(season: dict) -> dict[str, list[tuple]]:
    """Pull the four aggregate row-sets out of one season JSON."""
    sid = season.get("season", "")
    pace_rows: list[tuple] = []
    qual_rows: list[tuple] = []
    ot_rows: list[tuple] = []
    contact_rows: list[tuple] = []
    grid_rows: list[tuple] = []

    for ev in season.get("events", []):
        venue = ev.get("venue", "")
        vorder = ev.get("venueOrder", 0)

        for session, q in (ev.get("qualifying") or {}).items():
            for driver, t in (q.get("times") or {}).items():
                best = t.get("bestMs")
                if isinstance(best, (int, float)) and 0 < best < _MAX_LAP_MS:
                    qual_rows.append((sid, venue, vorder, session, driver, float(best)))

        for race_key, race in (ev.get("races") or {}).items():
            try:
                rnum = int(race_key)
            except (TypeError, ValueError):
                continue

            for driver, laps in (race.get("laps") or {}).items():
                stats = _pace_stats(laps)
                if stats:
                    pace_rows.append((
                        sid, venue, vorder, rnum, driver,
                        stats["avg_ms"], stats["best_ms"], stats["worst_ms"],
                        stats["stdev_ms"], stats["cv_pct"], stats["laps_used"],
                    ))

            made: dict[str, int] = {}
            suffered: dict[str, int] = {}
            for ov in race.get("overtakes") or []:
                if ov.get("driver"):
                    made[ov["driver"]] = made.get(ov["driver"], 0) + 1
                if ov.get("passed"):
                    suffered[ov["passed"]] = suffered.get(ov["passed"], 0) + 1
            for driver in set(made) | set(suffered):
                ot_rows.append((sid, venue, vorder, rnum, driver, made.get(driver, 0), suffered.get(driver, 0)))

            contacts: dict[str, int] = {}
            for c in race.get("contacts") or []:
                for who in (c.get("driver1"), c.get("driver2")):
                    if who:
                        contacts[who] = contacts.get(who, 0) + 1
            for driver, n in contacts.items():
                contact_rows.append((sid, venue, vorder, rnum, driver, n))

            # positionChanges is null on low-confidence grids — skip those races.
            for driver, ch in (race.get("positionChanges") or {}).items():
                net = ch.get("net") if isinstance(ch, dict) else None
                if net is not None:
                    grid_rows.append((sid, venue, vorder, rnum, driver, int(net)))

    return {"pace": pace_rows, "qual": qual_rows, "overtakes": ot_rows,
            "contacts": contact_rows, "grid": grid_rows}


def load_races(con: duckdb.DuckDBPyConnection, races_dir: Path = DEFAULT_RACES_DIR) -> dict[str, int]:
    """Create the race tables and load every season file. Returns row counts.

    Safe no-op (empty tables) when the dataset is absent, so a Markdown-only
    checkout still rebuilds.
    """
    con.execute(RACES_SCHEMA_SQL)
    files = _iter_season_files(races_dir) if races_dir.exists() else []

    all_rows: dict[str, list[tuple]] = {"pace": [], "qual": [], "overtakes": [], "contacts": [], "grid": []}
    for path in files:
        try:
            season = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        for key, rows in _extract(season).items():
            all_rows[key].extend(rows)

    if all_rows["pace"]:
        con.executemany("INSERT INTO race_pace VALUES (?,?,?,?,?,?,?,?,?,?,?)", all_rows["pace"])
    if all_rows["qual"]:
        con.executemany("INSERT INTO qual_times VALUES (?,?,?,?,?,?)", all_rows["qual"])
    if all_rows["overtakes"]:
        con.executemany("INSERT INTO race_overtakes VALUES (?,?,?,?,?,?,?)", all_rows["overtakes"])
    if all_rows["contacts"]:
        con.executemany("INSERT INTO race_contacts VALUES (?,?,?,?,?,?)", all_rows["contacts"])
    if all_rows["grid"]:
        con.executemany("INSERT INTO grid_moves VALUES (?,?,?,?,?,?)", all_rows["grid"])

    return {
        "race_pace": len(all_rows["pace"]),
        "qual_times": len(all_rows["qual"]),
        "race_overtakes": len(all_rows["overtakes"]),
        "race_contacts": len(all_rows["contacts"]),
        "grid_moves": len(all_rows["grid"]),
    }
