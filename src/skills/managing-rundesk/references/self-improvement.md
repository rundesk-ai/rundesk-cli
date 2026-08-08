# Evidence-based self-improvement

Read this only when self-improvement itself is the task. This is a focused review, not ordinary task
overhead. Improve future execution from evidence; do not turn one difficult run into permanent
rules, memory, or capability changes.

## Bounded review

1. Read `MEMORY.md` and only indexes it links. Establish the agent's durable role, responsibilities,
   active scope, and owner preferences.
2. Start with previous `agent-upkeep` scheduled runs when they exist: inspect the schedule and its
   bounded messages with public Rundesk commands, then compare what went well, what did not, and what a
   prior action already resolved. Continue across the full bounded evidence window at listing level,
   opening only relevant recent messages and turns. Look for repeated lookups, owner corrections,
   failed or blocked outcomes, unsupported claims,
   missing context, avoidable rework, and useful skills or delegations that were ignored. Narrow
   before using `--full`; never open agent records directly.
3. Classify evidence before changing anything:
   - keep a durable owner preference, role fact, cross-project process, trap, or gotcha in compact
     personal continuity;
   - keep client/project mappings in a maintained shared index when several entries outgrow memory;
   - keep changing or project-specific evidence in that project's own files;
   - propose a durable product/process fix for repeated friction rather than recording endless
     workarounds; and
   - discard one-off outcomes that do not change a future action.
4. Inspect `"$RUNDESK_COMMAND" agents` and `"$RUNDESK_COMMAND" gateways`. Compare available and
   granted skills with `"$RUNDESK_COMMAND" skills list`, `"$RUNDESK_COMMAND" skills list <agent>`,
   and `"$RUNDESK_COMMAND" skills doctor <agent>`. Exclude yourself. Only an active gateway is a
   delegation candidate. Require explicit focus and skill evidence. Never infer a specialist's
   focus from its name, or usefulness from non-use. Use gateway state only to determine delegation
   availability; do not turn transient hosting or supervision state into a capability finding.
5. Route a proven capability gap in this order:
   - prefer a named specialist when its focus and skills make it materially better for heavy,
     self-contained work;
   - use a provider-local helper for independent heavy work needed in the same turn when no named
     specialist fits; then
   - find or create a skill only for a recurring capability gap this agent must own and neither
     route covers. Skills do not replace delegation.
   Before recommending a skill, report the evidence that the gap recurs, belongs to this agent, and
   why neither route covers it.
6. Treat grants conservatively. Non-use alone is not evidence that a skill is wrong. Revocation is
   rare: require a confirmed role change, repeated mismatch, or proof that a standing specialist now
   owns the capability. Never recommend revoking the required `managing-rundesk` skill.
7. Apply a safe local continuity improvement when the evidence directly supports it, this schedule
   authorizes it, and it affects only agent-owned memory or indexes. Do not merely recommend work the
   agent can safely finish and verify itself. If a fix needs wider authority, report the exact owner
   decision needed and why.
8. Do not change grants, install catalogs, create skills, or edit standing rules without explicit
   authority in this request or schedule. Otherwise report the exact evidence-backed recommendation
   and the command or skill-authoring follow-up the owner can approve.
9. Reread changed continuity, verify each claimed improvement against the evidence, and give one
   complete final report: evidence reviewed, changes made, recommendations, preserved uncertainty,
   and how the result was checked.

Useful bounded entry points:

```sh
"$RUNDESK_COMMAND" messages AGENT --since YYYY-MM-DD --limit 50
"$RUNDESK_COMMAND" messages AGENT --source schedule --limit 10
"$RUNDESK_COMMAND" turns AGENT --limit 20
"$RUNDESK_COMMAND" agents
"$RUNDESK_COMMAND" gateways
"$RUNDESK_COMMAND" skills list
"$RUNDESK_COMMAND" skills list AGENT
"$RUNDESK_COMMAND" skills doctor AGENT
```

Start narrower when the review names a client, project, correction, failure, or time window. Read a
full message or turn only after the bounded listing identifies relevant evidence. For prior upkeep,
select the `(schedule agent-upkeep)` conversation shown by the listing, then read that conversation
by ID. Another audience's history remains private and is used only when needed for this agent's
improvement.

## Definition of done for each firing

- Maintenance is complete and verified before retrospective work begins.
- The retrospective covers the full bounded evidence window, compares the previous entry, records
  each material success/failure and its solution route, and is reread after any change.
- Self-improvement either finishes every safe authorized local fix or names the exact owner decision
  required; it checks named specialists, provider-local helpers, and available and granted skills.
- A no-change result follows evidence of what was checked, never a superficial scan.
- Before the final, verify every claimed change and preservation, every requested phase, and the
  absence of leftover task scratch. Anything unverified is blocked, not done.

## Combined upkeep contract

An `agent-upkeep` run uses the maintenance reference first, the retrospective reference second, and
the self-improvement reference last. Work sequentially. Do not open the next reference until the
current phase is verified. The initiator owns timing and supplies the evidence window; these
references own the work and definition of done.

Keep its final exactly one sentence, very short and attention-first:

- No attention: `Upkeep complete — continuity and workspace tidied; no owner action needed.`
- Attention required: `Upkeep needs attention — <the owner action and its reason>.`

The detailed verification remains in turn records; the owner-facing schedule response is not an
audit transcript. See [Schedules](schedules.md) for timing and recovery rules.
