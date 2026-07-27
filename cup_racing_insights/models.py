"""Structured Insight type — the common output of every detector.

Detectors return Insight objects. Renderers consume them. The scorer ranks
them. Keep this lean: anything category-specific lives in `payload`, while
top-level fields are what the scorer and renderers care about.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class InsightCategory(str, Enum):
    FIRST_ONLY_LAST = "first_only_last"
    MILESTONE = "milestone"
    STREAK = "streak"
    RECORD = "record"
    ANOMALY = "anomaly"
    TRAJECTORY = "trajectory"
    MARGIN = "margin"
    SPLIT = "split"
    HEAD_TO_HEAD = "head_to_head"
    PEER_RANK = "peer_rank"


class Insight(BaseModel):
    """A single, deterministically detected fact about a driver/season/etc.

    Fields:
        category    Which detector family produced this.
        kind        Short slug naming the *specific* detector
                    (e.g. "top5_streak", "career_personal_best_finish").
                    Used to pick the renderer template.
        subject     The primary entity (usually a driver name).
        headline    A pre-rendered short string suitable for a graphic chip.
        body        Optional longer prose for snippets.
        payload     Detector-specific structured data — drives templates.
        score       Notability score (0..1+). Higher = more interesting.
        sources     Free-form pointers (season ids, venues) for auditing.
    """

    category: InsightCategory
    kind: str
    subject: str
    headline: str
    body: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    score: float = 0.0
    sources: list[str] = Field(default_factory=list)

    model_config = {"frozen": False}


# Stewards occasionally record a result at a position far outside the field
# instead of reclassifying it to last — S21 Monza R4 has James at P99, a
# self-inflicted DNF they let stand as the penalty. It is a deliberate,
# meaningful result: it counts as a start and keeps its points. But it is a
# *penalty placement*, not a finishing position, and averaging it as one turned
# James's S21 average finish into 7.88 for a season he won 9 of 16 races.
#
# The threshold sits well clear of any real field (the largest the league has
# ever run is 19) so a genuine finish can never be mistaken for one.
PENALTY_POSITION_MIN = 50

# Reusable predicate for "a position you can average". Note it deliberately
# does NOT filter DNS — callers that need that add `AND NOT dns` themselves,
# since a DNS and a penalty placement are different exclusions.
CLASSIFIED_POSITION_SQL = f"position IS NOT NULL AND position < {PENALTY_POSITION_MIN}"


__all__ = [
    "Insight",
    "InsightCategory",
    "PENALTY_POSITION_MIN",
    "CLASSIFIED_POSITION_SQL",
]
