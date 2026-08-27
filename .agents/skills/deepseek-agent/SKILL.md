---
name: deepseek-agent
description: >-
  Guides dispatching, task-file authoring, safety constraints, and post-hoc review for
  the autonomous DeepSeek agent loop running in an isolated git worktree.
---

# DeepSeek Agent Loop Workflow

`scripts/deepseek_agent.py` runs an autonomous DeepSeek tool-calling session inside an isolated `git worktree`.

It is intended for **pinned, mechanical code-writing and test authoring** after architecture decisions and specifications have already been settled.

---

## 1. Safety Guardrails & Model Posture

- **Isolated Worktree**: Every run executes in `<repo_root>/.deepseek-agent-runs/<run-id>/worktree`.
- **Restricted Command Allowlist**: Only allows `pytest`, `ruff`, `mypy`, and `python <file>` (`python -c` is blocked; `npm`/`tsc` not available).
- **No Push, No PR, No Merge**: The agent can only create local git commits inside its worktree.
- **Never Trust Self-Reported Success**: Always inspect the real git diff and run logs before accepting changes.

---

## 2. Authoring Effective Task Files

To prevent token exhaustion and loops, follow the structural house style:

1. **State the exact deliverable in paragraph 1**: Name the target file, function signatures, and expected behaviour.
2. **Paste referenced code verbatim**: Do not ask DeepSeek to explore or read 5+ files; paste the exact current implementations into the task file.
3. **Specify the first tool call**: Tell the agent: `"Your first tool call should be edit_file (or write_file), not read_file."`
4. **Mechanical Verification**: Give clear commands to verify (e.g. `.venv/bin/pytest tests/test_my_feature.py`).
5. **Git Verification**: Remind the agent to run `git_status` before calling `finish_task`.

---

## 3. Invoking the Agent Loop

```sh
export DEEPSEEK_API_KEY="your_api_key"
.venv/bin/python scripts/deepseek_agent.py --task-file task.md
```

### Reviewing the Output:
```sh
git log --oneline main..<branch>
git diff main..<branch>
```

---

## 4. References
- Full specification, failure modes, and safety invariants: `docs/agents/deepseek-agent.md`.
