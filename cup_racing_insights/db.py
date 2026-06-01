"""DuckDB schema, loader, and connection helper.

We use a file-backed DuckDB database (./output/cup_racing.duckdb by default)
so detectors can run SQL directly. The whole dataset is small enough that
this fits comfortably in memory, but on-disk persistence means parsing
only has to happen on data changes.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import duckdb

from .parser import ParsedDataset, parse_markdown


DEFAULT_DB_PATH = Path("output/cup_racing.duckdb")
DEFAULT_DATA_PATH = Path("data/Cup_Racing_Complete_Data.md")


SCHEMA_SQL = """
DROP TABLE IF EXISTS seasons;
DROP TABLE IF EXISTS career_stats;
DROP TABLE IF EXISTS race_results;
DROP TABLE IF EXISTS weighted_scores;
DROP TABLE IF EXISTS team_standings;

CREATE TABLE seasons (
    season_id        VARCHAR PRIMARY KEY,
    season_num       INTEGER NOT NULL,
    season_sub       VARCHAR NOT NULL,
    type             VARCHAR NOT NULL,
    car              VARCHAR NOT NULL,
    venues           VARCHAR[] NOT NULL,
    races_per_venue  INTEGER NOT NULL,
    wdc              VARCHAR,
    wcc              VARCHAR
);

CREATE TABLE career_stats (
    driver        VARCHAR PRIMARY KEY,
    wdc           INTEGER,
    wcc           INTEGER,
    wins          INTEGER,
    podiums       INTEGER,
    poles         INTEGER,
    fls           INTEGER,
    points        INTEGER,
    races         INTEGER,
    win_pct       DOUBLE,
    pod_pct       DOUBLE,
    pts_per_race  DOUBLE,
    fl_pct        DOUBLE,
    top5          INTEGER,
    top5_pct      DOUBLE
);

CREATE TABLE race_results (
    season_id        VARCHAR NOT NULL,
    venue            VARCHAR NOT NULL,
    venue_order      INTEGER NOT NULL,
    race_num         INTEGER NOT NULL,
    driver           VARCHAR NOT NULL,
    car              VARCHAR,
    position         INTEGER,
    points           INTEGER NOT NULL,
    is_pole          BOOLEAN NOT NULL,
    is_fastest_lap   BOOLEAN NOT NULL,
    penalty          INTEGER NOT NULL,
    dns              BOOLEAN NOT NULL
);

CREATE INDEX idx_results_driver ON race_results(driver);
CREATE INDEX idx_results_season ON race_results(season_id);

CREATE TABLE weighted_scores (
    driver           VARCHAR NOT NULL,
    season_id        VARCHAR NOT NULL,
    rank             INTEGER NOT NULL,
    weighted_score   DOUBLE  NOT NULL,
    win_pct          DOUBLE,
    pod_pct          DOUBLE,
    top5_pct         DOUBLE,
    pts_per_race     DOUBLE,
    fl_pct           DOUBLE,
    pole_pct         DOUBLE,
    pts_rate         DOUBLE,
    participation    DOUBLE,
    has_wdc          BOOLEAN,
    has_wcc          BOOLEAN,
    PRIMARY KEY (driver, season_id)
);

CREATE INDEX idx_ws_driver ON weighted_scores(driver);

CREATE TABLE team_standings (
    season_id    VARCHAR NOT NULL,
    team_label   VARCHAR NOT NULL,
    team_name    VARCHAR,
    members      VARCHAR[] NOT NULL,
    points       INTEGER NOT NULL,
    season_rank  INTEGER NOT NULL,
    PRIMARY KEY (season_id, team_label)
);

CREATE INDEX idx_team_season ON team_standings(season_id);
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


@contextmanager
def open_db(db_path: Path = DEFAULT_DB_PATH) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(db_path)
    try:
        yield con
    finally:
        con.close()


def rebuild(
    data_path: Path = DEFAULT_DATA_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    """Parse the markdown and rebuild the DuckDB from scratch.

    Returns row counts per table.
    """
    ds = parse_markdown(data_path)
    with open_db(db_path) as con:
        con.execute(SCHEMA_SQL)
        _bulk_insert(con, ds)
        counts = {
            "seasons": con.execute("SELECT COUNT(*) FROM seasons").fetchone()[0],
            "career_stats": con.execute("SELECT COUNT(*) FROM career_stats").fetchone()[0],
            "race_results": con.execute("SELECT COUNT(*) FROM race_results").fetchone()[0],
            "weighted_scores": con.execute("SELECT COUNT(*) FROM weighted_scores").fetchone()[0],
            "team_standings": con.execute("SELECT COUNT(*) FROM team_standings").fetchone()[0],
        }
    return counts


def _bulk_insert(con: duckdb.DuckDBPyConnection, ds: ParsedDataset) -> None:
    # seasons
    if ds.seasons:
        con.executemany(
            """
            INSERT INTO seasons VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    s.season_id,
                    s.season_num,
                    s.season_sub,
                    s.type,
                    s.car,
                    s.venues,
                    s.races_per_venue,
                    s.wdc,
                    s.wcc,
                )
                for s in ds.seasons
            ],
        )

    if ds.career_stats:
        con.executemany(
            """
            INSERT INTO career_stats VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    c.driver, c.wdc, c.wcc, c.wins, c.podiums, c.poles, c.fls,
                    c.points, c.races, c.win_pct, c.pod_pct, c.pts_per_race,
                    c.fl_pct, c.top5, c.top5_pct,
                )
                for c in ds.career_stats
            ],
        )

    if ds.race_results:
        con.executemany(
            """
            INSERT INTO race_results VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.season_id, r.venue, r.venue_order, r.race_num, r.driver,
                    r.car, r.position, r.points, r.is_pole, r.is_fastest_lap,
                    r.penalty, r.dns,
                )
                for r in ds.race_results
            ],
        )

    if ds.weighted_scores:
        con.executemany(
            """
            INSERT INTO weighted_scores VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    w.driver, w.season_id, w.rank, w.weighted_score,
                    w.win_pct, w.pod_pct, w.top5_pct, w.pts_per_race,
                    w.fl_pct, w.pole_pct, w.pts_rate, w.participation,
                    w.has_wdc, w.has_wcc,
                )
                for w in ds.weighted_scores
            ],
        )

    if ds.team_standings:
        con.executemany(
            """
            INSERT INTO team_standings VALUES
            (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    t.season_id, t.team_label, t.team_name,
                    t.members, t.points, t.season_rank,
                )
                for t in ds.team_standings
            ],
        )
