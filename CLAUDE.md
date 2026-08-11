## Agent skills

### Issue tracker

Issues live on GitHub (`IlhamKassim/live-political-analysis`), managed via the `gh` CLI. External PRs are not treated as a request surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Default label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Citation check

Every civic-education content page (#22's children) runs `lpa.citation_check`
before its content counts as done — fetches each cited source and checks the
page's claims against it, with the semantic half handed to a subagent rather
than a human per-claim gate. See `docs/agents/citation-check.md`.
