"""The Sentiment Scorer's pure seam: article text -> a score per Coalition.

The classifier is injected, so these tests pin attribution and aggregation
without loading a model. The model itself is covered by the smoke test in
tests/test_sentiment_model.py.
"""

from lpa.sentiment import attribute_sentences, score_article

ALIASES = {
    "PH": ["Pakatan Harapan", "PH", "DAP"],
    "PN": ["Perikatan Nasional", "PN", "PAS"],
    "BN": ["Barisan Nasional", "BN", "UMNO"],
}


def fixed_scores(scores: dict[str, float]):
    """A classifier that returns a per-sentence score looked up by substring."""

    def classify(sentences):
        return [
            next((v for k, v in scores.items() if k in sentence), 0.0)
            for sentence in sentences
        ]

    return classify


def test_an_article_mentioning_no_coalition_scores_nothing():
    # Issue #4: "null where no Coalition is mentioned".
    assert score_article("The weather in Putrajaya was fine.", fixed_scores({}), ALIASES) is None


def test_each_coalition_is_scored_only_from_the_sentences_that_name_it():
    text = (
        "Pakatan Harapan was praised for the budget. "
        "UMNO was criticised over the scandal."
    )

    scores = score_article(text, fixed_scores({"praised": 0.8, "criticised": -0.6}), ALIASES)

    assert scores == {"PH": 0.8, "BN": -0.6}


def test_a_component_party_counts_as_a_mention_of_its_coalition():
    # A headline naming DAP is coverage of PH; the alias list carries that.
    scores = score_article("DAP was praised today.", fixed_scores({"praised": 0.5}), ALIASES)

    assert scores == {"PH": 0.5}


def test_a_sentence_naming_two_coalitions_scores_both():
    text = "Pakatan Harapan and Barisan Nasional were praised jointly."

    scores = score_article(text, fixed_scores({"praised": 0.4}), ALIASES)

    assert scores == {"PH": 0.4, "BN": 0.4}


def test_a_coalitions_score_is_the_mean_over_the_sentences_naming_it():
    text = (
        "PH was praised for the budget. "
        "PH was criticised over fuel prices. "
        "UMNO was praised for the reshuffle."
    )

    scores = score_article(text, fixed_scores({"praised": 1.0, "criticised": -0.4}), ALIASES)

    assert scores["PH"] == 0.3  # mean of 1.0 and -0.4
    assert scores["BN"] == 1.0


def test_an_alias_inside_a_longer_word_is_not_a_mention():
    # "PHone" is not PH, and "PASsion" is not PAS.
    assert attribute_sentences("The PHone rang with PASsion.", ALIASES) == {}


def test_a_coalition_is_found_in_bahasa_malaysia_text():
    text = "Kerajaan Pakatan Harapan dipuji rakyat kerana belanjawan itu."

    assert attribute_sentences(text, ALIASES) == {"PH": [text]}


def test_an_alias_that_is_also_an_ordinary_malay_word_needs_its_capitals():
    # "pas" is everyday Bahasa Malaysia; PAS is a party. Case is what tells
    # them apart, and a false mention moves a Coalition's score for no reason.
    assert attribute_sentences("pas ni kita kena kerja lebih.", ALIASES) == {}
    assert attribute_sentences("PAS won the seat.", ALIASES) == {"PN": ["PAS won the seat."]}


def test_a_hyphenated_word_built_on_an_alias_is_not_a_mention():
    # "PAS-ti" ("surely") is not coverage of PAS.
    assert attribute_sentences("PAS-ti menang pada pilihan raya.", ALIASES) == {}


def test_a_title_before_a_name_does_not_end_the_sentence():
    # Malaysian coverage is dense with "Dr.", "Datuk", "Dato'". Splitting there
    # would tear a mention away from the words carrying its sentiment.
    text = "Dr. Mahathir criticised PH sharply. UMNO stayed quiet."

    attributed = attribute_sentences(text, ALIASES)

    assert attributed["PH"] == ["Dr. Mahathir criticised PH sharply"]
    assert attributed["BN"] == ["UMNO stayed quiet."]
