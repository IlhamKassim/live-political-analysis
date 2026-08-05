"""Aggregation: the day's scored Articles -> one Sentiment per Coalition.

Pure. Sits between the Sentiment Scorer and the Swing Model, which wants a
single number per Coalition rather than a pile of per-Article scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from lpa.domain import Article, Coalition


@dataclass(frozen=True)
class AggregatedSentiment:
    """The day's Sentiment per Coalition, with the evidence behind it.

    The counts and sources travel with the scores because a Projection built
    on three articles should not look like one built on three hundred (issue
    #1, user stories 4 and 5).
    """

    scores: Mapping[Coalition, float] = field(default_factory=dict)
    article_counts: Mapping[Coalition, int] = field(default_factory=dict)
    total_articles: int = 0
    sources: Sequence[str] = field(default_factory=list)
    """Every outlet read, whether or not its coverage named a Coalition —
    user story 5 asks which sources feed the score, and an outlet that was
    read and found nothing political is still part of that answer."""


def aggregate_sentiment(
    scored_articles: Iterable[tuple[Article, Mapping[Coalition, float] | None]],
) -> AggregatedSentiment:
    """Average each Coalition's score over the Articles that actually named it.

    An Article naming no Coalition contributes nothing to any score — it is
    absence of evidence, not evidence of neutrality — but it still counts
    towards the day's total, which is what says how much was read.
    """
    totals: dict[Coalition, float] = {}
    counts: dict[Coalition, int] = {}
    sources: set[str] = set()
    total_articles = 0

    for article, scores in scored_articles:
        total_articles += 1
        sources.add(article.source)
        if not scores:
            continue
        for coalition, score in scores.items():
            totals[coalition] = totals.get(coalition, 0.0) + score
            counts[coalition] = counts.get(coalition, 0) + 1

    return AggregatedSentiment(
        scores={c: totals[c] / counts[c] for c in totals},
        article_counts=counts,
        total_articles=total_articles,
        sources=sorted(sources),
    )
