"""Live network proof that the deterministic half of the pipeline actually
works against a real citation, not just a stub. Marked `network` and excluded
from the default run (`pytest -m network` to run it) — the rest of the suite
stays network-free, matching `tests/test_scraper.py`'s approach.

The semantic half (does the source really support the claim) is not
exercised here: that's the subagent's job, not pytest's — see
docs/agents/citation-check.md. Deciding that for this exact fixture, live, is
how issue #24's acceptance criterion 3 was actually satisfied; see the PR
description for the transcript.
"""

from pathlib import Path

import httpx
import pytest

from lpa.citation_check import Verdict, check_page, deferred_judge, http_fetch

pytestmark = pytest.mark.network

FIXTURE = Path(__file__).parent / "fixtures" / "citation_check_demo.html"


def test_both_demo_claims_fetch_their_real_citation():
    html_text = FIXTURE.read_text()

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        results = check_page(html_text, http_fetch(client), deferred_judge)

    assert [r.claim.id for r in results] == ["majority-true", "majority-false"]
    for result in results:
        # Both cite the same live CONTEXT.md; the fetch must succeed for
        # either claim to be judgeable at all.
        assert result.verdict == Verdict.NEEDS_JUDGMENT
        assert result.source is not None
        assert "Majority" in result.source


def test_the_fetched_source_actually_states_the_112_seat_threshold():
    # Confirms the real source content the semantic judgment call was made
    # against — the number that makes "majority-true" true and
    # "majority-false" false.
    html_text = FIXTURE.read_text()

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        results = check_page(html_text, http_fetch(client), deferred_judge)

    assert "112" in results[0].source
