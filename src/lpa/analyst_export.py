"""Machine-readable exports for the Analyst workbench.

Baseline, model config, state signals, and current Sentiment inputs — the
static bundle the client-side Swing Model sandbox replays without hitting
Storage at runtime.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from lpa.config import (
    coalition_names,
    load_coalition_config,
    load_state_election_signals,
    swing_model_config,
)
from lpa.domain import Coalition, SeatBaseline, SwingModelConfig
from lpa.public_export import CAVEAT as PROJECTION_CAVEAT
from lpa.storage import load_seat_baselines, load_sentiment_snapshots

SCHEMA_VERSION = 1

METHODOLOGY_URL = "https://politikku.my/methodology.html"


def export_baseline(baseline: Sequence[SeatBaseline]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "FACT",
        "description": "GE15 Baseline per Seat — fixed record, not a Projection.",
        "seats": [
            {
                "code": seat.code,
                "name": seat.name,
                "state": seat.state,
                "vote_share": dict(seat.vote_share),
                "margin": seat.margin,
                "winner": seat.winner,
            }
            for seat in baseline
        ],
    }


def export_model_config(config: SwingModelConfig, names: Mapping[Coalition, str]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "MODEL",
        "description": (
            "Swing Model tunables and Government Coalition membership. "
            "Constants are provisional and uncalibrated (ADR 0003)."
        ),
        "government_coalitions": sorted(config.government_coalitions),
        "government_coalition_names": {
            c: names.get(c, c) for c in sorted(config.government_coalitions)
        },
        "majority_threshold": config.majority_threshold,
        "sentiment_sensitivity": config.sentiment_sensitivity,
        "state_signal_weight": config.state_signal_weight,
        "caveat": PROJECTION_CAVEAT,
    }


def export_state_signals() -> dict[str, Any]:
    signals = load_state_election_signals()
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "FACT",
        "description": "State Election Signals blended into the Swing Model per state.",
        "signals": [
            {
                "state": signal.state,
                "held_on": signal.held_on.isoformat(),
                "vote_share": dict(signal.vote_share),
            }
            for signal in signals
        ],
    }


def export_current_inputs(engine: Engine) -> dict[str, Any]:
    snapshots = load_sentiment_snapshots(engine)
    if not snapshots:
        raise ValueError("No Sentiment snapshot in Storage — run the pipeline first.")
    latest = snapshots[-1]
    sentiment = latest.sentiment
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "MODEL",
        "description": "Latest aggregated News Sentiment scores fed into the Swing Model.",
        "computed_at": latest.computed_at.isoformat(),
        "scores": dict(sentiment.scores),
        "article_counts": dict(sentiment.article_counts),
        "total_articles": sentiment.total_articles,
        "sources": list(sentiment.sources),
    }


def export_methodology() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "META",
        "methodology_url": METHODOLOGY_URL,
        "labels": {
            "FACT": "Historical record (GE15 Baseline, state election results).",
            "MODEL": "Modelled estimate — provisional constants, not a forecast.",
            "META": "Documentation and export metadata.",
        },
        "caveat": PROJECTION_CAVEAT,
    }


def export_analyst_payloads(engine: Engine) -> dict[str, dict[str, Any]]:
    config_data = load_coalition_config()
    names = coalition_names(config_data)
    baseline = load_seat_baselines(engine)
    if not baseline:
        raise ValueError("No Seat Baseline in Storage.")
    model_config = swing_model_config(config_data)
    return {
        "baseline.json": export_baseline(baseline),
        "model_config.json": export_model_config(model_config, names),
        "state_signals.json": export_state_signals(),
        "current_inputs.json": export_current_inputs(engine),
        "methodology.json": export_methodology(),
    }


def to_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2) + "\n"


def write_analyst_exports(engine: Engine, output_dir: Path) -> dict[str, str]:
    """Write analyst JSON files under output_dir/analyst/data/."""
    data_dir = output_dir / "analyst" / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    bodies: dict[str, str] = {}
    for name, payload in export_analyst_payloads(engine).items():
        body = to_json(payload)
        (data_dir / name).write_text(body, encoding="utf-8")
        bodies[name] = body
    return bodies


def build_analyst_bundle(
    engine: Engine,
    output_dir: Path,
    *,
    projection_json: str | None = None,
    sentiment_json: str | None = None,
    articles_json: str | None = None,
) -> None:
    """Write analyst/data/ JSON files and a downloadable ZIP bundle."""
    from lpa.ideas_topics import load_ideas_topics

    data_dir = output_dir / "analyst" / "data"
    bundle_dir = data_dir / "bundle"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    payloads = export_analyst_payloads(engine)
    for name, payload in payloads.items():
        text = to_json(payload)
        (data_dir / name).write_text(text, encoding="utf-8")
        (bundle_dir / name).write_text(text, encoding="utf-8")

    extras: dict[str, str] = {}
    if projection_json is not None:
        extras["projection.json"] = projection_json
    if sentiment_json is not None:
        extras["sentiment.json"] = sentiment_json
    if articles_json is not None:
        extras["articles.json"] = articles_json

    for name, body in extras.items():
        (data_dir / name).write_text(body, encoding="utf-8")
        (bundle_dir / name).write_text(body, encoding="utf-8")

    topics_config = load_ideas_topics()
    if articles_json:
        articles_payload = json.loads(articles_json)
        for topic_id in topics_config["topics"]:
            topic_dir = bundle_dir / topic_id
            topic_dir.mkdir(parents=True, exist_ok=True)
            matched = [
                article
                for article in articles_payload.get("articles", [])
                if topic_id in article.get("topics", [])
            ]
            csv_lines = ["url,title,source,dominant_coalition,computed_at"]
            for article in matched:
                csv_lines.append(
                    ",".join(
                        [
                            _csv_escape(article.get("url", "")),
                            _csv_escape(article.get("title", "")),
                            _csv_escape(article.get("source", "")),
                            _csv_escape(article.get("dominant_coalition", "")),
                            _csv_escape(articles_payload.get("computed_at", "")),
                        ]
                    )
                )
            (topic_dir / "articles.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

    zip_path = data_dir / "analyst-bundle.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(bundle_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(bundle_dir)))


def _csv_escape(value: str) -> str:
    if any(ch in value for ch in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def main() -> None:
    import argparse

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("public"))
    args = parser.parse_args()
    engine = connect()
    try:
        write_analyst_exports(engine, args.output_dir)
        print(f"Wrote analyst exports to {args.output_dir / 'analyst' / 'data'}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
