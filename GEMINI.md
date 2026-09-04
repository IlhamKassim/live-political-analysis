# live-political-analysis — Antigravity Workspace Rules

This repository tracks sentiment on the Malaysian political landscape and projects GE16 election outcomes (publicly branded as **PolitikKu** at [politikku.my](https://politikku.my)).

All agent sessions operating in this repository must follow the conventions below.

---

## 1. Domain Vocabulary & Architecture Decisions

This is a **single-context repository**. Before exploring or proposing changes, read:
- **`CONTEXT.md`** at the repository root: Canonical domain glossary (*Coalition*, *Seat*, *Majority*, *Government Coalition*, *Non-government*, *Baseline*, *Sentiment*, *Swing*, *State Election Signal*, *Election Status*, *Swing Model*, *Projection*, *Seat-Level Projection*, *Seat Call*, *Postcode → Seat Index*, *MP Profile*, *Division*, *Bill*, *Audience*, *Return Trigger*).
  - Use exact terms from `CONTEXT.md`. Never invent or drift to avoided synonyms (e.g., avoid "prediction", "forecast", "opposition", "alliance").
  - Every Seat Call is arithmetic against the GE15 Baseline, never a bespoke judgement about that constituency.
- **`docs/adr/`**: Architecture Decision Records.
  - **ADR 0002 / ADR 0006 / ADR 0007**: Zero recurring cost by default, static HTML generation for the public site, no paid external APIs for pipeline runs.
  - **ADR 0003**: Model is provisional and uncalibrated; never frame projections as predictions.
  - **ADR 0008 / 0009 / 0010**: Sourcing rules for postcodes, MP profiles, and parliamentary bill tracking.
- If your work contradicts an ADR or requires a new domain term, flag it explicitly to the user.

---

## 2. Strict Guardrails

1. **No remote push or PRs**: Never run `git push`, open a pull request, or merge anything. Local commits only when explicitly instructed.
2. **No destructive git commands**: Never execute destructive git actions (`reset --hard`, `clean -f`, `checkout --`, force-push, branch deletion) without explicit user instructions.
3. **Zero recurring cost**: Never introduce dependencies or integrations that require paid API calls or persistent hosted compute without explicit user sign-off (ADR 0002 / 0007).
4. **Workspace confinement**: Stay strictly within this repository's working tree.
5. **Verify mechanically**: Always run `.venv/bin/pytest` and linter checks (`ruff check`, `mypy`) before claiming a task is done. Never claim success from narrative alone if tests have not passed.

---

## 3. Model & Effort Policy

Default to the cheapest/fastest capable model (`flash` or `inherit`). Escalate to the strong model (`pro`) **only** when hitting one of the four escalation triggers (`docs/agents/model-effort.md`):

1. **Visual / design judgment**: Typography, layout, UI register, visual mockups.
2. **Editorial judgment on sensitive content**: Content touching Malaysian ethnic/religious lines, coalition politics, or trust-critical framing.
3. **Security- or correctness-critical engineering**: Code where subtle mistakes defeat verification or safety (e.g. citation-check prompts, agent execution sandboxes).
4. **Irreversible or hard-to-reverse decisions**: Complex data schema migrations or destructive actions.

### Effort & Review Depth
- **Medium effort**: Standard implementation, run tests, report results.
- **High effort**: Verify each claim against real sources/data before reporting done (e.g. cross-referencing mockups against real datasets).
- **Review depth**: If a diff's correctness is fully verifiable by `pytest`/`ruff`/`mypy`, keep reviews light. If a diff touches trust rules, copy, or uncalibrated tags, perform thorough semantic checks.
- **Strong Model Consultation**: The orchestrator can dynamically spawn a `pro` subagent via `invoke_subagent(Model='pro', ...)` for focused consultation whenever hitting escalation triggers or complex architectural decisions.

---

## 4. Issue Tracking & Workflow

Issues live on GitHub (`IlhamKassim/live-political-analysis`) managed via the `gh` CLI (`docs/agents/issue-tracker.md`):
- Read an issue: `gh issue view <number> --comments`
- Comment on an issue: `gh issue comment <number> --body "..."`
- Manage labels: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- Canonical triage labels (`docs/agents/triage-labels.md`): `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`.
- PRs are not a request surface — track work through issues only.

---

## 5. Specialized Workflows & Skills

- **Civic Education Content**: Any page under `public/learn/` must be verified using `python -m lpa.citation_check public/learn/<page>.html` before it counts as done (`.agents/skills/citation-check/SKILL.md`).
- **Mechanical Task Delegation**: Spec-pinned, mechanical code-writing and test boilerplate can be delegated to `scripts/deepseek_agent.py` in an isolated git worktree (`.agents/skills/deepseek-agent/SKILL.md`).
- **Session & Context Monitoring**: Inspect active token context and session metrics anytime via `python scripts/session_status.py` (`.agents/skills/session-status/SKILL.md`).
- **UI/UX Improvement Work**: `mypolitik`'s frontend design system
  (`docs/design/mypolitik-new-views-spec.md`) is the surviving visual
  direction — see ADR 0012. `docs/design/ui-ux-brief.md` is retired.
