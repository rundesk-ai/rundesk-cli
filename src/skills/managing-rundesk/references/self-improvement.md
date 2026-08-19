# Evidence-based self-improvement

Read this only when self-improvement itself is the task. This is a focused review, not ordinary task
overhead. Improve future execution from evidence; do not turn one difficult run into permanent
rules, memory, or capability changes.

## Bounded review

1. Read `MEMORY.md` and only indexes it links. Establish the agent's durable role, responsibilities,
   active scope, and owner preferences. Maintenance preservation remains in force: never open a
   symlink or its target in this or any later phase; inspect link metadata and target spelling only.
2. Start with previous `weekly-self-improve-upkeep` scheduled runs when they exist: inspect the schedule and its
   bounded messages with public Rundesk commands, then compare what went well, what did not, and what a
   prior action already resolved. Continue across the full bounded evidence window at listing level,
   opening only relevant recent messages and turns. During combined upkeep, begin with at most 50
   messages or 20 turns and open at most three full turns. Expand a listing or open another full
   turn only when a named material question cannot be resolved from the bounded evidence; record the
   reason before expanding. Never exceed 100 messages, 40 turns, or five full turns; if that evidence
   cannot resolve the question, stop, make no durable behavioral improvement from the unresolved
   evidence, and record the uncertainty rather than loading more. Use the attention result only when
   a specific owner action can resolve a required blocker. Identify
   candidates across the full window, then investigate at most two repeated frictions with the
   greatest owner impact or avoidable cost. Do not audit every possible capability merely because it
   exists. When selected friction has an independent heavy research question and provider-local
   helpers are available, launch at least one and synthesize its result. If such a question exists but
   provider-local helpers are unavailable, record the unavailable route and continue only with bounded
   local evidence. If no selected friction contains such a question, record that fact without further
   helper analysis. Look for repeated
   lookups, owner corrections,
   failed or blocked outcomes, unsupported claims,
   missing context, avoidable rework, and useful skills or delegations that were ignored. Narrow
   before using `--full`; never open agent records directly.
3. Classify evidence before changing anything:
   - require two independent occurrences before promoting a lesson into memory, a standing rule,
     automation, a skill, or another durable behavior change. One owner correction belongs in the
     retrospective, not permanent continuity, unless it explicitly states a durable preference or
     corroborates earlier evidence;
   - keep a durable owner preference, role fact, cross-project process, trap, or gotcha in compact
     personal continuity;
   - keep client/project mappings in a maintained shared index when several entries outgrow memory;
   - keep changing or project-specific evidence in that project's own files;
   - propose a durable product/process fix for repeated friction rather than recording endless
     workarounds;
   - measure avoidable token, context, tool-call, latency, and provider-cost overhead, choosing the
     smallest durable improvement that removes repeated work without creating maintenance debt; and
   - discard one-off outcomes that do not change a future action.
4. When one of the selected frictions may be a capability, delegation, or grant gap, inspect
   `"$RUNDESK_COMMAND" agents` and `"$RUNDESK_COMMAND" gateways`, then compare only the relevant
   available and granted skills with `"$RUNDESK_COMMAND" skills list`,
   `"$RUNDESK_COMMAND" skills list <agent>`, and `"$RUNDESK_COMMAND" skills doctor <agent>`.
   Otherwise skip this inventory. Exclude yourself. Only an active gateway is a delegation
   candidate. Require explicit focus and skill evidence. Never infer another agent's focus from its
   name, or usefulness from non-use. Use gateway state only to determine delegation availability;
   do not turn transient hosting or supervision state into a capability finding. Never open another
   agent's home, memory, or records; these public surfaces are the boundary.
5. Route a proven capability gap in this order:
   - prefer a named agent when its focus and skills make it materially better for heavy,
     self-contained work;
   - use a provider-local research helper for independent heavy work needed in the same turn when no
     named agent fits;
   - propose a new named agent only when a recurring heavy boundary has no focused owner
     and the evidence justifies its ongoing cost; then
   - find or create a skill only for a recurring capability gap this agent must own and neither
     route covers. Skills do not replace delegation.
   Before recommending a skill, report the evidence that the gap recurs, belongs to this agent, and
   why neither route covers it.
6. Treat grants conservatively. Non-use alone is not evidence that a skill is wrong. Revocation is
   rare: require a confirmed responsibility change, repeated mismatch, or proof that another agent now
   owns the capability. Never recommend revoking the required `managing-rundesk` skill.
7. Apply a safe local improvement when the evidence directly supports it and this schedule
   authorizes it. This includes compact agent-owned memory/index changes and a small cross-project
   script under `scripts/` when repeated evidence proves it saves work. A script states its purpose,
   inputs and safety limits, contains no secrets, and is exercised against a fixture after its final
   edit. Derive a post-edit fixture matrix from every documented input type and error branch. Cover
   missing, unreadable file, unreadable directory, and direct symlink inputs when accepted or
   claimed safe; a skipped input is reported, never called clean. Do not merely recommend work the
   agent can safely finish and verify itself. If a fix needs wider authority, report the exact owner
   decision needed and why.
8. Do not change grants, install catalogs, create skills or standing agents, or edit standing rules without explicit
   authority in this request or schedule. Otherwise report the exact evidence-backed recommendation
   and the command or skill-authoring follow-up the owner can approve.
9. Reread changed continuity and artifacts, verify each claimed improvement against the evidence,
   and state how the next upkeep cycle can measure whether it helped. Keep the detailed evidence in
   the work and turn record. During combined upkeep use the exact short final below; when this review
   is the whole task, report evidence, changes, recommendations, uncertainty, and verification.

Classify the outcome honestly. A retrospective, `OPEN_ITEMS.md` reconciliation, brief update, or
future experiment does not count as self-improvement by itself. An applied improvement must change
future execution now, be verified at its actual boundary, and name what the next cycle will measure.
When repeated evidence does not justify such a change, record that no durable change was justified;
do not manufacture activity.

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
select the `(schedule weekly-self-improve-upkeep)` conversation shown by the listing, then read that conversation
by ID. Another audience's history remains private and is used only when needed for this agent's
improvement.

## Definition of done for each firing

- Maintenance is complete and verified before retrospective work begins.
- The retrospective covers the full bounded evidence window, compares the previous entry, records
  each material success/failure and its solution route, and is reread after any change.
- Self-improvement selects at most two repeated frictions, then either finishes every safe authorized
  local fix for them or names the exact owner decision required. It checks named agents, helpers,
  skills, memory/index changes, and automation only when a selected friction makes that route
  relevant.
- A selected material independent research question uses a provider-local helper when one is
  available. When provider-local helpers are unavailable, record that route and continue only with
  bounded local evidence. With no such selected question, record only that fact without further
  helper analysis; named-agent evaluation never crosses the public Rundesk boundary.
- The review identifies avoidable token/cost/repeated-work overhead and either removes one proven
  source safely or explains why no durable change is justified.
- Any agent-owned automation is verified after its final edit against every documented input type,
  error branch, and stated safety limit.
- A no-change result follows evidence of what was checked, never a superficial scan.
- Before the final, verify every claimed change and preservation, every requested phase, and the
  absence of leftover task scratch. Anything unverified is blocked, not done.

## Combined upkeep contract

A `weekly-self-improve-upkeep` run uses the maintenance reference first, the retrospective reference second, and
the self-improvement reference last. Work sequentially. Do not open the next reference until the
current phase is verified. The initiator owns timing and supplies the evidence window; these
references own the work and definition of done.

Keep its final exactly one sentence, very short and attention-first:

- Applied improvement: `Upkeep completed — improved <specific behavior>; no owner action is needed.`
- Honest no-change: `Upkeep completed — no durable change was justified; no owner action is needed.`
- Attention required: `Upkeep needs attention — <the owner action and its reason>.`

Use the attention result when an incomplete required phase, an unverified claimed improvement, or a
known operational failure needs owner action. Unrelated tracked work already recorded in its
canonical source does not force attention unless this upkeep proves that record inaccurate or unsafe.

The improvement phrase names the behavior changed, not the file edited. Detailed verification
remains in turn records; the owner-facing schedule response is not an audit transcript. See
[Schedules](schedules.md) for timing and recovery rules.
