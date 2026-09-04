"""A machine-readable export of Sentiment, alongside `politikku_sentiment.py`.

`politikku_sentiment.py` turns Sentiment into HTML for a reader
(`/sentiment.html`, `/ms/sentiment.html`). This is the same data as JSON —
for the frontend's own sentiment view, and for anyone else who wants the
numbers without scraping the page.

Follows `public_export.py`'s seam exactly: `export_model` reads a
`SentimentPageModel` (already the one correct construction of this data —
`politikku_sentiment.sentiment_page_model`) and returns a plain,
JSON-serializable `dict`. `to_json` turns that dict into the on-disk shape.
`build_export` is the I/O half, calling `sentiment_page_model` itself rather
than re-deriving per-Coalition scores, article counts, or deltas from
Storage a second time.

`SCHEMA_VERSION` exists so a future breaking change to this shape has
somewhere to say so, the same reasoning `public_export.SCHEMA_VERSION`
carries.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import Engine

from lpa.domain import Coalition
from lpa.politikku_sentiment import SentimentPageModel

SCHEMA_VERSION = 1

HISTORY_LIMIT = 14
"""How many of the most recent stored days `history` carries.

`sentiment_page_model` does not cap its own `history` — the HTML page draws
a fixed-width chart itself and can decide the window at render time — so
this export takes the most recent `HISTORY_LIMIT` points itself, oldest
first, the same span this repo already treats as "recent" for a trend
(`public_page.MIN_TREND_READINGS`'s neighbourhood, not that same constant —
this is a page of history to read, not a line that needs enough points to
be honestly joined).
"""


def export_model(model: SentimentPageModel, names: Mapping[Coalition, str]) -> dict[str, Any]:
    """Build the export payload as a plain, JSON-serializable dict.

    Pure: reads only its arguments, decides no file shape. `model` is
    `sentiment_page_model`'s own output — every score, article count, and
    delta here is that function's arithmetic, never re-derived.
    """
    coalitions = [
        {
            "coalition": row.coalition,
            "coalition_name": names.get(row.coalition, row.coalition),
            "article_count": row.article_count,
            "score": row.score,
            "delta": row.delta,
        }
        for row in model.rows
    ]
    history = [
        {
            "computed_at": point.computed_at.isoformat(),
            "total_articles": point.total_articles,
            "scores": dict(point.scores),
        }
        for point in model.history[-HISTORY_LIMIT:]
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "computed_at": model.updated_at.isoformat(),
        "sources_count": model.sources_count,
        "total_articles": model.total_articles,
        "sources": list(model.sources),
        "coalitions": coalitions,
        "history": history,
    }


def to_json(payload: Mapping[str, Any]) -> str:
    """`payload` as pretty-printed JSON, newline-terminated."""
    return json.dumps(payload, indent=2) + "\n"


def build_export(engine: Engine) -> str:
    """Read Storage and return the JSON body for the latest Sentiment."""
    from lpa.config import coalition_names, load_coalition_config
    from lpa.politikku_sentiment import sentiment_page_model

    names = coalition_names(load_coalition_config())
    model = sentiment_page_model(engine=engine, names=names)
    if not model.rows and not model.history:
        raise SystemExit(
            "No Sentiment snapshot stored. Run `python -m lpa.pipeline` to compute one."
        )
    payload = export_model(model, names)
    return to_json(payload)


def main() -> None:
    """Render the export from Storage and write it to disk."""
    import argparse
    from pathlib import Path

    from lpa.storage import connect

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("frontend/public/data"),
        help="directory to write sentiment.json into (default: frontend/public/data)",
    )
    args = parser.parse_args()

    json_body = build_export(connect())
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "sentiment.json").write_text(json_body, encoding="utf-8")
    print(f"Wrote sentiment.json to {args.output_dir}")


if __name__ == "__main__":
    main()
