"""Citation check's pure seam: extraction, orchestration, and every `Judge`
implementation except the network half of `subagent_judge` (its subprocess
call is stubbed here — no network, no real `claude` CLI invocation).
`http_fetch` is exercised against a stub client, the same way
`tests/test_scraper.py` stubs `httpx`.

The live, real-network-and-real-subagent demonstration (issue #24's
acceptance criterion 3: run against a page with a true and a deliberately
wrong claim, confirm the automated judge tells them apart) lives in
`tests/test_citation_check_live.py`, marked `network` and excluded from the
default run.
"""

import json
import subprocess

from lpa.citation_check import (
    Claim,
    CitationCheckResult,
    FetchResult,
    Verdict,
    check_page,
    deferred_judge,
    extract_claims,
    http_fetch,
    override_judge,
    subagent_judge,
    verdicts_from_file,
)

# --- extraction --------------------------------------------------------


def test_a_claim_with_a_citation_is_extracted():
    html = '<p data-claim data-cite="https://x/1">GPS formed in 2018.</p>'

    claims = extract_claims(html)

    assert claims == [Claim(id="claim-1", text="GPS formed in 2018.", citation="https://x/1")]


def test_a_claim_with_no_citation_still_extracts_with_citation_none():
    # Issue #24: a claim with no citation must be flagged, not skipped.
    html = "<p data-claim>GPS formed in 2018.</p>"

    assert extract_claims(html) == [Claim(id="claim-1", text="GPS formed in 2018.", citation=None)]


def test_text_outside_a_claim_element_is_not_a_claim():
    html = "<p>Just prose.</p><p data-claim>The real claim.</p>"

    assert [c.text for c in extract_claims(html)] == ["The real claim."]


def test_multiple_claims_get_sequential_ids_in_document_order():
    html = (
        '<p data-claim data-cite="https://x/1">First.</p>'
        '<p data-claim data-cite="https://x/2">Second.</p>'
    )

    claims = extract_claims(html)

    assert [c.id for c in claims] == ["claim-1", "claim-2"]


def test_an_explicit_id_attribute_is_kept_instead_of_the_auto_id():
    # So a verdicts file survives claims being reordered or ones added
    # elsewhere on the page.
    html = '<p data-claim id="gps-founding" data-cite="https://x/1">GPS formed in 2018.</p>'

    assert extract_claims(html)[0].id == "gps-founding"


def test_nested_markup_inside_a_claim_collapses_into_its_text():
    html = '<p data-claim data-cite="https://x/1">GPS is a <strong>Sarawak</strong>-based coalition.</p>'

    assert extract_claims(html)[0].text == "GPS is a Sarawak-based coalition."


def test_whitespace_inside_a_claim_is_normalised():
    html = '<p data-claim data-cite="https://x/1">\n  GPS   formed\n  in 2018.\n</p>'

    assert extract_claims(html)[0].text == "GPS formed in 2018."


def test_a_void_element_inside_a_claim_does_not_break_extraction():
    html = '<p data-claim data-cite="https://x/1">Line one.<br>Line two.</p>'

    assert extract_claims(html)[0].text == "Line one.Line two."


def test_a_page_with_no_claims_extracts_nothing():
    assert extract_claims("<html><body><p>Nothing tagged here.</p></body></html>") == []


# --- check_page orchestration -------------------------------------------


def fetch_map(sources: dict[str, str]):
    def fetch(url: str) -> FetchResult:
        if url not in sources:
            return FetchResult(text=None, error="404")
        return FetchResult(text=sources[url], error=None)

    return fetch


def substring_judge(text_that_must_appear: str):
    """A toy Judge: SUPPORTED if the source contains a marker string, else
    CONTRADICTED. Stands in for real semantic judgment in these pure tests —
    see the module docstring for why no real Judge ships with the tool."""

    def judge(claim: Claim, source_text: str):
        if text_that_must_appear in source_text:
            return Verdict.SUPPORTED, "marker text present in source"
        return Verdict.CONTRADICTED, "marker text absent from source"

    return judge


def test_a_claim_with_no_citation_is_flagged_without_fetching():
    html = "<p data-claim>Unsourced claim.</p>"

    def explode(url):
        raise AssertionError("fetched a claim with no citation")

    results = check_page(html, explode, deferred_judge)

    assert results == [
        CitationCheckResult(
            Claim(id="claim-1", text="Unsourced claim.", citation=None),
            Verdict.NO_CITATION,
            "no citation attached to this claim",
        )
    ]
    assert not results[0].passed


def test_a_citation_that_fails_to_fetch_is_flagged_without_judging():
    html = '<p data-claim data-cite="https://x/missing">A claim.</p>'

    def explode(claim, source_text):
        raise AssertionError("judged a claim whose source never fetched")

    results = check_page(html, fetch_map({}), explode)

    assert results[0].verdict == Verdict.FETCH_FAILED
    assert results[0].detail == "404"
    assert not results[0].passed


def test_a_claim_the_source_supports_is_marked_supported():
    html = (
        '<p data-claim data-cite="https://x/majority">'
        "A Coalition needs 112 of the 222 seats for a Majority."
        "</p>"
    )
    fetch = fetch_map({"https://x/majority": "Holding more than half the 222 seats (112+) is a Majority."})

    results = check_page(html, fetch, substring_judge("112"))

    assert results[0].verdict == Verdict.SUPPORTED
    assert results[0].passed


def test_a_claim_the_source_contradicts_is_caught():
    # Issue #24 acceptance criterion 3, exercised at the unit level: a
    # deliberately wrong claim must be flagged, not passed silently.
    html = (
        '<p data-claim data-cite="https://x/majority">'
        "A Coalition needs only 100 of the 222 seats for a Majority."
        "</p>"
    )
    fetch = fetch_map({"https://x/majority": "Holding more than half the 222 seats (112+) is a Majority."})

    results = check_page(html, fetch, substring_judge("100"))

    assert results[0].verdict == Verdict.CONTRADICTED
    assert not results[0].passed


def test_the_source_text_is_carried_on_the_result():
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "the fetched source"})

    results = check_page(html, fetch, substring_judge("the fetched source"))

    assert results[0].source == "the fetched source"


def test_a_page_with_several_claims_checks_each_independently():
    html = (
        '<p data-claim data-cite="https://x/ok">True one.</p>'
        "<p data-claim>No citation.</p>"
        '<p data-claim data-cite="https://x/missing">Never fetches.</p>'
    )
    fetch = fetch_map({"https://x/ok": "source text"})

    results = check_page(html, fetch, substring_judge("source text"))

    assert [r.verdict for r in results] == [
        Verdict.SUPPORTED,
        Verdict.NO_CITATION,
        Verdict.FETCH_FAILED,
    ]


# --- deferred_judge and NEEDS_JUDGMENT is a failure ----------------------


def test_deferred_judge_marks_every_fetched_claim_needs_judgment():
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    results = check_page(html, fetch, deferred_judge)

    assert results[0].verdict == Verdict.NEEDS_JUDGMENT
    assert not results[0].passed  # unjudged must not read as passed


# --- verdicts_from_file ---------------------------------------------------


def test_verdicts_from_file_applies_a_recorded_verdict(tmp_path):
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(
        json.dumps([{"id": "claim-1", "verdict": "supported", "detail": "checked by hand"}])
    )
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    results = check_page(html, fetch, verdicts_from_file(verdicts_path))

    assert results[0].verdict == Verdict.SUPPORTED
    assert results[0].detail == "checked by hand"


def test_verdicts_from_file_applies_a_contradicted_verdict(tmp_path):
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(
        json.dumps([{"id": "claim-1", "verdict": "contradicted", "detail": "source says 112, not 100"}])
    )
    html = '<p data-claim data-cite="https://x/1">Wrong claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    results = check_page(html, fetch, verdicts_from_file(verdicts_path))

    assert results[0].verdict == Verdict.CONTRADICTED
    assert not results[0].passed


def test_a_claim_missing_from_the_verdicts_file_stays_unjudged_not_passed():
    # A subagent that never reached this claim must not thereby pass it.
    verdicts_path_entries = json.dumps([{"id": "claim-999", "verdict": "supported", "detail": "x"}])
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    def judge_from_string(raw: str):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.json"
            p.write_text(raw)
            return verdicts_from_file(p)

    results = check_page(html, fetch, judge_from_string(verdicts_path_entries))

    assert results[0].verdict == Verdict.NEEDS_JUDGMENT
    assert not results[0].passed


def test_verdicts_from_file_reports_an_entry_missing_the_verdict_field():
    # A hand-authored or LLM-written file can be malformed; a bare
    # KeyError/ValueError crash would abort the whole run over one bad entry.
    verdicts_path_entries = json.dumps([{"id": "claim-1", "detail": "forgot the verdict"}])
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    def judge_from_string(raw: str):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.json"
            p.write_text(raw)
            return verdicts_from_file(p)

    results = check_page(html, fetch, judge_from_string(verdicts_path_entries))

    assert results[0].verdict == Verdict.NEEDS_JUDGMENT
    assert "verdict" in results[0].detail


def test_verdicts_from_file_reports_an_unrecognised_verdict_value(tmp_path):
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(json.dumps([{"id": "claim-1", "verdict": "probably true?"}]))
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    results = check_page(html, fetch, verdicts_from_file(verdicts_path))

    assert results[0].verdict == Verdict.NEEDS_JUDGMENT
    assert "probably true?" in results[0].detail


# --- override_judge --------------------------------------------------------


def test_override_judge_prefers_the_overrides_verdict_when_present(tmp_path):
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(json.dumps([{"id": "claim-1", "verdict": "contradicted", "detail": "human says no"}]))
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    def automated_always_supports(claim, source_text):
        raise AssertionError("fallback judge should not be reached when the override has an opinion")

    judge = override_judge(verdicts_from_file(verdicts_path), automated_always_supports)
    results = check_page(html, fetch, judge)

    assert results[0].verdict == Verdict.CONTRADICTED
    assert results[0].detail == "human says no"


def test_override_judge_falls_through_to_the_automated_judge_when_absent(tmp_path):
    # A verdicts file only needs to cover the claims someone wants to
    # override — everything else still gets judged automatically.
    verdicts_path = tmp_path / "verdicts.json"
    verdicts_path.write_text(json.dumps([{"id": "some-other-claim", "verdict": "supported"}]))
    html = '<p data-claim data-cite="https://x/1">A claim.</p>'
    fetch = fetch_map({"https://x/1": "source text"})

    judge = override_judge(verdicts_from_file(verdicts_path), substring_judge("source text"))
    results = check_page(html, fetch, judge)

    assert results[0].verdict == Verdict.SUPPORTED


# --- subagent_judge (the automated Judge) ----------------------------------
#
# These stub the subprocess call (`run`) rather than actually invoking the
# `claude` CLI — no network, no real subagent, fast and deterministic. The
# real end-to-end call is exercised live in test_citation_check_live.py.


class FakeCompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _claude_stdout(result_json: str) -> str:
    """What `claude -p --output-format json` prints: an envelope whose
    "result" field holds the model's raw text reply."""
    return json.dumps({"type": "result", "subtype": "success", "result": result_json})


def test_subagent_judge_parses_a_supported_verdict():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return FakeCompletedProcess(_claude_stdout('{"verdict": "supported", "detail": "matches"}'))

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "112 seats is a Majority.", "https://x/1"), "112 or more is a Majority.")

    assert verdict == Verdict.SUPPORTED
    assert detail == "matches"


def test_subagent_judge_parses_a_contradicted_verdict():
    def fake_run(cmd, **kwargs):
        return FakeCompletedProcess(_claude_stdout('{"verdict": "contradicted", "detail": "source says 112"}'))

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "100 seats is a Majority.", "https://x/1"), "112 or more is a Majority.")

    assert verdict == Verdict.CONTRADICTED
    assert detail == "source says 112"


def test_subagent_judge_parses_an_unclear_verdict():
    def fake_run(cmd, **kwargs):
        return FakeCompletedProcess(_claude_stdout('{"verdict": "unclear", "detail": "ambiguous"}'))

    judge = subagent_judge(run=fake_run)
    verdict, _ = judge(Claim("claim-1", "Something vague.", "https://x/1"), "some unrelated text")

    assert verdict == Verdict.UNCLEAR


def test_subagent_judge_embeds_the_claim_and_source_in_the_prompt():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess(_claude_stdout('{"verdict": "supported", "detail": "x"}'))

    judge = subagent_judge(run=fake_run)
    judge(Claim("claim-1", "GPS formed in 2018.", "https://x/1"), "GPS was formed in 2018 in Sarawak.")

    [cmd] = calls
    prompt = cmd[cmd.index("-p") + 1]
    assert "GPS formed in 2018." in prompt
    assert "GPS was formed in 2018 in Sarawak." in prompt


def test_subagent_judge_grants_no_tools_to_the_subagent():
    # The claim and source are already in the prompt; the subagent must not
    # be able to browse or read files to "judge" against something else.
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompletedProcess(_claude_stdout('{"verdict": "supported", "detail": "x"}'))

    subagent_judge(run=fake_run)(Claim("claim-1", "x", "https://x/1"), "y")

    [cmd] = calls
    assert cmd[cmd.index("--allowedTools") + 1] == ""


def test_subagent_judge_runs_from_a_neutral_working_directory():
    # Not this project's checkout: running there lets the subagent
    # auto-discover CLAUDE.md and go exploring instead of just judging (see
    # subagent_judge's docstring) — a bare cwd has nothing to discover.
    kwargs_seen = []

    def fake_run(cmd, **kwargs):
        kwargs_seen.append(kwargs)
        return FakeCompletedProcess(_claude_stdout('{"verdict": "supported", "detail": "x"}'))

    subagent_judge(run=fake_run)(Claim("claim-1", "x", "https://x/1"), "y")

    [kwargs] = kwargs_seen
    assert kwargs["cwd"] is not None
    assert not str(kwargs["cwd"]).rstrip("/").endswith("live-political-analysis")


def test_subagent_judge_extracts_the_verdict_from_a_reply_with_preamble():
    # A subagent that ignores "reply with ONLY JSON" and wraps its answer in
    # explanation and a markdown fence should still be readable.
    def fake_run(cmd, **kwargs):
        reply = (
            "Let me check the source text against the claim.\n\n"
            "```json\n"
            '{"verdict": "contradicted", "detail": "source says 112, not 100"}\n'
            "```"
        )
        return FakeCompletedProcess(_claude_stdout(reply))

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "x", "https://x/1"), "y")

    assert verdict == Verdict.CONTRADICTED
    assert detail == "source says 112, not 100"


def test_subagent_judge_treats_a_nonzero_exit_as_needs_judgment():
    def fake_run(cmd, **kwargs):
        return FakeCompletedProcess(stderr="rate limited", returncode=1)

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "x", "https://x/1"), "y")

    assert verdict == Verdict.NEEDS_JUDGMENT
    assert "rate limited" in detail


def test_subagent_judge_treats_unparsable_output_as_needs_judgment():
    def fake_run(cmd, **kwargs):
        return FakeCompletedProcess(stdout="not json at all")

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "x", "https://x/1"), "y")

    assert verdict == Verdict.NEEDS_JUDGMENT
    assert detail


def test_subagent_judge_treats_an_out_of_vocabulary_verdict_as_needs_judgment():
    def fake_run(cmd, **kwargs):
        return FakeCompletedProcess(_claude_stdout('{"verdict": "definitely maybe", "detail": "x"}'))

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "x", "https://x/1"), "y")

    assert verdict == Verdict.NEEDS_JUDGMENT


def test_subagent_judge_treats_a_launch_failure_as_needs_judgment():
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("claude: command not found")

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "x", "https://x/1"), "y")

    assert verdict == Verdict.NEEDS_JUDGMENT
    assert "claude: command not found" in detail


def test_subagent_judge_treats_a_timeout_as_needs_judgment():
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    judge = subagent_judge(run=fake_run)
    verdict, detail = judge(Claim("claim-1", "x", "https://x/1"), "y")

    assert verdict == Verdict.NEEDS_JUDGMENT


def test_check_page_wires_subagent_judge_end_to_end_with_a_stub_run():
    # Same shape as issue #24 acceptance criterion 3, but with the subprocess
    # stubbed: a true and a deliberately wrong claim citing the same source
    # must land on different verdicts through the real default Judge.
    html = (
        '<p data-claim id="true-claim" data-cite="https://x/1">'
        "A Coalition needs 112 seats for a Majority."
        "</p>"
        '<p data-claim id="false-claim" data-cite="https://x/1">'
        "A Coalition needs 100 seats for a Majority."
        "</p>"
    )
    fetch = fetch_map({"https://x/1": "112 or more of the 222 seats is a Majority."})

    def fake_run(cmd, **kwargs):
        prompt = cmd[cmd.index("-p") + 1]
        if "needs 100 seats" in prompt:
            return FakeCompletedProcess(_claude_stdout('{"verdict": "contradicted", "detail": "source says 112"}'))
        return FakeCompletedProcess(_claude_stdout('{"verdict": "supported", "detail": "matches"}'))

    results = check_page(html, fetch, subagent_judge(run=fake_run))

    by_id = {r.claim.id: r for r in results}
    assert by_id["true-claim"].verdict == Verdict.SUPPORTED
    assert by_id["false-claim"].verdict == Verdict.CONTRADICTED
    assert by_id["true-claim"].verdict != by_id["false-claim"].verdict


# --- http_fetch -------------------------------------------------------


class StubResponse:
    def __init__(self, status_code=200, text="", content_type="text/html"):
        self.status_code = status_code
        self.text = text
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("error", request=None, response=self)


class StubClient:
    def __init__(self, response):
        self.response = response

    def get(self, url):
        return self.response


def test_http_fetch_strips_html_when_the_content_type_says_html():
    fetch = http_fetch(StubClient(StubResponse(text="<p>Hello <b>world</b></p>", content_type="text/html")))

    result = fetch("https://x/1")

    assert result.ok
    assert result.text == "Hello world"


def test_http_fetch_leaves_plain_text_untouched():
    fetch = http_fetch(StubClient(StubResponse(text="raw plain text", content_type="text/plain")))

    result = fetch("https://x/1")

    assert result.text == "raw plain text"


def test_http_fetch_truncates_a_long_source():
    from lpa.citation_check import MAX_SOURCE_CHARS

    fetch = http_fetch(StubClient(StubResponse(text="x" * (MAX_SOURCE_CHARS * 2), content_type="text/plain")))

    result = fetch("https://x/1")

    assert len(result.text) == MAX_SOURCE_CHARS


def test_http_fetch_reports_a_failed_status_as_an_error_not_a_crash():
    fetch = http_fetch(StubClient(StubResponse(status_code=404)))

    result = fetch("https://x/1")

    assert not result.ok
    assert result.text is None
    assert "404" in result.error or "Error" in result.error


# --- http_fetch + RobotsPolicy -----------------------------------------
#
# http_fetch defaults to no RobotsPolicy (an attended, low-volume, authoring
# tool — see its docstring), but when main() passes one it must actually be
# respected: `lpa.scraper.Scraper` treats this policy as mandatory before
# any outbound fetch, and there's no reason a citation should be exempt from
# a robots.txt that says no.


class StubRobots:
    def __init__(self, allowed):
        self.allowed = allowed
        self.waited = []
        self.limiter = self

    def is_allowed(self, url):
        return self.allowed

    def refusal_reason(self, url):
        return "robots.txt disallows this path"

    def crawl_delay(self, url):
        return None

    def wait_turn(self, url, crawl_delay=None):
        self.waited.append(url)


def test_http_fetch_respects_a_disallowing_robots_policy():
    robots = StubRobots(allowed=False)
    fetch = http_fetch(StubClient(StubResponse(text="should never be read")), robots=robots)

    result = fetch("https://x/1")

    assert not result.ok
    assert "robots.txt" in result.error


def test_http_fetch_proceeds_and_waits_its_turn_when_robots_allows():
    robots = StubRobots(allowed=True)
    fetch = http_fetch(StubClient(StubResponse(text="ok", content_type="text/plain")), robots=robots)

    result = fetch("https://x/1")

    assert result.ok
    assert result.text == "ok"
    assert robots.waited == ["https://x/1"]


def test_http_fetch_with_no_robots_policy_skips_the_check_entirely():
    # The documented default: no RobotsPolicy given, no gate applied.
    fetch = http_fetch(StubClient(StubResponse(text="ok", content_type="text/plain")))

    result = fetch("https://x/1")

    assert result.ok
