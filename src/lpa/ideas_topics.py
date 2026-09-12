"""IDEAS research topic taxonomy for Analyst exports.

Simple keyword matching on title and body — zero-cost heuristic, not ML.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lpa.config import data_file


def load_ideas_topics(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or data_file("ideas_topics.json")).read_text(encoding="utf-8"))


def classify_article_topics(title: str, text: str, *, config: dict[str, Any] | None = None) -> list[str]:
    cfg = config or load_ideas_topics()
    haystack = f"{title} {text}".lower()
    matched: list[str] = []
    for topic_id, topic in cfg["topics"].items():
        keywords = topic.get("keywords", [])
        if any(kw.lower() in haystack for kw in keywords):
            matched.append(topic_id)
    return matched
