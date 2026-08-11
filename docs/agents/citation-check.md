# Citation check

How to run `lpa.citation_check` against a content page under `public/learn/`
(#26/#27/#28) before considering its content done, per #22's "Verification —
settled" section: every factual claim has to trace to its cited source, and
this pass runs with no per-claim human gate — an agent decides, not a human
eyeballing each pair.

## The citation convention

Mark a claim by wrapping it in any element with a `data-claim` attribute and a
`data-cite` attribute pointing at its source:

```html
<p data-claim data-cite="https://example.com/source-page">
  GPS was formed in 2018 after four Sarawak-based parties left Barisan
  Nasional.
</p>
```

- Every fact a page states needs its own `data-claim` element — don't bundle
  two claims into one block, since the check is per-element.
- Omit `data-cite` (or leave it empty) for a claim with no source; the check
  flags it rather than skipping it.
- Add an explicit `id` on the element (`<p data-claim id="gps-founding" ...>`)
  for a claim you expect to revisit — otherwise ids are assigned `claim-1`,
  `claim-2`, ... in document order, which shifts if claims are reordered.

## Running it

```
python -m lpa.citation_check public/learn/coalitions.html
```

This extracts every claim, fetches every citation, and immediately flags:

- claims with no citation (`no_citation`)
- citations that failed to fetch (`fetch_failed`)

Everything else fetched successfully but still needs semantic judgment —
"does this source actually say what the claim says" is not something the tool
decides on its own (see the module docstring in `src/lpa/citation_check.py`
for why: no paid API, and no local model is worth adding for something that
runs once per page at authoring time rather than daily and unattended). Those
claims are written to `public/learn/coalitions.html.pending.json`:

```json
[
  {
    "id": "claim-1",
    "claim": "GPS was formed in 2018 after four Sarawak-based parties left Barisan Nasional.",
    "citation": "https://example.com/source-page",
    "source_excerpt": "... the fetched page's text, truncated ..."
  }
]
```

## The subagent step

Whichever agent session is authoring the page already has the Agent/Task tool
available — that is the "already-available agent/subagent call" this pass
uses instead of a new API dependency. Spawn a subagent (or, if you're a human
running this by hand, do the same reading yourself) with a prompt like:

> Read `public/learn/coalitions.html.pending.json`. For each entry, decide
> whether `source_excerpt` actually supports `claim` — not just that it's
> on-topic, but that it says the specific fact the claim states. Write your
> answer as a JSON array to `verdicts.json`:
> `[{"id": ..., "verdict": "supported" | "contradicted" | "unclear", "detail": "one line, why"}]`.
> Use `contradicted` when the source states something different from the
> claim, `unclear` when the source doesn't clearly settle it either way — do
> not default to `supported` when in doubt.

Then re-run the check with the verdicts plugged in:

```
python -m lpa.citation_check public/learn/coalitions.html --verdicts verdicts.json
```

This prints a final per-claim report and exits non-zero if anything is
unsupported, contradicted, uncited, unfetchable, or still unjudged (a claim
id absent from `verdicts.json` stays `needs_judgment` — a subagent that ran
out of claims to judge must not thereby pass the ones it never looked at). A
page passes the citation-check step only once every claim reports
`supported`.

## Why this shape

- **No per-claim human gate, but not a rubber stamp either.** The mechanical
  half (extraction, fetching, flagging missing/broken citations) is pure
  Python and unit-tested with no network — see `tests/test_citation_check.py`.
  The semantic half is real judgment, so it's handed to an agent rather than
  faked with a keyword match that would pass or fail claims for the wrong
  reasons.
- **Zero recurring cost (ADR 0002).** The subagent call costs nothing beyond
  the already-running session's own usage — no new API key, no per-page fee.
  This is different from `sentiment.py`'s self-hosted model, which exists
  because sentiment scoring runs daily and unattended in GitHub Actions; this
  pass runs once per page, by hand or by an attended agent session, so there
  is no unattended-run requirement forcing a self-hosted model here too.
