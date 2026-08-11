"""Live network proof that the pipeline actually works against a real
citation with a real automated judgment, not just stubs. Marked `network` and
excluded from the default run (`pytest -m network` to run it) — the rest of
the suite stays network-free, matching `tests/test_scraper.py`'s approach.

`test_the_automated_judge_tells_the_true_claim_from_the_wrong_one` is issue
#24's acceptance criterion 3, exercised for real, end to end: fetch the demo
fixture's real citation (`CONTEXT.md`, live off GitHub) and let
`subagent_judge` — an actual `claude -p` subprocess call, not a stub — render
a verdict for both the true and the deliberately wrong claim. A captured run
of this exact test is committed at
`docs/agents/citation-check-demo-transcript.txt`; reproduce it yourself with:

    pytest -m network tests/test_citation_check_live.py -v

(Requires the `claude` CLI on PATH and authenticated — the same one running
this session, if you're an agent reading this.)
"""

from pathlib import Path

import pytest

from lpa.citation_check import Verdict, check_page, deferred_judge, http_fetch, subagent_judge
from lpa.scraper import USER_AGENT, new_client

pytestmark = pytest.mark.network

FIXTURE = Path(__file__).parent / "fixtures" / "citation_check_demo.html"


def _check_demo_fixture(judge):
    html_text = FIXTURE.read_text()
    # `new_client` is the one place this project builds an httpx.Client —
    # same User-Agent, timeout and redirect handling as `main()` and the
    # daily Scraper, so this live test exercises the real configuration
    # rather than a hand-rolled lookalike that can drift from it.
    with new_client(USER_AGENT) as client:
        return check_page(html_text, http_fetch(client), judge)


def test_both_demo_claims_fetch_their_real_citation():
    results = _check_demo_fixture(deferred_judge)

    assert [r.claim.id for r in results] == ["majority-true", "majority-false"]
    for result in results:
        # Both cite the same live CONTEXT.md; the fetch must succeed for
        # either claim to be judgeable at all, against the actual number
        # that makes "majority-true" true and "majority-false" false.
        assert result.verdict == Verdict.NEEDS_JUDGMENT
        assert result.source is not None
        assert "Majority" in result.source
        assert "112" in result.source


def test_the_automated_judge_tells_the_true_claim_from_the_wrong_one():
    # Issue #24 acceptance criterion 3: given a page with a true claim and a
    # deliberately wrong claim citing the same real source, the pass must
    # catch the wrong one automatically — no hand-authored verdict, no human
    # gate. This is the tool's actual default Judge, live.
    results = _check_demo_fixture(subagent_judge())

    by_id = {r.claim.id: r for r in results}
    assert by_id["majority-true"].verdict == Verdict.SUPPORTED
    assert by_id["majority-false"].verdict == Verdict.CONTRADICTED
    assert by_id["majority-true"].verdict != by_id["majority-false"].verdict
