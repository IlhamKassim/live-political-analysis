# Citation check

How to run `lpa.citation_check` against a content page under `public/learn/`
(#26/#27/#28) before considering its content done, per #22's "Verification —
settled" section: every factual claim has to trace to its cited source, and
this pass runs with no per-claim human gate — the tool itself spawns a
subagent to judge each claim; no one has to eyeball each pair, or hand-author
an answer, for the run to reach a verdict.

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

This extracts every claim, fetches every citation, immediately flags:

- claims with no citation (`no_citation`)
- citations that failed to fetch (`fetch_failed`)

and judges everything else **automatically** — no separate step, no file to
hand-author. For each claim whose citation fetched, the tool itself spawns a
`claude -p` subagent (`subagent_judge` in `src/lpa/citation_check.py`), gives
it the claim text and the fetched source text directly in the prompt (no
tool access — it can't browse or read files, only judge what it was handed),
and reads back `supported` / `contradicted` / `unclear`. The report prints
immediately and the run exits non-zero if anything is unsupported,
contradicted, uncited, unfetchable, or still unjudged after that — nothing
here passes silently, and a page passes the citation-check step only once
every claim reports `supported`.

A claim the automated judge couldn't resolve — a malformed reply, the
`claude` CLI unavailable, a source that's genuinely ambiguous — is written to
`public/learn/coalitions.html.pending.json` as diagnostic output, not a
required next step:

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

## Overriding a verdict by hand

`--verdicts verdicts.json` is optional, and never required to reach a
verdict on a fetchable claim — it exists for correcting one specific call,
not for supplying judgment the tool doesn't otherwise have:

```
python -m lpa.citation_check public/learn/coalitions.html --verdicts verdicts.json
```

```json
[{"id": "claim-1", "verdict": "unclear", "detail": "the source hedges more than this claim admits"}]
```

An entry here wins over what the automated judge decided for that claim id;
any id the file doesn't mention still goes through the automated judge as
normal — the file only needs to cover the claims someone actually wants to
override.

## Why this shape

- **No per-claim human gate, but not a rubber stamp either.** The mechanical
  half (extraction, fetching, flagging missing/broken citations) is pure
  Python and unit-tested with no network — see `tests/test_citation_check.py`.
  The semantic half is real judgment, so the tool spawns a subagent to do it
  rather than faking it with a keyword match that would pass or fail claims
  for the wrong reasons.
- **Zero recurring cost (ADR 0002).** `subagent_judge` shells out to the
  `claude` CLI — the same subscription-seat tool an interactive session
  already runs under — not the metered Anthropic API ADR 0002 rules out for
  daily/unattended use. It costs nothing beyond the running session's own
  usage: no new API key, no per-page fee. This is different from
  `sentiment.py`'s self-hosted model, which exists because sentiment scoring
  runs daily and unattended in GitHub Actions; this pass runs once per page,
  at authoring time, so there's no unattended-run requirement forcing a
  self-hosted model here too.
- **The subagent runs from a bare working directory, not this checkout.**
  Tried against the project root directly, the subagent auto-discovers
  `CLAUDE.md`, decides the judgment prompt looks like agent work, and starts
  exploring the repo instead of just answering — measured at 19 turns and
  $0.19 for one claim, instead of a few cents. `subagent_judge` runs the CLI
  call with `cwd` set to a temp directory so there's nothing to discover.
