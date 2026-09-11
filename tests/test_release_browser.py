"""Build real routes using isolated fixture data, then check the resulting site."""

import asyncio
import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from lpa.aggregate import AggregatedSentiment
from lpa.config import load_coalition_config, load_mp_profiles, swing_model_config
from lpa.domain import SeatBaseline
from lpa.politikku_landing import build_and_write_landing_pages
from lpa.politikku_lookup_index import build_and_write_client_index
from lpa.politikku_prerender import prerender_all_routes
from lpa.release_check import check_browser
from lpa.release_data import check_release, export_release
from lpa.storage import connect, save_seat_baselines, save_snapshot
from lpa.swing_model import swing_model


@pytest.mark.browser
def test_build_and_browse_release(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    output = tmp_path / "public"
    shutil.copytree(repo / "frontend/public", output / "app")
    shutil.copytree(repo / "public/fonts", output / "fonts")
    shutil.copytree(repo / "frontend/public/fonts", output / "fonts", dirs_exist_ok=True)
    shutil.copy2(repo / "public/favicon.ico", output / "favicon.ico")
    shutil.copy2(repo / "public/lookup.js", output / "lookup.js")
    url = f"sqlite+pysqlite:///{tmp_path / 'fixture.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    engine = connect(url)
    # Reuse real Seat identifiers, but never publish this synthetic test Projection.
    source = json.loads((repo / "frontend/public/data/projection.json").read_text())
    baseline = [
        SeatBaseline(
            code=s["code"], name=s["name"], state=s["state"], vote_share={"PH": 0.6, "PN": 0.4}
        )
        for s in source["seats"]
    ]
    config = swing_model_config(load_coalition_config())
    day = date(2026, 9, 1)
    save_seat_baselines(engine, baseline)
    save_snapshot(
        engine,
        swing_model(baseline, {}, [], config, day),
        AggregatedSentiment(
            scores={"PH": 0.2}, article_counts={"PH": 3}, total_articles=3, sources=["fixture"]
        ),
        {},
    )
    export_release(engine, output)
    build_and_write_client_index(
        engine, output / "data/lookup-index.json", unresolved_path=None, coverage_path=None
    )
    build_and_write_landing_pages(output)
    engine.dispose()
    profiles = load_mp_profiles()
    monkeypatch.setattr(
        "lpa.politikku_prerender.load_mp_profiles", lambda: {"P.107": profiles["P.107"]}
    )
    asyncio.run(prerender_all_routes(output, output / "app"))
    assert (output / "projection/2026/09/01.html").is_file()
    check_release(output)
    asyncio.run(check_browser(output))
