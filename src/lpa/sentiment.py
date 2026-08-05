"""Sentiment Scorer: article text -> a Sentiment score per Coalition.

Split in two so the interesting half is testable without a model:

- `attribute_sentences` and `score_article` are pure. They decide which
  Coalition each sentence is about and aggregate the classifier's output.
- `TransformerClassifier` is the model, loaded lazily and run as local CPU
  inference. No external API is called at any point (ADR 0002).

Attribution is per sentence rather than per article because Malaysian
political coverage routinely praises one Coalition and attacks another in the
same piece; scoring the whole article would average that into noise.
"""

from __future__ import annotations

import re
from typing import Callable, Mapping, Sequence

from lpa.domain import Coalition

Classifier = Callable[[Sequence[str]], Sequence[float]]
"""Scores a batch of sentences, each as a polarity in [-1.0, 1.0]."""

_ABBREVIATIONS = (
    "Dr", "Datuk", "Dato", "Datin", "Tun", "Tan", "Sri", "Hj", "Mr", "Mrs", "Ms",
    "Sdn", "Bhd", "No", "St", "vs", "etc",
)
_SENTENCE = re.compile(
    # A sentence ends at .!? — optionally through a closing quote — but not
    # after a title or initial, which in Malaysian coverage is constant:
    # "Datuk Seri Anwar", "Dr. Mahathir", "S. Subramaniam".
    r"(?<!\b" + r")(?<!\b".join(_ABBREVIATIONS) + r")"
    r"(?<![A-Z])"
    r"[.!?][\"\u2019\u201d)]*\s+|\n+"
)


def attribute_sentences(
    text: str, aliases: Mapping[Coalition, Sequence[str]]
) -> dict[Coalition, list[str]]:
    """Group the sentences of `text` by the Coalitions each one names.

    Matching is case-sensitive and bounded to whole words. Case matters
    because every alias is a proper noun while several are also ordinary
    Bahasa Malaysia words — "pas ni kita kena kerja" is not about PAS.
    Word bounds mean "PHone" is not a mention of PH. A sentence naming two
    Coalitions counts for both.
    """
    patterns = _alias_patterns(aliases)
    found: dict[Coalition, list[str]] = {}
    for sentence in _sentences(text):
        for coalition, pattern in patterns.items():
            if pattern.search(sentence):
                found.setdefault(coalition, []).append(sentence)
    return found


def score_article(
    text: str,
    classify: Classifier,
    aliases: Mapping[Coalition, Sequence[str]],
) -> dict[Coalition, float] | None:
    """Score `text` per Coalition, or None where it names no Coalition at all.

    A Coalition's score is the mean over the sentences naming it, so a piece
    that returns to one Coalition repeatedly does not thereby weigh more.
    """
    by_coalition = attribute_sentences(text, aliases)
    if not by_coalition:
        return None

    sentences = list(dict.fromkeys(s for group in by_coalition.values() for s in group))
    scored = classify(sentences)
    if len(scored) != len(sentences):
        raise ValueError(
            f"classifier returned {len(scored)} scores for {len(sentences)} sentences"
        )
    scores = dict(zip(sentences, scored))
    return {
        coalition: sum(scores[s] for s in group) / len(group)
        for coalition, group in by_coalition.items()
    }


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text) if s.strip()]


def _alias_patterns(
    aliases: Mapping[Coalition, Sequence[str]]
) -> dict[Coalition, re.Pattern[str]]:
    return {
        coalition: re.compile(
            r"(?<![\w-])(?:" + "|".join(re.escape(a) for a in names) + r")(?![\w-])"
        )
        for coalition, names in aliases.items()
    }


DEFAULT_MODEL = "cardiffnlp/twitter-xlm-roberta-base-sentiment"
"""An open-source multilingual XLM-RoBERTa sentiment classifier, per ADR 0002.

Chosen for language coverage: it reads English and Bahasa Malaysia alike,
which a monolingual English model would not. Weights are downloaded once and
cached; inference is local and free.
"""


class TransformerClassifier:
    """A `Classifier` backed by a self-hosted model run on the local CPU.

    The model is loaded on first use, so importing this module — as the tests
    of the pure seam do — costs nothing.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._pipeline = None

    def __call__(self, sentences: Sequence[str]) -> list[float]:
        if not sentences:
            return []
        return [self._polarity(scores) for scores in self._classify(list(sentences))]

    def _classify(self, sentences: list[str]):
        if self._pipeline is None:
            from transformers import pipeline

            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                device=-1,  # CPU: the pipeline runs on free-tier GitHub Actions.
                top_k=None,
                truncation=True,
                max_length=512,
            )
        return self._pipeline(sentences)

    @staticmethod
    def _polarity(scores) -> float:
        """Collapse the model's label probabilities to one polarity in [-1, 1].

        Positive probability minus negative, so a confident call lands near the
        ends of the range and a neutral or torn one lands near zero.
        """
        by_label = {s["label"].lower(): s["score"] for s in scores}
        if "positive" not in by_label and "negative" not in by_label:
            raise ValueError(
                f"model returned unusable labels {sorted(by_label)}; expected "
                "positive/negative/neutral. A checkpoint emitting LABEL_0/1/2 "
                "would otherwise score every sentence a silent 0.0."
            )
        return by_label.get("positive", 0.0) - by_label.get("negative", 0.0)
