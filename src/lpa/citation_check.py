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

There is deliberately **no built-in `Judge`.** ADR 0002 keeps this project at
zero recurring cost, and "does this claim match this source" needs real
language understanding that a keyword check can't give reliably — the two
options are a paid LLM API (ruled out) or a self-hosted model (which, unlike
sentiment scoring, has no daily-unattended-run requirement forcing that
trade-off: this pass runs once per content page, at authoring time, driven by
a human or an agent session that already has one). So the semantic step is
handed to whatever already-running agent session is authoring the page, via
the CLI's two-step protocol below — no new dependency, paid or otherwise.

CLI protocol (see docs/agents/citation-check.md for the full walkthrough):

    python -m lpa.citation_check PAGE.html

extracts claims, fetches every citation, and immediately flags claims with no
citation or a citation that failed to fetch. Every claim whose source *did*
fetch is written to `PAGE.html.pending.json` — claim text, citation URL, and
the fetched source text — because none of those can be decided without
semantic judgment. A subagent (or the calling agent itself) reads that file,
judges each entry, and writes a verdicts file:

    [{"id": "claim-1", "verdict": "supported", "detail": "..."}, ...]

    python -m lpa.citation_check PAGE.html --verdicts verdicts.json

re-runs the check with those verdicts plugged in as the `Judge`, prints the
final per-claim report, and exits non-zero if anything is unsupported,
contradicted, uncited, unfetchable, or still unjudged — nothing here passes
silently.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Protocol

import httpx

from lpa.scraper import USER_AGENT, strip_html

MAX_SOURCE_CHARS = 8_000
"""A fetched source is truncated to this many characters before it reaches a
Judge or a pending report — long enough to carry real context, short enough
that a subagent reading it costs a bounded amount of context."""

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
    """Fetched successfully but no Judge has decided it yet — the state
    `deferred_judge` returns, and what a claim missing from a verdicts file
    stays at. Counts as a failure precisely so an unjudged claim cannot be
    mistaken for a supported one."""


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


class Fetcher(Protocol):
    def __call__(self, url: str) -> FetchResult: ...


class Judge(Protocol):
    def __call__(self, claim: Claim, source_text: str) -> tuple[Verdict, str]: ...
    """Decide whether `source_text` supports `claim.text`. Must return
    SUPPORTED, CONTRADICTED, or UNCLEAR — the other two Verdict members are
    reserved for `check_page` itself, which never asks a Judge about a claim
    it couldn't fetch a source for in the first place."""


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
    """The default `Judge`: defers every fetched claim rather than guessing.

    No local judgment is attempted here, on purpose — see the module
    docstring. Fetched claims come back NEEDS_JUDGMENT, which `check_page`
    treats as a failure, so a page checked with this Judge and no follow-up
    fails closed rather than reporting green.
    """
    return Verdict.NEEDS_JUDGMENT, "not yet judged — see docs/agents/citation-check.md"


def verdicts_from_file(path: Path) -> Judge:
    """A `Judge` backed by a verdicts file, keyed by claim id.

    This is how a subagent's judgment re-enters the pipeline after reading a
    pending report (see the module docstring's CLI protocol). A claim id
    absent from the file is left NEEDS_JUDGMENT rather than assumed
    supported — a subagent that ran out of claims to judge must not thereby
    pass the ones it never looked at.
    """
    entries = {
        entry["id"]: entry for entry in json.loads(path.read_text(encoding="utf-8"))
    }

    def judge(claim: Claim, source_text: str) -> tuple[Verdict, str]:
        entry = entries.get(claim.id)
        if entry is None:
            return Verdict.NEEDS_JUDGMENT, f"no verdict recorded for {claim.id!r}"
        return Verdict(entry["verdict"]), entry.get("detail", "")

    return judge


def http_fetch(client) -> Fetcher:
    """The real `Fetcher`: one HTTP GET, HTML reduced to plain text.

    `client` is duck-typed to `.get(url) -> response` with `.raise_for_status()`,
    `.text` and `.headers`, the same shape `lpa.scraper` depends on — so tests
    can substitute a stub instead of a live `httpx.Client`, and this never
    needs to construct one itself.
    """

    def fetch(url: str) -> FetchResult:
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


def _write_pending(results: list[CitationCheckResult], path: Path) -> None:
    pending = [r for r in results if r.verdict == Verdict.NEEDS_JUDGMENT]
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
        help="a verdicts JSON file written by a subagent after reading a pending report",
    )
    parser.add_argument(
        "--pending",
        type=Path,
        default=None,
        help="where to write claims needing judgment (default: <page>.pending.json)",
    )
    args = parser.parse_args(argv)

    html_text = args.page.read_text(encoding="utf-8")
    judge: Judge = verdicts_from_file(args.verdicts) if args.verdicts else deferred_judge

    with httpx.Client(
        timeout=15.0, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    ) as client:
        results = check_page(html_text, http_fetch(client), judge)

    _print_report(results)

    pending = [r for r in results if r.verdict == Verdict.NEEDS_JUDGMENT]
    if pending:
        pending_path = args.pending or args.page.with_suffix(args.page.suffix + ".pending.json")
        _write_pending(results, pending_path)
        print(
            f"\n{len(pending)} claim(s) need semantic judgment. Wrote {pending_path} "
            "— see docs/agents/citation-check.md for the subagent step."
        )

    failing = [r for r in results if not r.passed]
    if failing:
        print(f"\n{len(failing)}/{len(results)} claim(s) flagged.")
        return 1
    print(f"\nAll {len(results)} claim(s) supported.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
