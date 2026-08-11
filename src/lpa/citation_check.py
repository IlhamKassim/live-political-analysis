"""Citation check: does a page's claim actually say what its citation says?

Every content ticket under #22 (the civic-education pages) runs this before its
content counts as done — issue #22's "Verification — settled" comment requires
it to run standalone, with **no per-claim human gate**. So "does this citation
say what we claim" has to be answered by something other than a human reading
each pair by eye.

The module is in two halves, split the same way `sentiment.py` splits attribution
from classification:

- `extract_claims` and `check_page` are pure and fully testable: given a page
  and an injected `Fetcher` + `Judge`, they decide which claims lack a
  citation, which citations fail to fetch, and — via the injected `Judge` —
  which claims the fetched source does and doesn't support. Nothing here
  reaches the network or calls a model.
- `http_fetch` is the real `Fetcher`: a source is fetched over HTTP once, with
  HTML reduced to plain text via `lpa.scraper.strip_html`.
- `subagent_judge` is the real `Judge`: it shells out to the `claude` CLI —
  the same subscription-seat tool an authoring session already runs under,
  not the metered Anthropic API ADR 0002 rules out for unattended/scripted
  use — with the claim and fetched source embedded directly in the prompt.
  No tools are granted to that subagent call; it never browses or reads
  files, it only judges the text it was given. This is the automated
  semantic step issue #24 asked for: the tool renders SUPPORTED,
  CONTRADICTED, or UNCLEAR itself, with no human required to have
  pre-written the answer.

CLI protocol (see docs/agents/citation-check.md for the full walkthrough):

    python -m lpa.citation_check PAGE.html

extracts every claim, fetches every citation, flags claims with no citation
or a citation that failed to fetch, and judges everything else automatically
via `subagent_judge` — one `claude -p` call per fetched claim, coming back
SUPPORTED, CONTRADICTED, or UNCLEAR (a real, rendered judgment — "the source
doesn't clearly settle it" is a legitimate outcome for a genuinely ambiguous
claim, and counts as a failure like any non-SUPPORTED verdict). The report
prints immediately; the run exits non-zero if anything is unsupported,
contradicted, uncited, unfetchable, or still unjudged after that automated
pass — nothing here passes silently. A claim where no judgment was rendered
at all — a malformed subagent reply, a `claude` CLI failure — is written to
`PAGE.html.pending.json` for a human or another agent to look at directly;
that file is diagnostic output for that failure mode, not a required input.

`--verdicts verdicts.json` is an optional override, never a required step: a
verdict recorded there for a given claim id wins over what the automated
judge decided (e.g. a human correcting one call), and any claim id the file
doesn't mention still goes through `subagent_judge` as normal.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

import httpx

from lpa.scraper import USER_AGENT, RobotsPolicy, new_client, strip_html

MAX_SOURCE_CHARS = 8_000
"""A fetched source is truncated to this many characters before it reaches a
Judge or a pending report — long enough to carry real context, short enough
that a subagent reading it costs a bounded amount of context."""

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5"
"""The model `subagent_judge` runs the `claude` CLI as.

Judging "does this source support this claim" is a bounded reading-
comprehension task, not open-ended reasoning, so the cheapest model that
reads reliably is the right default — override with `--judge-model` for a
page whose claims need more care.
"""

_VOID_ELEMENTS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
     "meta", "param", "source", "track", "wbr"}
)


class Verdict(StrEnum):
    """Where a claim landed. Every value but SUPPORTED is a failure —
    `CitationCheckResult.passed` treats them alike so nothing new added here
    later can accidentally pass silently."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNCLEAR = "unclear"
    NO_CITATION = "no_citation"
    FETCH_FAILED = "fetch_failed"
    NEEDS_JUDGMENT = "needs_judgment"
    """Fetched successfully but no Judge has rendered a verdict for it — the
    state `deferred_judge` returns, what `subagent_judge` falls back to when
    it can't get a usable answer, and what a claim missing from a verdicts
    file stays at. Counts as a failure precisely so an unjudged claim cannot
    be mistaken for a supported one."""


@dataclass(frozen=True)
class Claim:
    """One factual claim on a page, as `extract_claims` found it."""

    id: str
    text: str
    citation: str | None
    """The cited source's URL, or None where the page attached no citation
    at all — extraction still surfaces the claim so it can be flagged rather
    than silently skipped."""


@dataclass(frozen=True)
class FetchResult:
    """What came back from fetching a citation. Exactly one of the two
    fields is set — never both, and never neither."""

    text: str | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class CitationCheckResult:
    claim: Claim
    verdict: Verdict
    detail: str
    source: str | None = None
    """The fetched source text the verdict was decided against, where a
    source was fetched at all. Carried through so a CLI or subagent can
    show it without re-fetching."""

    @property
    def passed(self) -> bool:
        return self.verdict == Verdict.SUPPORTED


Fetcher = Callable[[str], FetchResult]
"""Fetch a citation's URL and return its content, or why it couldn't be
fetched. Injected so `check_page` never has to reach the network itself —
`http_fetch` below is the real implementation; tests use a stub."""

Judge = Callable[[Claim, str], tuple[Verdict, str]]
"""Decide whether the second argument (a fetched source's text) supports a
Claim's text. Must return SUPPORTED, CONTRADICTED, or UNCLEAR when it
actually renders a judgment; NEEDS_JUDGMENT is reserved for a Judge that
explicitly declines to (`deferred_judge`, or `subagent_judge` when it
couldn't get a usable response) — `check_page` itself never asks a Judge
about a claim it couldn't fetch a source for in the first place, so
NO_CITATION and FETCH_FAILED never reach a Judge at all."""


def check_page(html_text: str, fetch: Fetcher, judge: Judge) -> list[CitationCheckResult]:
    """Check every claim on a page: extract, fetch, judge.

    A claim with no citation or an unfetchable one is flagged immediately and
    never reaches the Judge — there is nothing for it to compare against.
    """
    results = []
    for claim in extract_claims(html_text):
        if not claim.citation:
            results.append(
                CitationCheckResult(
                    claim, Verdict.NO_CITATION, "no citation attached to this claim"
                )
            )
            continue
        fetched = fetch(claim.citation)
        if not fetched.ok:
            results.append(CitationCheckResult(claim, Verdict.FETCH_FAILED, fetched.error or ""))
            continue
        verdict, detail = judge(claim, fetched.text or "")
        results.append(CitationCheckResult(claim, verdict, detail, source=fetched.text))
    return results


def deferred_judge(claim: Claim, source_text: str) -> tuple[Verdict, str]:
    """A `Judge` that defers every fetched claim rather than judging it.

    Not the default — `main()` uses `subagent_judge` unless told otherwise —
    but useful on its own: as the pure orchestration tests' baseline (judging
    is not what those tests exercise), and as an explicit "just show me what
    fetched" mode. A page checked with this Judge and no follow-up fails
    closed rather than reporting green, same as any other unjudged claim.
    """
    return Verdict.NEEDS_JUDGMENT, "not judged — see docs/agents/citation-check.md"


def override_judge(overrides: Judge, fallback: Judge) -> Judge:
    """Layer a hand-authored verdicts file over an automated Judge.

    `overrides` wins for any claim id it has an opinion on — a human's
    correction to what `fallback` (normally `subagent_judge`) decided. A
    claim id the overrides file doesn't mention comes back NEEDS_JUDGMENT
    from `verdicts_from_file`, which this treats as "no opinion" and falls
    through to `fallback` — so a verdicts file only ever needs to cover the
    claims someone actually wants to override, never every claim on the page.
    """

    def judge(claim: Claim, source_text: str) -> tuple[Verdict, str]:
        verdict, detail = overrides(claim, source_text)
        if verdict != Verdict.NEEDS_JUDGMENT:
            return verdict, detail
        return fallback(claim, source_text)

    return judge


def verdicts_from_file(path: Path) -> Judge:
    """A `Judge` backed by a hand-authored verdicts file, keyed by claim id.

    This is how a human's correction re-enters the pipeline — see
    `override_judge`. A claim id absent from the file, or an entry missing a
    usable `verdict` field, is left NEEDS_JUDGMENT rather than assumed
    supported, with a detail explaining why so a malformed file surfaces as
    a readable message rather than a crash.
    """
    entries = {
        entry["id"]: entry for entry in json.loads(path.read_text(encoding="utf-8"))
    }

    def judge(claim: Claim, source_text: str) -> tuple[Verdict, str]:
        entry = entries.get(claim.id)
        if entry is None:
            return Verdict.NEEDS_JUDGMENT, f"no verdict recorded for {claim.id!r} in {path}"
        try:
            verdict = Verdict(entry["verdict"])
        except KeyError:
            return (
                Verdict.NEEDS_JUDGMENT,
                f"{path}: entry for {claim.id!r} has no \"verdict\" field",
            )
        except ValueError:
            allowed = ", ".join(v.value for v in Verdict)
            return (
                Verdict.NEEDS_JUDGMENT,
                f"{path}: entry for {claim.id!r} has verdict {entry['verdict']!r}, "
                f"which isn't one of: {allowed}",
            )
        return verdict, entry.get("detail", "")

    return judge


def subagent_judge(
    model: str = DEFAULT_JUDGE_MODEL,
    timeout: float = 120.0,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Judge:
    """The real `Judge`: spawns a `claude -p` subagent per claim.

    The claim and the fetched source text are embedded directly in the
    prompt (see `_judge_prompt`) and no tools are granted (`--allowedTools
    ""`), so the subagent never browses or reads a file — it only judges the
    text it was handed, the same information a pure `Judge` stub gets in
    tests. `run` is injected (defaulting to `subprocess.run`) so tests can
    stub the CLI call the same way `http_fetch` takes an injected client.

    The call runs with its working directory set to a bare temp directory
    rather than this project's checkout. Tried against this repo directly, a
    `claude -p` call auto-discovers `CLAUDE.md`, decides a citation-judgment
    prompt looks like agent work, and goes exploring — 19 turns and $0.19 for
    one claim in testing, instead of a few cents. A neutral cwd with nothing
    to discover keeps the call to what it's actually here to do.

    Any failure — the `claude` binary missing, a timeout, an unparsable or
    out-of-vocabulary response — comes back NEEDS_JUDGMENT with a detail
    explaining why, rather than raising: one claim's judge call failing must
    not crash the whole page's check.
    """

    def judge(claim: Claim, source_text: str) -> tuple[Verdict, str]:
        prompt = _judge_prompt(claim, source_text)
        try:
            completed = run(
                [
                    "claude", "-p", prompt,
                    "--model", model,
                    "--output-format", "json",
                    "--allowedTools", "",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return (
                Verdict.NEEDS_JUDGMENT,
                f"subagent judge unavailable: {type(error).__name__}: {error}",
            )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()[:200]
            return Verdict.NEEDS_JUDGMENT, f"subagent judge exited {completed.returncode}: {stderr}"
        return _parse_subagent_verdict(completed.stdout)

    return judge


def _judge_prompt(claim: Claim, source_text: str) -> str:
    return (
        "You are fact-checking one claim on a webpage against its cited source. "
        "Decide whether the source actually supports the claim — not just that "
        "it's on-topic, but that it states the specific fact the claim states.\n\n"
        f"CLAIM:\n{claim.text}\n\n"
        f"SOURCE (already fetched from {claim.citation} — this is the complete "
        "text you must judge against):\n"
        f"{source_text}\n\n"
        "You have no tool access in this session. Do not attempt to fetch the "
        "URL yourself or ask for permission to — the SOURCE text above is the "
        "actual fetched content and is all you get; judge from it alone.\n\n"
        "Reply with ONLY a JSON object and nothing else — no markdown fences, "
        "no reasoning or explanation outside the JSON:\n"
        '{"verdict": "supported" | "contradicted" | "unclear", "detail": "one sentence why"}\n'
        'Use "contradicted" when the source states something different from the '
        'claim. Use "unclear" when the source doesn\'t clearly settle it either '
        'way. Do not default to "supported" when in doubt.'
    )


_VERDICT_JSON = re.compile(r'\{[^{}]*"verdict"\s*:\s*"[^"]*"[^{}]*\}')
"""Matches a flat `{"verdict": ..., "detail": ...}` object anywhere in a
subagent's reply. The prompt asks for nothing else in the response, but a
model that ignores that and wraps the JSON in a code fence or a sentence of
preamble should still be readable — the schema has no nested braces, so the
last such object in the text is taken as the actual answer (over any earlier
JSON-shaped text in a preamble)."""


def _parse_subagent_verdict(stdout: str) -> tuple[Verdict, str]:
    """Unpack `claude -p --output-format json`'s envelope and the verdict
    JSON it should contain in `result`, per `_judge_prompt`'s instructions.

    Tolerates the result not being *pure* JSON (a code fence, a sentence of
    preamble) by pulling out the last `{"verdict": ...}`-shaped substring —
    see `_VERDICT_JSON` — rather than requiring the whole field to parse.
    """
    try:
        payload = json.loads(stdout)
        result = payload["result"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        preview = stdout.strip()[:200]
        return (
            Verdict.NEEDS_JUDGMENT,
            f"could not parse subagent output as the claude CLI's json envelope "
            f"({type(error).__name__}: {error}): {preview!r}",
        )
    matches = _VERDICT_JSON.findall(result)
    if not matches:
        return (
            Verdict.NEEDS_JUDGMENT,
            f"subagent reply had no verdict JSON: {result.strip()[:200]!r}",
        )
    try:
        verdict_json = json.loads(matches[-1])
        verdict = Verdict(verdict_json["verdict"])
    except (json.JSONDecodeError, KeyError, ValueError) as error:
        return (
            Verdict.NEEDS_JUDGMENT,
            f"could not parse subagent's verdict JSON ({type(error).__name__}: {error}): {matches[-1]!r}",
        )
    if verdict not in (Verdict.SUPPORTED, Verdict.CONTRADICTED, Verdict.UNCLEAR):
        return Verdict.NEEDS_JUDGMENT, f"subagent returned {verdict.value!r}, not a judgment"
    return verdict, str(verdict_json.get("detail", ""))


def http_fetch(client: httpx.Client, robots: RobotsPolicy | None = None) -> Fetcher:
    """The real `Fetcher`: one HTTP GET, HTML reduced to plain text.

    `robots`, when given, is the same `RobotsPolicy` `lpa.scraper.Scraper`
    treats as mandatory before any outbound fetch (issue #1, story 21) — a
    citation whose host disallows fetching comes back FETCH_FAILED with the
    refusal reason, and requests are spaced per host via the policy's
    `RateLimiter`, same as the daily Scraper. It defaults to `None` here
    because this pass, unlike the daily Scraper, is an attended,
    low-volume, authoring-time tool — a human picks a handful of citation
    URLs for one page, not a scheduled crawl of ~20 outlets — so skipping it
    is a defensible default rather than an oversight. `main()` always
    passes one; pass `None` explicitly (or omit it) only for tests or a
    one-off script.
    """

    def fetch(url: str) -> FetchResult:
        if robots is not None:
            if not robots.is_allowed(url):
                return FetchResult(text=None, error=f"disallowed by robots.txt: {robots.refusal_reason(url)}")
            robots.limiter.wait_turn(url, robots.crawl_delay(url))
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            return FetchResult(text=None, error=f"{type(error).__name__}: {error}")
        content_type = response.headers.get("content-type", "")
        text = strip_html(response.text) if "html" in content_type else response.text
        return FetchResult(text=text[:MAX_SOURCE_CHARS], error=None)

    return fetch


def extract_claims(html_text: str) -> list[Claim]:
    """Pull every claim out of a page. Pure — no network.

    A claim is any element carrying a `data-claim` attribute; its text is the
    element's text content (nested tags collapse, so `<strong>` inside a claim
    doesn't split it), and its citation is that same element's `data-cite`
    attribute. An explicit `id` attribute is kept as the claim's id, so a
    verdicts file survives edits elsewhere on the page; without one, ids are
    assigned `claim-1`, `claim-2`, ... in document order.

    This is this project's citation convention going forward for the
    hand-authored pages under #26/#27/#28 — see docs/agents/citation-check.md.
    """
    parser = _ClaimParser()
    parser.feed(html_text)
    parser.close()
    return parser.claims


class _ClaimParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.claims: list[Claim] = []
        self._stack: list[dict] = []
        self._depth = 0
        self._auto_id = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_ELEMENTS:
            return
        self._depth += 1
        attr_dict = dict(attrs)
        if "data-claim" in attr_dict:
            self._auto_id += 1
            claim_id = attr_dict.get("id") or f"claim-{self._auto_id}"
            self._stack.append(
                {
                    "tag": tag,
                    "depth": self._depth,
                    "text": [],
                    "cite": attr_dict.get("data-cite") or None,
                    "id": claim_id,
                }
            )

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_ELEMENTS:
            return
        if (
            self._stack
            and self._stack[-1]["depth"] == self._depth
            and self._stack[-1]["tag"] == tag
        ):
            entry = self._stack.pop()
            text = " ".join("".join(entry["text"]).split())
            self.claims.append(Claim(id=entry["id"], text=text, citation=entry["cite"]))
        self._depth -= 1


def _print_report(results: list[CitationCheckResult]) -> None:
    for result in results:
        preview = result.claim.text if len(result.claim.text) <= 80 else result.claim.text[:77] + "..."
        print(f"[{result.verdict.value}] {result.claim.id}: {preview!r} — {result.detail}")


def _write_pending(pending: list[CitationCheckResult], path: Path) -> None:
    """Write claims still at NEEDS_JUDGMENT after the automated pass.

    Takes the already-filtered list rather than filtering internally — `main`
    is the only caller and needs that same filtered list itself (to decide
    whether to write the file at all, and how many claims to report), so
    filtering once there and passing the result down keeps there being
    exactly one place that decides what "pending" means.
    """
    path.write_text(
        json.dumps(
            [
                {
                    "id": r.claim.id,
                    "claim": r.claim.text,
                    "citation": r.claim.citation,
                    "source_excerpt": r.source or "",
                }
                for r in pending
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", type=Path, help="the HTML page to check")
    parser.add_argument(
        "--verdicts",
        type=Path,
        default=None,
        help=(
            "optional verdicts JSON overriding the automated judge for "
            "specific claim ids (e.g. a human correction) — never required"
        ),
    )
    parser.add_argument(
        "--pending",
        type=Path,
        default=None,
        help="where to write claims the automated judge couldn't resolve (default: <page>.pending.json)",
    )
    parser.add_argument(
        "--judge-model",
        default=DEFAULT_JUDGE_MODEL,
        help="model the automated judge subagent runs as (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    html_text = args.page.read_text(encoding="utf-8")
    judge: Judge = subagent_judge(model=args.judge_model)
    if args.verdicts:
        judge = override_judge(verdicts_from_file(args.verdicts), judge)

    with new_client(USER_AGENT) as client:
        results = check_page(html_text, http_fetch(client, robots=RobotsPolicy(client=client)), judge)

    _print_report(results)

    pending = [r for r in results if r.verdict == Verdict.NEEDS_JUDGMENT]
    if pending:
        pending_path = args.pending or args.page.with_suffix(args.page.suffix + ".pending.json")
        _write_pending(pending, pending_path)
        print(
            f"\n{len(pending)} claim(s) the automated judge could not resolve. Wrote "
            f"{pending_path} — see docs/agents/citation-check.md."
        )

    failing = [r for r in results if not r.passed]
    if failing:
        print(f"\n{len(failing)}/{len(results)} claim(s) flagged.")
        return 1
    print(f"\nAll {len(results)} claim(s) supported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
