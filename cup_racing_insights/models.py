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


__all__ = ["Insight", "InsightCategory"]
