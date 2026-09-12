"""Export scored articles for Analyst sentiment drill-down."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from sqlalchemy.engine import Engine

from lpa.config import coalition_names, load_coalition_config
from lpa.domain import Coalition
from lpa.ideas_topics import classify_article_topics
from lpa.storage import load_scored_articles, load_sentiment_snapshots

SCHEMA_VERSION = 1


def dominant_coalition(scores: Mapping[Coalition, float] | None) -> str | None:
    if not scores:
        return None
    return max(scores, key=lambda c: scores[c])


def export_articles(
    *,
    computed_at: date,
    articles: Sequence[dict[str, Any]],
    sentiment_deltas: Mapping[Coalition, float | None],
    coalition_names_map: Mapping[Coalition, str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "MODEL",
        "computed_at": computed_at.isoformat(),
        "description": "Article-level News Sentiment scores for the latest pipeline run.",
        "coalition_deltas": {coalition: delta for coalition, delta in sentiment_deltas.items()},
        "coalition_names": dict(coalition_names_map),
        "articles": articles,
    }


def _article_rows(engine: Engine, computed_at: date) -> list[dict[str, Any]]:
    rows = load_scored_articles(engine, computed_at=computed_at)
    exported: list[dict[str, Any]] = []
    for row in rows:
        scores_raw = row["coalition_scores"]
        scores: dict[str, float] = (
            {str(key): float(value) for key, value in scores_raw.items()}
            if isinstance(scores_raw, Mapping)
            else {}
        )
        exported.append(
            {
                "url": str(row["url"]),
                "title": str(row["title"]),
                "source": str(row["source"]),
                "scores": scores,
                "dominant_coalition": dominant_coalition(scores),
                "topics": classify_article_topics(str(row["title"]), str(row.get("text") or "")),
            }
        )
    return exported


def sentiment_deltas(engine: Engine, computed_at: date) -> dict[Coalition, float | None]:
    snapshots = load_sentiment_snapshots(engine)
    by_day = {snap.computed_at: snap.sentiment for snap in snapshots}
    latest = by_day.get(computed_at)
    if latest is None:
        return {}
    prior_days = [day for day in by_day if day < computed_at]
    if not prior_days:
        return dict.fromkeys(latest.scores, None)
    prior = by_day[max(prior_days)]
    return {
        coalition: latest.scores[coalition] - prior.scores[coalition]
        if coalition in prior.scores
        else None
        for coalition in latest.scores
    }


def build_export(engine: Engine) -> str:
    snapshots = load_sentiment_snapshots(engine)
    if not snapshots:
        raise ValueError("No Sentiment snapshot in Storage.")
    latest_day = snapshots[-1].computed_at
    config = load_coalition_config()
    names = coalition_names(config)
    payload = export_articles(
        computed_at=latest_day,
        articles=_article_rows(engine, latest_day),
        sentiment_deltas=sentiment_deltas(engine, latest_day),
        coalition_names_map=names,
    )
    return json.dumps(payload, indent=2) + "\n"


def main() -> None:
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("public"))
    args = parser.parse_args()
    engine = connect()
    try:
        body = build_export(engine)
        out = args.output_dir / "analyst" / "data" / "articles.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"Wrote {out}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
