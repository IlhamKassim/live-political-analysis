---
name: model-effort
description: >-
  Rules and criteria for model selection (flash vs pro), prompt effort calibration,
  and code review depth across repository tasks.
---

# Model Selection & Effort Policy

This repository operates on a **cheap by default, escalate on trigger** policy.

---

## 1. Model Selection Tiers

- **Default Model (`flash` or `inherit`)**: Used for routine tooling, mechanical translation of settled specs, integration wiring, unit test boilerplate, and data parsing.
- **Strong Model (`pro`)**: Escalate **only** if the task meets at least one of the 4 triggers below.

---

## 2. The Four Escalation Triggers

1. **Visual / Design Judgment**:
   - Typography, component layout, color registers, or aesthetic choices.
2. **Editorial Judgment on Sensitive Content**:
   - Copy or framing touching Malaysian ethnic/religious lines, coalition politics, or historical sensitivities.
3. **Security- or Correctness-Critical Engineering**:
   - Code where subtle flaws break the core verification or security purpose (e.g., prompt injection defenses in `citation_check.py`, command jailing in `deepseek_agent.py`).
4. **Irreversible or Hard-to-Reverse Decisions**:
   - Destructive operations, difficult schema migrations, or fundamental architectural shifts.

---

## 3. Calibrating "Effort"

"Effort" represents the verification depth specified in agent prompts:
- **Medium Effort**: Standard implementation, execute test suite, report findings.
- **High Effort**: Independent cross-verification required (e.g. cross-referencing mockups against real datasets, checking raw Hansard extracts).

---

## 4. Subagent Escalation & Strong Model Consultation

Under the Manager & Subagent Swarm workflow:
- The orchestrator can dynamically consult a stronger model by invoking a `pro` subagent (`invoke_subagent(Model='pro', ...)`).
- **When to Consult `pro`**:
  1. Any of the 4 escalation triggers are met during a task.
  2. Architectural review of complex refactors before committing changes.
  3. Validating security/safety constraints on unverified code.
  4. Resolving complex edge cases or ambiguous specifications.
- The `pro` subagent executes the focused high-judgment slice, reports its analysis/diff back to the orchestrator, and exits, keeping total context and token consumption optimal.

---

## 5. Review Depth

- **Testable / Mechanical Changes**: Single light pass if `ruff`, `mypy`, and `pytest` fully verify the behavior.
- **Unchecked Semantic / Trust Changes**: Multi-axis review focusing on domain rule compliance and edge cases.

---

## 5. References
- Full decision record and worked examples: `docs/agents/model-effort.md`.
