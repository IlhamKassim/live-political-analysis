---
name: issue-tracker
description: >-
  Standard procedures for interacting with GitHub issues, managing triage labels,
  tracking sub-issues, and handling wayfinding maps via the gh CLI.
---

# Issue Tracker Workflow (`gh` CLI)

All issues, PRDs, and task tracking for `IlhamKassim/live-political-analysis` live on GitHub Issues and are operated via the `gh` CLI.

Pull requests are **not** an intake surface; work is tracked exclusively via issues.

---

## 1. Canonical Commands

- **View an issue with comments**:
  ```sh
  gh issue view <number> --comments
  ```
- **Create an issue**:
  ```sh
  gh issue create --title "Title" --body "Detailed description..."
  ```
- **Comment on an issue**:
  ```sh
  gh issue comment <number> --body "Status update..."
  ```
- **Apply or remove labels**:
  ```sh
  gh issue edit <number> --add-label "ready-for-agent"
  gh issue edit <number> --remove-label "needs-triage"
  ```
- **Close an issue with context**:
  ```sh
  gh issue close <number> --comment "Resolved in commit abc1234"
  ```

---

## 2. Canonical Triage Labels

| Label | Meaning |
| :--- | :--- |
| `needs-triage` | Maintainer needs to evaluate or scope this issue |
| `needs-info` | Waiting on reporter or external feedback |
| `ready-for-agent` | Fully specified task, ready for an autonomous agent run |
| `ready-for-human` | Requires human implementation or visual/editorial sign-off |
| `wontfix` | Will not be actioned |

---

## 3. Wayfinding & Dependency Tracking

For multi-step initiatives:
- **Map Issue**: Labelled `wayfinder:map` (holds decisions, architecture context, and sub-issues).
- **Blocking Dependencies**: Added via GitHub native dependencies:
  ```sh
  gh api --method POST repos/IlhamKassim/live-political-analysis/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>
  ```
- **Frontier Query**: Find open child issues with no open blockers and no assignee.

---

## 4. References
- Detailed guides: `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.
