"""The PolitikKu Sentiment Analysis page (#124): model arithmetic and rendered markup."""

from __future__ import annotations

import sys
from datetime import date

from pytest import approx

from lpa.aggregate import AggregatedSentiment
from lpa.domain import ElectionStatus
from lpa.politikku_sentiment import (
    PAGE_PATH,
    build_all_sentiment_languages,
    build_and_write_sentiment_pages,
    main,
    render_sentiment_body,
    render_sentiment_page,
    sentiment_page_model,
)
from lpa.politikku_shell import Language
from lpa.storage import SentimentSnapshot

NOT_CALLED = ElectionStatus(constitutional_deadline=date(2028, 2, 17), source="x")
NAMES = {"PH": "Pakatan Harapan", "PN": "Perikatan Nasional", "BN": "Barisan Nasional"}
LATEST_DAY = date(2026, 8, 23)
SEVEN_DAYS_BACK = date(2026, 8, 16)


def _snapshot(day: date, scores: dict[str, float], counts: dict[str, int]) -> SentimentSnapshot:
    return SentimentSnapshot(
        computed_at=day,
        sentiment=AggregatedSentiment(
            scores=scores,
            article_counts=counts,
            total_articles=sum(counts.values()),
            sources=["Free Malaysia Today", "Malaysiakini"],
        ),
    )


def test_empty_snapshots_produces_empty_sentiment_model():
    model = sentiment_page_model(snapshots=[], names=NAMES, status=NOT_CALLED)

    assert model.total_articles == 0
    assert model.rows == ()
    assert model.history == ()
    assert model.sources == ()
    assert model.sources_count == 0


def test_sentiment_model_calculates_scores_and_7_day_delta():
    history = [
        _snapshot(SEVEN_DAYS_BACK, {"PH": 0.02, "PN": 0.10}, {"PH": 4, "PN": 2}),
        _snapshot(LATEST_DAY, {"PH": 0.10, "PN": -0.05, "BN": 0.0}, {"PH": 8, "BN": 5, "PN": 3}),
    ]
    model = sentiment_page_model(snapshots=history, names=NAMES, status=NOT_CALLED)

    assert model.total_articles == 16
    assert model.updated_at == LATEST_DAY
    assert len(model.rows) == 3
    assert len(model.history) == 2
    assert model.sources_count == 2

    by_coalition = {row.coalition: row for row in model.rows}
    assert by_coalition["PH"].score == 0.10
    assert by_coalition["PH"].article_count == 8
    assert by_coalition["PH"].delta == approx(0.08)
    assert by_coalition["PN"].delta == approx(-0.15)
    assert by_coalition["BN"].delta is None


def test_render_sentiment_body_carries_all_expected_sections():
    history = [
        _snapshot(SEVEN_DAYS_BACK, {"PH": 0.02, "PN": 0.10}, {"PH": 4, "PN": 2}),
        _snapshot(LATEST_DAY, {"PH": 0.10, "PN": -0.05}, {"PH": 8, "PN": 3}),
    ]
    model = sentiment_page_model(snapshots=history, names=NAMES, status=NOT_CALLED)
    body = render_sentiment_body(model, Language.EN)

    assert "News Sentiment Tracker" in body
    assert "Current Sentiment by Coalition" in body
    assert "Historical Sentiment Trend" in body
    assert "Monitored News Outlets" in body
    assert "Pakatan Harapan" in body
    assert "Free Malaysia Today" in body
    assert "Read the full methodology →" in body


def test_render_sentiment_page_wraps_in_shell_with_sentiment_active():
    model = sentiment_page_model(snapshots=[], names=NAMES, status=NOT_CALLED)
    page_en = render_sentiment_page(model, language=Language.EN)
    page_ms = render_sentiment_page(model, language=Language.MS)

    assert '<html lang="en">' in page_en
    assert 'class="sb-item on" href="/sentiment/" aria-current="page"' in page_en

    assert '<html lang="ms">' in page_ms
    assert 'class="sb-item on" href="/ms/sentiment/" aria-current="page"' in page_ms
    assert "Penjejak Sentimen Berita" in page_ms
    assert "Sentimen Semasa Mengikut Gabungan" in page_ms
    assert "Portal Berita Dipantau" in page_ms


def test_render_sentiment_page_carries_real_meta_and_og_tags_at_the_new_path():
    # #143: `/sentiment/` (not the retired flat `sentiment.html`) is now
    # this page's real, individually-addressable path, and `render_shell`
    # derives every meta/OG/canonical tag from `PAGE_PATH` — this pins both
    # the page-specific copy and the URL they now point at in one place.
    model = sentiment_page_model(snapshots=[], names=NAMES, status=NOT_CALLED)
    page_en = render_sentiment_page(model, language=Language.EN)
    page_ms = render_sentiment_page(model, language=Language.MS)

    assert "<title>News Sentiment Analysis — PolitikKu</title>" in page_en
    assert 'og:title" content="News Sentiment Analysis — PolitikKu"' in page_en
    assert 'og:description" content="Daily news sentiment tracker' in page_en
    assert 'og:image" content="https://politikku.my/og-image.png"' in page_en
    assert 'rel="canonical" href="https://politikku.my/sentiment/"' in page_en

    assert "<title>Analisis Sentimen Berita — PolitikKu</title>" in page_ms
    assert 'rel="canonical" href="https://politikku.my/ms/sentiment/"' in page_ms


def test_build_and_write_sentiment_pages(tmp_path, monkeypatch):
    history = [_snapshot(LATEST_DAY, {"PH": 0.10}, {"PH": 8})]
    monkeypatch.setattr("lpa.storage.load_sentiment_snapshots", lambda engine: history)

    en_len, ms_len = build_and_write_sentiment_pages(object(), output_dir=tmp_path)

    en_file = tmp_path / PAGE_PATH / "index.html"
    ms_file = tmp_path / "ms" / PAGE_PATH / "index.html"
    assert en_file.is_file()
    assert ms_file.is_file()
    assert len(en_file.read_bytes()) == en_len
    assert len(ms_file.read_bytes()) == ms_len


def test_build_all_sentiment_languages(monkeypatch):
    history = [_snapshot(LATEST_DAY, {"PH": 0.10}, {"PH": 8})]
    monkeypatch.setattr("lpa.storage.load_sentiment_snapshots", lambda engine: history)

    built = build_all_sentiment_languages(object())
    assert len(built) == 2
    languages = [item[0] for item in built]
    assert Language.EN in languages
    assert Language.MS in languages


def test_main_cli_writes_pages(tmp_path, monkeypatch):
    history = [_snapshot(LATEST_DAY, {"PH": 0.10}, {"PH": 8})]
    monkeypatch.setattr("lpa.storage.connect", lambda: object())
    monkeypatch.setattr("lpa.storage.load_sentiment_snapshots", lambda engine: history)
    monkeypatch.setattr(
        sys,
        "argv",
        ["politikku_sentiment", "--output-dir", str(tmp_path)],
    )

    main()
    assert (tmp_path / "sentiment" / "index.html").is_file()
    assert (tmp_path / "ms" / "sentiment" / "index.html").is_file()
