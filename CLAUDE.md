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
page's claims against it, spawning a subagent itself to judge each one rather
than requiring a human per-claim gate. See `docs/agents/citation-check.md`.

### Model and effort policy

Cheap model by default (Sonnet), escalate to the strong model (Opus) only on
one of five triggers: visual/design judgment, editorial judgment on sensitive
content, code review, security/correctness-critical engineering, or an
irreversible/hard-to-reverse decision. `to-tickets` runs in this repo state a
model/effort line per ticket; any agent dispatch here should too. See
`docs/agents/model-effort.md`.
