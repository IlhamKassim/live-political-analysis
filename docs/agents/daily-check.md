# Daily check: attended, diff-scoped bug hunt

An attended, two-worker bug hunt over the diff since the last run, dispatched
to Antigravity workers the user runs by hand, verified independently by
Claude, and filed to the issue tracker. Operational steps live in
`.agents/skills/daily-check/SKILL.md`; this doc is the rationale, tradeoffs,
and known limitations behind them.

## What it is and isn't

- **Attended, not scheduled.** A person dispatches both Antigravity workers
  by hand, every time. Nothing here is wired into `.github/workflows/`.
  This mirrors the discipline `docs/agents/deepseek-agent.md` states for the
  DeepSeek loop and ADR 0002's zero-recurring-cost constraint — promoting a
  recurring agent job from "something I run" to "something that runs itself"
  is a deliberate future decision, never a default, even though this uses a
  different provider (Gemini via Antigravity) than the DeepSeek loop that
  rule was originally written for.
- **Diff-scoped, not a codebase re-scan** (after the first run). `ci.yml`
  already owns lint, types, tests, and secrets on every push to `main`.
  `/code-review` already owns diff review against a spec/originating issue.
  This fills the gap between them: a diff review with no single originating
  issue to anchor against, run on a cadence the user controls rather than
  per-PR — this repo pushes straight to `main`, so there is no PR gate to
  hook a review into.
- **Two independent passes, never merged.** Standards and Correctness are
  reported and filed separately, the same reason `/code-review` never
  reranks Spec against Standards: a change can pass one axis and fail the
  other, and merging them lets one mask the other.
- **Antigravity finds and fixes, Claude verifies and files.** Every
  candidate finding is re-checked against the real code before it reaches
  the issue tracker, and every claimed fix or push-back in the address pass
  is re-checked the same way before Claude closes, relabels, or escalates
  an issue — see "Verification" and "Address pass" below for why
  self-verification wasn't trusted at either stage.

## The checkpoint: `last-bug-review`

A git tag, advanced to the reviewed commit and pushed after every run. A
normal run's diff is `git diff last-bug-review..main`.

**First run only**: the tag doesn't exist yet. `git rev-parse
last-bug-review` failing is the signal to run both workers over the whole
codebase instead of a diff — a deliberate one-time baseline audit, not the
steady-state mode. Every run after that is a true incremental diff. A
missing tag on any run after the first means the tag wasn't advanced last
time (a bug to fix), not an invitation to silently re-sweep the whole
codebase again.

## Model choice

Both workers run on Gemini 3.8 Flash, high effort — a fixed choice, no
per-diff escalation. Worth naming explicitly: `docs/agents/model-effort.md`'s
four escalation triggers (visual/design judgment, editorial judgment on
sensitive content, security/correctness-critical engineering, an
irreversible/hard-to-reverse decision) don't apply here the way they do to a
Claude dispatch — a diff that squarely matches trigger 3 (e.g. a change to
`scripts/deepseek_agent.py`) gets the same fixed Flash-tier pass as a
formatting-only diff. That's an accepted, explicitly-chosen tradeoff, not an
oversight, made when this workflow was designed.

Antigravity has no access to this harness's skills (`/code-review` included)
— every worker prompt in `SKILL.md` is written fully self-contained, pasting
the smell baseline and the brief rather than naming a skill. Antigravity
workers do have real repo/filesystem access, the same as this project's
existing feature-dispatch workers, so they read `CONTEXT.md`, `docs/adr/*`,
and `CLAUDE.md` directly rather than needing those pasted in too.

## Verification (Claude's role)

Every candidate finding from both workers gets independently re-checked
before it reaches the issue tracker — trace the concrete failure scenario
(what input/state, what wrong output) against the actual code, don't just
restate the worker's claim. What happens next depends on whether that
re-check actually settles it:

- **Confirmed by reading alone** → `CONFIRMED`, no need to involve the user.
- **Can't be fully confirmed** → not a soft "maybe" tag to carry forward.
  Claude asks the user directly, right then, with the finding and what
  could and couldn't be verified about it, and the user decides on the spot
  whether it gets filed anyway or dropped. An earlier version of this
  design used a `PLAUSIBLE` tag instead — bundling anything unconfirmed
  into one note in the final report rather than deciding it. That just
  moved the ambiguity to the end of the run instead of resolving it, so it
  was replaced with the same live-ask pattern the address pass already
  uses (see "Address pass" below) — one mechanism for unresolved ambiguity,
  used wherever it comes up, rather than two.

This mirrors `lpa.citation_check`'s own design: it spawns a separate
subagent to judge each claim rather than trusting the pass that produced it,
specifically because a model re-reading its own reasoning tends to confirm
itself rather than stress-test it. Cross-model verification (Claude checking
Gemini's claims) is stronger against that failure mode than same-model
self-check would be — the reason Claude verifies here rather than a third
Antigravity worker.

## Filing

A GitHub issue, labeled `needs-triage`, gets filed for every finding that's
either `CONFIRMED` or that the user chose to file despite unresolved
ambiguity — one issue per finding, quoting the concrete failure scenario and
which pass found it. Anything the user chose to drop instead isn't filed at
all; it's noted in the final report so it isn't forgotten, but needs no
further action.

## Address pass

Filing an issue isn't the end of the run. The same two workers that found
the `CONFIRMED` issues get a second prompt, scoped to only the issues their
own pass produced, telling them to either fix and close each one or push
back with a reason and leave it open. Claude then verifies that pass too —
same discipline as verifying the original findings, not a rubber stamp on
either worker's self-report:

- A claimed fix that genuinely resolves the recorded failure scenario gets
  closed — a plain check, no judgement call.
- A push-back whose reasoning clearly holds up gets closed as `wontfix`
  directly — also plain, not a judgement call.
- **Anything else is put to the user live, in the same session, rather than
  auto-labelled and parked.** A fix that doesn't actually check out, a
  push-back that doesn't clearly settle the question, or an issue nobody
  touched — Claude asks directly, with the concrete situation (what was
  claimed, what checking it found), and acts immediately on whatever the
  user decides: another fix attempt, accepting the push-back anyway, or
  something else entirely. This replaced an earlier version of the design
  that auto-relabelled an unresolved judgement call to `ready-for-human` and
  moved on — that left genuine decisions sitting async in the tracker for
  the user to notice and get to later, which is exactly the kind of silent
  gap this skill exists to close for actual bugs; there's no reason to
  reintroduce the same gap one level up, in the review process itself.

**The checkpoint tag advances once every issue from this run has an actual
decision behind it** — closed, or explicitly left open because the user
chose to hold onto it themselves after being asked directly. In the normal
case that means every run ends with the tag advanced and nothing open;
`ready-for-human` still exists as a label, but now only for a case the user
deliberately chose to defer, not a default outcome the pipeline reaches on
its own.

The report back to the user names what got filed (including anything filed
only because they chose to despite ambiguity), anything dropped during
verification, what happened to each filed issue in the address pass, and
whether the checkpoint actually advanced — it does not repeat `CONFIRMED`
findings' full detail, since the issue (open or closed) is the actual
record.

## Known limitations

- **Gemini Flash, fixed tier, no escalation.** A security/correctness-
  critical diff gets no stronger a pass than a trivial one — see "Model
  choice" above.
- **The first-run full sweep is a real one-time cost.** Both workers
  reviewing the whole codebase at once is slower and noisier than any later
  diff-scoped run. Budget for that once; it is not the steady state.
- **Antigravity has no skill access.** Every worker prompt in `SKILL.md`
  must stay self-contained. If `/code-review`'s smell baseline ever changes,
  this doc's/`SKILL.md`'s copy of it needs updating by hand — there is no
  single source of truth shared between them.
- **Verification is a reading pass, not a mechanical check.** Unlike
  `ci.yml`'s tests or `deepseek_agent.py`'s `git diff --stat`, there is no
  automated ground truth for "is this really a bug" — `CONFIRMED` means
  Claude traced and believes the failure scenario, not that it was proven by
  a runnable reproduction.
- **"Dead code" needs checking against dev tooling, not just the shipped
  pipeline.** The first real run's dead-code finding (`public_page.py`'s
  render functions) was confirmed against `daily.yml`'s own comments, which
  was true but incomplete — `scripts/preview_public_page.py` turned out to
  still import and call the same functions directly. The address pass's
  push-back caught this, not the original verification. Checking
  `daily.yml`/CI is necessary but not sufficient for "unused"; grep for
  other callers across `scripts/` too before confirming a dead-code finding.
- **`ruff check` and `ruff format --check` are two separate CI steps —
  verifying only one is not verifying CI.** The first real run's address
  pass shipped two commits (#153's rename, #168's fix) that passed `ruff
  check`, `mypy`, and `pytest` — the only three checks anyone ran, worker
  and Claude alike — and broke CI anyway, because `ci.yml` also runs `ruff
  format --check .` as its own step, which nobody ran. Real CI failure, a
  live push notification, caught by the user rather than this skill.
  `SKILL.md`'s address-pass prompt and step 7 now both name `ruff format
  --check` explicitly rather than leaving "ruff" ambiguous between the two.
- **Antigravity workers can't push — Claude does, after independently
  verifying.** `AGENTS.md`'s rule 3 ("Never push... local commits only when
  requested") predates this skill and applies to every Antigravity dispatch
  in this repo, address-pass fixes included. `SKILL.md`'s worker prompt
  says commit-only for this reason; pushing a verified commit is Claude's
  job in step 7, same trust boundary as verifying the fix itself.
- **Two workers editing the same shared working directory at once can
  produce transient, unrelated test failures.** The first real run's
  address pass had both workers fixing issues concurrently in the same
  checkout (not separate worktrees); one worker's in-progress, uncommitted
  edit briefly broke tests the other worker's already-committed fix had
  nothing to do with. Re-running the full suite after both workers finish
  (not mid-flight) is what actually resolved this, not a real regression —
  but a false alarm here is a real risk of this design, worth knowing before
  concluding a failure means a fix is broken.
- **The checkpoint tag advances to the current HEAD after the address
  pass, not the commit recorded at the start of the run.** The address pass
  adds real commits (fixes, and anything resolving a step-7 live question
  directly) on top of that starting point, and all of them get personally
  verified before the tag moves — advancing to the stale, pre-address-pass
  SHA would hand the next run's workers commits already scrutinized this
  session as if they were unreviewed. `SKILL.md` step 8 was corrected to
  this after the first real run advanced the tag to the wrong commit.
