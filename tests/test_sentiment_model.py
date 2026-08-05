"""Smoke test for the self-hosted model itself (issue #4).

Slow: it downloads model weights on first run and does real CPU inference, so
it is marked `model` and deselected by default. Run it with:

    pytest -m model

Assertions are on the sign of the score, never on exact values — the point is
that the model reads political praise and attack correctly in English *and*
Bahasa Malaysia, not that it produces a particular number. ADR 0002 accepts
that this model is weaker than an LLM on sarcasm and code-switching.
"""

import pytest

from lpa.config import load_coalition_config
from lpa.sentiment import TransformerClassifier, score_article

pytestmark = pytest.mark.model

ENGLISH_PRAISE = "Pakatan Harapan was widely praised for an excellent budget that helps ordinary families."
ENGLISH_ATTACK = "Pakatan Harapan was condemned over a disastrous and corrupt scandal that betrayed voters."
MALAY_PRAISE = "Pakatan Harapan dipuji rakyat kerana belanjawan yang sangat baik dan membantu rakyat."
MALAY_ATTACK = "Pakatan Harapan dikecam kerana skandal rasuah yang teruk dan mengecewakan rakyat."


@pytest.fixture(scope="module")
def aliases():
    return load_coalition_config()["coalition_aliases"]


@pytest.fixture(scope="module")
def classify():
    return TransformerClassifier()


@pytest.mark.parametrize(
    "text,expected_sign",
    [
        (ENGLISH_PRAISE, 1),
        (ENGLISH_ATTACK, -1),
        (MALAY_PRAISE, 1),
        (MALAY_ATTACK, -1),
    ],
    ids=["english-praise", "english-attack", "malay-praise", "malay-attack"],
)
def test_known_sentiment_examples_score_with_the_right_sign(
    text, expected_sign, classify, aliases
):
    scores = score_article(text, classify, aliases)

    assert scores is not None
    assert scores["PH"] * expected_sign > 0


def test_an_article_naming_no_coalition_still_scores_nothing(classify, aliases):
    assert score_article("Heavy rain closed several roads in Kuala Lumpur.", classify, aliases) is None


def test_scoring_makes_no_network_calls_once_the_model_is_cached(classify, aliases):
    # ADR 0002: classification must never hit an external API. Any outbound
    # HTTP during scoring would mean a paid or rate-limited dependency.
    import socket

    classify(["warm up the model"])
    real_connect = socket.socket.connect

    def refuse(self, address):
        raise AssertionError(f"Sentiment scoring attempted a network call to {address}")

    socket.socket.connect = refuse
    try:
        scores = score_article(ENGLISH_PRAISE, classify, aliases)
    finally:
        socket.socket.connect = real_connect

    assert scores is not None
