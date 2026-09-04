# live-political-analysis — Antigravity & Agent Guidelines

See [GEMINI.md](file:///Users/hamboii/code/live-political-analysis/GEMINI.md) for full workspace rules, domain vocabulary from [CONTEXT.md](file:///Users/hamboii/code/live-political-analysis/CONTEXT.md), architecture decisions from [docs/adr/](file:///Users/hamboii/code/live-political-analysis/docs/adr/), and guardrails.

### Quick Reference
1. **Domain Terms**: Use terms from `CONTEXT.md` exactly. Avoid synonyms (e.g. use "Seat", "Majority", "Government Coalition", "Projection", "Seat Call").
2. **Zero Cost**: Keep all runtime operations zero recurring cost (ADR 0002/0007).
3. **Safety**: Never push, open PRs, or perform destructive git actions. Local commits only when requested.
4. **Verification**: Verify all changes with `.venv/bin/pytest` before claiming completion.
5. **Model Tiering**: Cheap model (`flash`/`inherit`) by default; escalate to `pro` only for visual design, sensitive political editorial judgment, security/correctness-critical engineering, or irreversible operations (`docs/agents/model-effort.md`).
6. **Context Bar**: Conclude every response with the standardized context and quota status bar footer (`[Context: ... | <Model>] [Quota Remaining: ...]`).
