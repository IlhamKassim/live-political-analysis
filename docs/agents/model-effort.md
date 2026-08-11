# Model and effort policy

Settled via `/grill-me` on 2026-08-12. When any session in this repo dispatches
an agent — via `to-tickets`, `implement`, a direct `Agent` call, or anything
else — it picks the model and states the effort per this policy, not by
ad hoc judgment re-derived each time.

## The rule: cheap by default, escalate on trigger

Default to the cheapest capable model. Escalate to the strong model only when
the task hits one of the five triggers below. A fixed lookup table of task
categories was considered and rejected — this project's work doesn't repeat
cleanly enough for a table to stay accurate, and a trigger rule travels to
task types that don't exist yet.

## Tiers

**Two tiers only: Sonnet (default) and Opus (triggered).**

Haiku was considered and dropped. The test proposed for "Haiku-worthy" was: the
entire correct output can be fully specified in the prompt itself, with no
need to read project context (`CONTEXT.md`, an ADR, a sibling module) to know
what "correct" even means. Almost nothing this project has produced clears
that bar — even ostensibly mechanical work (writing the GE16 process page,
wiring nav links) needs enough context-reading that a third tier would exist
in name only. If a genuinely Haiku-sized task shows up later (a single
fully-specified rename, a one-file lookup-and-report), nothing stops using it
then — this policy just doesn't reserve a tier for a case that hasn't
happened.

## The five escalation triggers

Any one of these justifies Opus. None of them present → Sonnet.

1. **Visual/design judgment** — "does this look right," typography, layout,
   register. Worked example: issue #25's register prototype (comparing the
   dashboard's print register against a distinct warmer register) — a
   judgment call about how something *looks*, not a rule that can be checked.

2. **Editorial judgment on sensitive content** — where subtly wrong framing
   costs trust, not just correctness. Worked example: issue #27's Coalition
   explainer, which necessarily touches ethnic and religious lines in
   Malaysian coalition politics — the standard from #22 (facts and structure
   only, no motive-narration, cite rather than assert) needs judgment to
   apply correctly, not just mechanical compliance.

3. **Code review** — any `/code-review` pass, either axis (Standards or
   Spec), every time. The whole point of a review pass is catching what a
   cheaper pass would miss; running it on the cheap model defeats its
   purpose.

4. **Security- or correctness-critical engineering** — not "any code," but
   code where a subtle mistake defeats the thing's actual purpose. Worked
   example, and a real miss: issue #24's citation-check tool went out on
   Sonnet for its initial build, and a `/code-review` pass later found an
   unmitigated prompt-injection gap — a source page could talk the judge into
   a false verdict, defeating the one thing the tool exists to do. A
   trust/verification mechanism like this should hit this trigger from the
   start, not only get caught at review time.

5. **Irreversible or hard-to-reverse decisions** — anything a mistake in is
   expensive to undo (matches the general safety framing already applied to
   destructive git operations, force-pushes, merges, deletions).

Everything else — mechanical translation of already-settled definitions,
wiring/integration, routine tooling, procedural content — defaults to Sonnet.
Worked examples from #22's children: the core-terms glossary page (#26,
translating `CONTEXT.md`'s existing definitions), the GE16 process page (#28,
procedural, low editorial risk), and the final wiring/integration ticket (#29,
apart from its own `/code-review` step, which hits trigger 3).

## "Effort" — what the label actually means

There is no settable effort parameter for a dispatched agent, unlike model.
"Medium" / "high" effort, as used in this repo's ticket tables (see
`docs/design/HANDOFF.md`'s workflow table, which predates this policy but
uses the same label), is **shorthand for how much verification and
thoroughness gets written into the subagent's prompt** — not a setting to
look for.

- **Medium effort**, concretely: "implement, run the tests, report the
  result." Standard care, no extra verification loop demanded.
- **High effort**, concretely: "verify each claim/decision against the real
  thing before reporting done — don't take the first pass at face value, and
  where a prior pass's claim can be independently checked (a test re-run, a
  fetched source, a rendered page), check it rather than trust it."

High effort should generally accompany an Opus dispatch (the triggers above
tend to be exactly the cases worth double-checking), but the two are
conceptually separate: model is *capability*, effort is *how much the prompt
asks the agent to verify its own work*.

## Where this gets applied

- **`to-tickets`**, run in this repo, states a model/effort line per this
  policy for every ticket it produces (see issues #24-#29 for the pattern
  already in use, e.g. #24's "Suggested model / effort" section).
- **Any direct `Agent` dispatch** in this repo — from `implement`, from a
  grilling/wayfinder session, or ad hoc — picks model per the trigger list
  and states effort in the subagent's prompt per the definitions above.
- This is repo-scoped. The shared `to-tickets` skill file itself
  (`~/.claude/skills/to-tickets/`) is untouched — this policy applies only
  because `CLAUDE.md` in this repo points to it, not because the skill
  changed for every project.
