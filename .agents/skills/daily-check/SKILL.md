---
name: daily-check
description: >-
  Attended, diff-scoped bug hunt: hand the user two self-contained prompts
  for their Antigravity workers (Standards pass + Correctness pass),
  independently verify what they find — asking the user live on the spot
  whenever something's ambiguous rather than deferring it — and file
  confirmed findings as GitHub issues labeled needs-triage.
---

# Daily check

Run this only when the user explicitly invokes it — attended, never
scheduled. See `docs/agents/daily-check.md` for why, and for the tradeoffs
behind every fixed choice below (model tier, tag mechanism, verification
role).

## Language

Every piece of communication this skill produces — both worker prompts, the
address-pass prompt, issue titles/bodies, and the final report to the user —
uses `CONTEXT.md`'s Language section vocabulary (Seat, Coalition, Majority,
Government Coalition, Non-government, Baseline, Sentiment, Swing,
Projection, Seat-Level Projection, Seat Call, MP Profile, Bill, Division,
Audience, Engaged Reader, Return Trigger, etc.) and avoids every synonym its
entries list as _Avoid_ (e.g. never "constituency"/"district" for Seat,
never "party"/"alliance"/"bloc" for Coalition, never "win" for Majority,
never "prediction"/"forecast" for Seat Call, never "Opposition" as a
catch-all for Non-government). This applies whenever a finding, fix, or
report touches a domain concept — it doesn't apply to findings that are
purely mechanical (a lint rule, an unrelated utility function) and have
nothing to do with the domain at all.

## Process

### 1. Determine the mode

Run `git rev-parse last-bug-review`.

- **Fails** → first run. Use the "whole codebase" variant of both prompts
  below.
- **Succeeds** → normal run. Run `git diff last-bug-review..main --stat`
  and `git log last-bug-review..main --oneline` first. If the diff is
  empty, tell the user there's nothing new to review and stop — don't
  dispatch workers for an empty diff. Otherwise use the "diff" variant of
  both prompts, filled in with `last-bug-review`'s SHA and current `main`'s
  SHA.

Record the current `main` HEAD SHA now, before handing off to the workers —
step 5 advances the tag to this exact commit, not to whatever HEAD is by the
time you get back to it.

### 2. Hand the user both worker prompts

Print both prompts below, filled in for this run (mode from step 1, real
SHAs where the diff variant needs them), for the user to paste into their
two Antigravity workers (Gemini 3.8 Flash, high effort — their fixed
choice, no escalation). Both prompts are fully self-contained — Antigravity
has no access to this harness's skills, so neither prompt names
`/code-review` or any other skill by name.

**Worker A — Standards pass:**

```
You are reviewing [the whole codebase / the diff between commit
<last-bug-review-sha> and <main-sha>] of the live-political-analysis repo.

Read CONTEXT.md, CLAUDE.md, and docs/adr/*.md first — those are this repo's
documented standards.

Check what you're reviewing against those documented standards, plus this
fixed baseline of code smells (Fowler, "Refactoring" ch.3). Each smell is a
judgement call, never a hard violation, and a documented repo standard
always overrides a smell it would otherwise flag. Skip anything already
enforced by tooling — check pyproject.toml's ruff/mypy config and
ts/package.json's lint/typecheck scripts if unsure what's already covered:

- Mysterious Name — a function, variable, or type whose name doesn't reveal
  what it does or holds.
- Duplicated Code — the same logic shape appears in more than one place.
- Feature Envy — a method that reaches into another object's data more than
  its own.
- Data Clumps — the same few fields or params keep travelling together.
- Primitive Obsession — a primitive/string standing in for a domain concept
  that deserves its own type.
- Repeated Switches — the same switch/if-cascade on the same type recurs.
- Shotgun Surgery — one logical change forces scattered edits across many
  files.
- Divergent Change — one file/module is edited for several unrelated
  reasons.
- Speculative Generality — abstraction/parameters/hooks added for needs
  nothing currently has.
- Message Chains — long a.b().c().d() navigation the caller shouldn't
  depend on.
- Middle Man — a class/function that mostly just delegates onward.
- Refused Bequest — a subclass/implementer that ignores or overrides most
  of what it inherits.

For each finding: name it, quote the exact file, line, and hunk, and state
whether it violates a specific documented repo standard (cite the file/rule)
or matches a baseline smell (name it). Do not fix anything — report only.

Write your report using CONTEXT.md's Language section vocabulary wherever a
finding touches a domain concept (say "Seat," not "constituency"; "Coalition,"
not "party"; and so on for every term CONTEXT.md defines) — avoid every
synonym its entries list as "Avoid."
```

**Worker B — Correctness pass:**

```
You are reviewing [the whole codebase / the diff between commit
<last-bug-review-sha> and <main-sha>] of the live-political-analysis repo.

Read CONTEXT.md first — it defines this repo's domain vocabulary (Seat,
Coalition, Baseline, Swing, Projection, MPProfile, Bill, etc.) and a
recurring discipline worth checking for specifically: several types
(MPProfile, Bill) require that any absent/missing field carry an explicit
recorded reason rather than being silently blank or guessed. A loader that
accepts an unexplained absence, or code that fills a blank with a plausible
invented value instead of surfacing the reason, is a real bug in this
codebase's terms, not a style nit.

Check what you're reviewing for genuine correctness/logic bugs, independent
of any written spec — does the code actually do what it appears to be
trying to do. Look specifically for: wrong conditionals, off-by-one errors,
mishandled edge cases, race conditions, and the absence-without-reason
pattern above.

For each finding: quote the exact file, line, and hunk, and state the
concrete failure scenario — what input or state triggers it, and what the
wrong output or behavior is. A suspicion with no concrete failure scenario
isn't a finding; keep looking or drop it. Do not fix anything — report
only.

Write your report using CONTEXT.md's Language section vocabulary wherever a
finding touches a domain concept (say "Seat," not "constituency"; "Coalition,"
not "party"; and so on for every term CONTEXT.md defines) — avoid every
synonym its entries list as "Avoid."
```

### 3. Collect the workers' output

Wait for the user to paste back both workers' raw findings.

### 4. Verify — resolve any ambiguity immediately

For each candidate finding from either worker: open the actual file(s) at
the cited lines and trace the concrete failure scenario yourself against
the real code — don't just restate the worker's claim as true.

- **You can trace and reproduce the failure scenario yourself** — it's
  `CONFIRMED`. Move on, no need to involve the user.
- **You can't fully confirm it from reading alone** — don't tag it and set
  it aside for later. Ask the user directly, right here, with the concrete
  finding and what you could and couldn't verify about it. Let them decide:
  file it as an issue anyway, or drop it. Whatever they decide is final for
  that finding — there's no intermediate "noted but undecided" state.

Treat every worker claim as unverified until it's reached one of those two
outcomes. See `docs/agents/daily-check.md`'s "Verification" section for why
this is a separate model checking, not the same worker double-checking
itself, and for why ambiguity gets resolved here rather than bundled for a
later report.

### 5. File

File a GitHub issue for every finding that's either `CONFIRMED`, or that the
user chose to file despite the ambiguity in step 4:

```
gh issue create --title "<short bug description>" --label needs-triage --body "$(cat <<'EOF'
Found by daily-check's [Standards/Correctness] pass.

**File**: path:line
**Failure scenario**: <concrete input/state -> wrong output>

<any other detail from verification worth recording — note here if this was
filed despite ambiguity, at the user's explicit call>
EOF
)"
```

Anything the user chose to drop in step 4 isn't filed at all — mention it
briefly in step 9's report so it isn't forgotten, but it needs no further
action from here.

### 6. Address pass

Once every `CONFIRMED` finding has a filed issue, write and hand the user
two more prompts — one per worker, each scoped only to the issues that
worker's own pass produced (Worker A → issues from the Standards pass,
Worker B → issues from the Correctness pass):

```
You filed the following issue(s) in a previous pass over this repo:
<issue numbers/URLs, one per line>

For each one, either:

(a) Fix it. Make the change, verify it against this repo's own checks —
for Python, run all three of `ruff check .`, `ruff format --check .` (a
separate step from `ruff check` — CI runs both, and a fix can pass the
first while still failing the second), and `pytest`; for ts/, `npm run
lint`, `npm run typecheck`, and `npm test` — match whichever the changed
file belongs to. Commit locally once all of them pass. Do not push —
AGENTS.md forbids it; Claude pushes once your commit is independently
verified. Then comment on the issue with what changed and the commit SHA,
and close it.

(b) Push back. If you believe the finding isn't a real bug or isn't worth
fixing, comment on the issue explaining why, in enough detail that someone
reading only the issue can judge whether you're right. Leave the issue
open — do not close it yourself for a push-back.

Do not touch any issue outside this list.

Write every commit message, issue comment, and push-back explanation using
CONTEXT.md's Language section vocabulary wherever it touches a domain
concept — avoid every synonym its entries list as "Avoid."
```

Wait for the user to paste back both workers' responses.

### 7. Verify the address pass

Before judging individual issues, independently re-run the full mechanical
check yourself — `ruff check .`, `ruff format --check .`, `mypy`, `pytest`
(and the ts/ equivalents if anything there changed) — rather than trusting
a worker's reported numbers. Run this after every worker claims to be done,
not mid-flight: if two workers are editing the same shared checkout at
once, a transient failure from the other worker's in-progress edit can look
like a real regression (see `docs/agents/daily-check.md`'s known
limitations). `ruff check` and `ruff format --check` are two separate CI
steps — a change can pass one and fail the other, and only running the
first is exactly the gap that let a real CI failure through on this skill's
first run.

For each issue from step 6, check its real state yourself — treat both
workers' claims as unverified, same discipline as step 4:

- **Claimed fixed, and it genuinely resolves the failure scenario recorded
  when filed**: close it yourself if the worker didn't already. Terminal —
  no need to involve the user.
- **Pushed back, and the reasoning clearly holds up** (the finding really
  was a false positive): close the issue yourself and label it `wontfix`.
  Terminal — this is a plain judgement call you can make.
- **Everything else — ask the user, live, in this session, before going
  any further.** This covers: a claimed fix that doesn't actually resolve
  the failure scenario when you check it, a push-back whose reasoning
  doesn't clearly settle the question, and an issue the worker never
  touched at all. Don't label it and move on — put the concrete situation
  to the user directly (what was claimed or argued, what you found when
  you checked) and get a real decision: fix it another way, accept the
  push-back as `wontfix` anyway, send it back to a worker for another
  attempt, or something else they choose. Act on whatever they decide
  immediately, in the same session — the point of asking live instead of
  parking it as `ready-for-human` is that the session ends with a decision
  made, not a label applied. The one exception: if the user explicitly says
  they want to hold onto a specific issue and handle it themselves later,
  that's their call to make — leave it open (`ready-for-human` fits this
  case), and say so plainly in step 9's report rather than treating it as
  resolved.

### 8. Advance the checkpoint

Advance the tag once every issue from step 5 has reached an actual decision
this session — closed (fixed-and-verified or `wontfix`), or explicitly left
open because the user chose to defer it after being asked directly in step
7. An issue that's still ambiguous — nobody's decided anything about it yet
— blocks this step: go back to step 7 rather than advancing past it.

**Advance to the current `main` HEAD, not the SHA recorded in step 1.** The
address pass adds real commits on top of that SHA (fixes, and anything you
made directly resolving a step-7 live question), and every one of them has
already been personally verified by you — re-diffing against the step-1 SHA
next time would hand the workers commits you've already scrutinized as if
they were new, unreviewed code.

```
git rev-parse HEAD  # confirm this is genuinely the last commit made this run
git tag -a last-bug-review -m "daily-check: <one-line summary of this run>" HEAD
git push origin last-bug-review
```

(First run establishing the tag: `-a` with a message, no `-f` needed. A
later run replacing an existing tag needs `-f` on both the tag and the
push, same as before.)

### 9. Report

Tell the user: which issues got filed (including any filed only because
they chose to, despite ambiguity in step 4), anything dropped in step 4,
what happened to each filed issue in the address pass (fixed /
accepted-as-wontfix / resolved live in step 7 / left open by their own
explicit choice), and whether the checkpoint advanced. In the normal case
every ambiguity got resolved live as it came up — in step 4, then again in
step 7 if needed — and the checkpoint advances with nothing left open.
Don't repeat `CONFIRMED` findings' full detail — the issue is the record,
not this message.

## See also

`docs/agents/daily-check.md` — why this stays attended rather than
scheduled, why Claude (not a third Antigravity worker) verifies, and the
known limitations of the fixed Gemini Flash tier.
