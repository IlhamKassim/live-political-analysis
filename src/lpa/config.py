"""Reading the Coalition configuration that lives in `data/coalitions.json`.

Government Coalition membership and the party rollup are data, not code, so a
realignment is a config edit (issue #1, story 20).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from lpa.domain import Coalition, SwingModelConfig

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "coalitions.json"


def load_coalition_config(path: Path | None = None) -> Mapping[str, Any]:
    return json.loads((path or DEFAULT_CONFIG_PATH).read_text())


def party_to_coalition(config: Mapping[str, Any]) -> Mapping[str, Coalition]:
    return config["party_to_coalition"]


def coalition_aliases(config: Mapping[str, Any]) -> Mapping[Coalition, list[str]]:
    """How each Coalition is named in coverage, for the Sentiment Scorer."""
    return config["coalition_aliases"]


def swing_model_config(config: Mapping[str, Any], **overrides: Any) -> SwingModelConfig:
    """Build the Swing Model's config from the Coalition configuration file."""
    settings: dict[str, Any] = {
        "government_coalitions": frozenset(config["government_coalitions"]),
        "majority_threshold": config["majority_threshold"],
    }
    settings.update(overrides)
    return SwingModelConfig(**settings)
