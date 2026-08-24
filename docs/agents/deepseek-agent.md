# DeepSeek agent loop

An autonomous DeepSeek-driven coding session, in an isolated `git worktree`,
for the workflow: a person describes a goal to Claude in conversation,
Claude turns it into a concrete task and dispatches `scripts/deepseek_agent.py`,
DeepSeek's chat-completions API works through it with real tool access, and
a human or Claude reviews the full result afterward. It is not a substitute
for Claude doing work directly — DeepSeek has shown real reasoning quirks at
straightforward tasks in this same repo (the citation-check DeepSeek-vs-Claude
comparison found it conflating a source's current data snapshot with the
general state its comments document, and over-literal "contradicted" verdicts
on differences that were only in precision, not fact). This tool is designed
around not trusting that judgment blindly.

## What it is and isn't

- **Bounded autonomous run, then full review.** DeepSeek works through the
  whole task alone, capped at a turn limit and a wall-clock limit, inside its
  own worktree. It stops — self-reported done, capped, or errored — and a
  human/Claude reviews the complete diff and transcript before anything from
  it is trusted. There is no per-step approval gate during the run.
- **No push, no PR, no merge.** The tool set below gives DeepSeek files +
  shell (a fixed allowlist) + *local* git only. Nothing in this script can
  reach the real remote or `main` directly — decision enforced by absence,
  not a runtime check, since no push/PR/merge tool exists in the schema at
  all.
- **Dispatched by Claude, not run ad hoc.** The intended workflow: a person
  talks to Claude, Claude writes a task spec to a file and runs this script
  (via its own shell access), then reports the reviewed result back. Nothing
  stops a person from running the CLI directly, but that isn't the workflow
  this was built for.

## Safety model

| tool | can | cannot / how enforced in code |
|---|---|---|
| `list_dir` | list one directory's immediate entries | path-jailed via `resolve_in_worktree`; non-recursive |
| `read_file` | read a text file, paginated by line | path-jailed; binary files rejected; fenced as untrusted content |
| `grep` | search via `git grep` | path-jailed; `shell=False` argv, no shell metacharacter surface |
| `write_file` | create/overwrite a file | path-jailed; cannot write outside the worktree by construction |
| `edit_file` | exact-match string replace | path-jailed; 0 or >1 matches rejected rather than guessing |
| `run_command` | run `pytest`, `ruff`, `mypy`, or `python` | fixed **allowlist**, not a denylist over a shell string; `shell=False`; `python -c` banned outright |
| `git_status` / `git_diff` | read-only worktree inspection | — |
| `git_add` | stage jailed paths | flag-injection-shaped paths (`--force`) rejected |
| `git_commit` | commit staged changes | fixed `user.name="DeepSeek Agent"` identity; never `--no-verify` |
| `finish_task` | the model's only way to end the run | schema-validated `status ∈ {success, blocked, failed}` |

**Why an allowlist, not a denylist.** A denylist has to anticipate every
bypass — block `rm`, get `python -c "shutil.rmtree(...)"`; block `curl`, get
`python -c "urllib.request..."`. Given DeepSeek's demonstrated reasoning
quirks in this repo, relying on having anticipated every bypass is the
opposite of the fail-closed posture the rest of this codebase already uses
(see `citation_check.py`'s `deepseek_judge`/`subagent_judge`). An allowlist
just has to check membership. Every `run_command` call uses `shell=False`
with an argv list, so shell metacharacters embedded in an argument are inert
literal text, not shell syntax.

**Path jail.** `resolve_in_worktree` is the one enforcement point every
file-touching tool routes through: a model-supplied path is resolved and
checked with `is_relative_to(worktree)` before any I/O. An absolute path, a
`../` traversal, or a symlink planted inside the worktree pointing elsewhere
are all caught the same way.

**Untrusted-content fencing.** File reads, grep matches, and command
stdout/stderr are wrapped in a per-call nonce-fenced block (`fence_untrusted`,
mirroring `citation_check.py`'s `_judge_prompt` pattern) before they reach
the model — a file or a test's printed output could in principle carry
adversarial text aimed at the loop, so this is designed in from the start.

**What this is NOT — read this before trusting a run.** `run_command`'s
allowlist is not a full OS sandbox. Once an allowlisted `pytest`/`python`
invocation is running, there is no network-egress control and no filesystem
confinement beyond the worktree the interpreter starts in —
`subprocess.run(cwd=...)` only sets the *starting* directory. The concrete
mitigations taken: `DEEPSEEK_API_KEY` (and any `ANTHROPIC_`/`OPENAI_`-prefixed
variable) is stripped from `run_command`'s subprocess environment, so an
arbitrary allowed invocation can't trivially read it back out; `python -c`
is banned as the single highest-leverage arbitrary-code vector. Neither is a
fix, both are mitigations — container/VM/`sandbox-exec` confinement is a
named follow-up, not solved here.

**`finish_task`'s `summary`/`status` is the model's own unverified claim.**
The CLI's final JSON computes `files_changed`/`commits` from real
`git diff --stat`/`git log`, not from what the model says it did — the diff
and transcript are the actual signal, always worth checking even when
`finish_task` reported `success`.

## Invocation

```
python scripts/deepseek_agent.py --task-file TASK.md
    [--repo-root PATH] [--base-ref REF] [--branch-name NAME] [--work-dir PATH]
    [--max-turns 40] [--max-wall-clock-seconds 1800]
    [--turn-timeout 120.0] [--command-timeout 120.0]
    [--model deepseek-chat] [--api-key KEY]
    [--keep-worktree / --no-keep-worktree]
```

Only `--task-file` is required — a file, not an inline string, since a real
task from a conversation is multi-paragraph. `DEEPSEEK_API_KEY` (or
`--api-key`) is checked before any worktree or network call; a missing key
fails closed immediately, same ordering `citation_check.py`'s `deepseek_judge`
already uses.

A run creates `<repo_root>/.deepseek-agent-runs/<run-id>/worktree` (a linked
`git worktree`, kept by default — `--no-keep-worktree` to auto-remove) and
prints one final JSON object to stdout:

```json
{
  "status": "finished",
  "turns_used": 4,
  "wall_clock_seconds": 4.9,
  "worktree": "...worktree",
  "branch": "deepseek-agent/20260813T041704Z-623452",
  "transcript_path": "...transcript.json",
  "self_reported_summary": "...",
  "files_changed": "greeting.py | 6 ++++++\n 1 file changed, 6 insertions(+)",
  "commits": ["fecbeae Add greeting module with greet function"]
}
```

Exit code 0 only for `status: "finished"`; 2 for `setup_failed` (nothing ran
at all); 1 for every other terminal state (`turn_cap_reached`,
`wall_clock_exceeded`, `stalled`, `api_error`, `finished_blocked`,
`finished_failed`) — branch on this directly rather than parsing prose.

**To review a run**, from the real repo checkout:

```
git -C <repo_root> log --oneline <base-ref>..<branch>
git -C <repo_root> diff <base-ref>..<branch>
```

Both work with no fetch step, since the worktree shares the main checkout's
`.git`. `docs/agents/deepseek-agent-demo-transcript.json` is a captured real
run, produced with the task in this doc's worked example.

## ADR 0002 cross-reference

This reaches DeepSeek's metered API directly, exactly like the experimental
`deepseek_judge` judge backend in `lpa.citation_check` (branch
`experiment/deepseek-judge`) — not the free subscription-seat CLI call ADR
0002 relies on elsewhere. It is deliberately attended/manual only. **Do not
wire this into `.github/workflows/daily.yml` or any other scheduled path**
without first revisiting that ADR's zero-recurring-cost constraint.

## model-effort.md cross-reference

Building or modifying this tool is a clean instance of `model-effort.md`'s
trigger #3 (security/correctness-critical engineering) — it grants a model
shell, file, and local-git access. A mandatory `/code-review` pass is
required before it's trusted for a real task; that pass runs on the strong
model *because* it's reviewing correctness-critical work (trigger 3 applies
to the review itself, same as it applies to building the tool — "code
review" was removed as its own automatic-Opus trigger, see `model-effort.md`'s
2026-08-24 amendment), not because every review is Opus by default. Same
reasoning `model-effort.md` cites as precedent either way: `citation_check.py`
shipped a real prompt-injection gap on its first pass that only a later
review caught.

## Known operational gotchas

- **A stray git repo at `/Users/hamboii/.git`** (an unrelated `money-saver`
  project) has repeatedly mis-provisioned Claude Code's own `Agent` tool
  `isolation: "worktree"` dispatches by auto-detecting a repo root
  ambiguously from `cwd`. This script never does path discovery from `cwd`
  at all — `resolve_repo_root` derives `repo_root` from its own `__file__`
  location and sanity-checks `pyproject.toml`'s `name` before doing anything
  else — so that specific failure mode doesn't transfer here. Still worth
  knowing about if a run ever looks like it touched the wrong repo.
- **A run genuinely blocks in the foreground.** Unlike some past agent
  dispatches in this project that claimed to be "waiting" without actually
  blocking, `main()` runs the loop synchronously and streams progress to
  stderr as it goes — a silent terminal for a while is not itself a sign of
  a hang, but a long real-world gap (the machine sleeping, etc.) can still
  make a run look stuck; check wall-clock time before assuming something's
  wrong.
- **Concurrent runs** against the same `repo_root` each get their own
  worktree/branch by run-id, but simultaneous `git worktree add`/`remove`
  against the same `.git` has known races in some git versions. Low risk for
  single-operator use; avoid deliberately running two at once against the
  same repo.

## Cleanup

Run directories live at `<repo_root>/.deepseek-agent-runs/<run-id>/` and are
kept by default — the whole point is post-hoc review, so nothing auto-deletes
unless `--no-keep-worktree` was passed. To clean up a reviewed (or abandoned)
run:

```
git -C <repo_root> worktree remove <path>
git -C <repo_root> branch -D deepseek-agent/<run-id>   # only if abandoning the branch
rm -rf <repo_root>/.deepseek-agent-runs/<run-id>
```

## Why this repo breaks its own "scripts/ has no tests" pattern here

Nothing else under `scripts/` has test coverage — `preview_public_page.py`
and `seed_dev_snapshots.py` have a blast radius bounded by "your own browser"
or "your own local dev database." This tool executes shell commands and git
commits chosen by a third-party model with real commit authority, which is
exactly the class of risk `model-effort.md`'s trigger #3 names. Breaking the
pattern here is deliberate, not a precedent for every future `scripts/`
addition to follow.
