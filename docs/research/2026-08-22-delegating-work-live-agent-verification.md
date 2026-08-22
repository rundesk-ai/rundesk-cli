# Delegating-work live-agent verification

**Date:** 2026-08-22

**Candidate:** PR #438 implementation commit `c0ac509`

**Providers:** Claude CLI 2.1.236, reported model `claude-opus-5[1m]`; Codex CLI 0.148.0,
reported model `gpt-5.6-sol`

**Fixture:** A fresh scratch Rundesk install and a four-file, read-only session-contract project

## Purpose

Test whether a separate `delegating-work` skill improves an agent's decision to delegate, the
quality of its brief, and its handling of asynchronous returns. The runs also exercise steering,
resuming, state inspection, evidence review, provider provenance, and the boundary with ordinary
Rundesk management. No candidate skill was installed into the live Rundesk home.

The fixture declares three requirements: a 900-second session lifetime, immediate token revocation
on logout, and case-insensitive email comparison. Its observations violate the first two. Its only
permitted command, `python3 verify.py`, prints both finding identifiers but exits zero. That gives a
small, reproducible contract audit plus a separate integration defect.

## Method and matrix

The candidate source was installed into a fresh temporary `RUNDESK_HOME`. Source and installed
SHA-256 hashes matched for `SKILL.md`, `references/operations.md`, and
`references/brief-examples.md`. All agents, gateways, conversations, messages, and fixture files
used for counted evidence lived under that scratch root.

| Run | Skills available to lead | Prompt shape | Result |
|---|---|---|---|
| A — baseline | `managing-rundesk`, no `delegating-work` | Small release-readiness decision; specialist merely available | Correct findings, but the lead first duplicated the complete audit and then delegated the same audit for confirmation |
| B — candidate control | Revised `delegating-work` and `managing-rundesk` | Same small task and availability | Correctly worked directly: three tiny files and one deterministic command did not justify coordination |
| C — candidate delegation | Revised `delegating-work` and `managing-rundesk` | Independent contract audit plus separate integration review | Delegated the bounded audit to Codex, retained integration ownership, reviewed the return, and issued the final decision |
| D — steering and recovery | Same delegation as C | Terminal steering asked how to classify exit code zero | The steer-only answer omitted the original evidence contract; Claude rejected it and resumed the same delegation for the missing evidence |
| E — unavailable provider | Revised skill on a Grok lead | Scratch-isolation probe | Not counted: Grok refused to open a conversation with `Authentication required` |

## Delegation decision and brief quality

Run B is the matched behavioral improvement. The baseline's redundant handoff added coordination
after the lead had already completed the specialist's work. With the candidate, the lead explicitly
applied the necessary-only rule and declined to delegate merely because a matching target existed.

Run C supplied a task where delegation was proportionate. Before handing it off, Claude loaded
`delegating-work`, read the project rules and matching brief example, and checked gateway state. The
stored brief named all of the following rather than relying on conversational implication:

- the bounded contract-audit outcome and the larger release decision;
- the exact three files and the separation from the lead-owned integration review;
- read-only authority and the single permitted command;
- quoted requirement and observation evidence, line locations, full stdout and stderr, and numeric
  exit status;
- observable done conditions and a structured return format.

The lead then reviewed integration independently without duplicating the delegated file audit. The
initial handoff was `del-3-c2e538`; supported `asked show` output recorded Codex as the effective and
terminal provider and `gpt-5.6-sol` as the terminal model.

## Steering, resuming, and review

While the delegation was `working`, an attended `asked say` asked the reviewer to distinguish a
contract mismatch from a verifier-integration limitation. The guidance was stored and reached the
active target, but the next answer addressed only that clarification. The delegation became
`answered` without the evidence required by the original brief.

Claude did not confuse an answered state with a satisfactory result. Its review listed the missing
quotes, locations, streams, and exit code; inspected provider provenance; and resumed
`del-3-c2e538` with a bounded correction. Codex returned the full three-requirement audit from the
same delegation and provider session. Claude retraced every material claim, reproduced the command,
rejected one overbroad uncertainty claim, and issued a no-go covering both contract failures and the
zero-exit integration defect. Final state was `answered`.

This exposed a useful edge: steering can shape the target's next terminal answer without satisfying
the original contract. The final skill now tells the delegator to review against both the steer and
the original brief, then resume the same answered delegation when evidence is missing.

All counted Claude and Codex turns ended `done`; their turn records reported zero unknown, lost, or
unsent events. Rundesk's return messages labeled delegated results as unchecked, and the lead treated
them that way.

## Scope boundaries and limitations

- Grok CLI 1.0.5 passed the adapter capability probe but could not authenticate, so no Grok agent
  behavior is claimed.
- A Codex-as-lead isolation probe inherited the operator's live command path instead of the scratch
  command path. It made only read-only `status` and `agents` calls, changed no live state, and was
  excluded. Codex is counted only as the scratch delegated reviewer, where its recorded conversation,
  messages, and turns remained in the scratch install.
- Live stop delivery was not forced because the bounded reviewer turns completed too quickly to make
  a natural stop reliable. The command, valid-state, `stopping`, and terminal `stopped` contract is
  covered by the skill's deterministic bundled tests; live runs covered `working` and `answered`.
- This is one synthetic audit workflow on macOS. It proves the handoff lifecycle and writing behavior,
  not every domain-specific delegation judgment.

## Exact-head confirmation and cleanup

Commit `c0ac509` was installed back into the same scratch home. The source and installed hashes were
identical:

| File | SHA-256 |
|---|---|
| `SKILL.md` | `548d84064d34f3afe9be022948a3c9f5f280607977c3fb98f440590725acea06` |
| `references/operations.md` | `ac646c907127bfb9fd2b51152f190151c9897f1bd88a6b621e7da8249bd58aaa` |
| `references/brief-examples.md` | `a00e2ff6788cb0d67e91ed59b89512076865c1af6a0a6ef4f9bbca14efb41eae` |

The focused bundled-skill suite passed 38 tests. Removing the observed steering/original-brief rule
made that suite fail, and restoring it returned the suite to green. Both configured Python paths ran
the full aggregate suite: 80 suites, zero failures each. Ruff and `git diff --check` also passed.

The substantive live runs preceded the final one-sentence steering correction that their observed
edge produced. An exact-commit provider rerun was attempted after reinstall, but Claude reported
`Not logged in` before doing work; it is not counted as confirmation. Exact-commit installation and
deterministic verification passed, while the live behavioral claim remains tied to the measured
working candidate whose only later skill-body change was that correction.

All manually hosted scratch gateways were stopped after evidence capture. The temporary scratch
home was then moved to Trash, so cleanup remains recoverable. No skill, agent, provider, gateway, or
configuration was installed into or changed in the live Rundesk home.

## Verdict

The separate skill is materially better than bundling delegation into `managing-rundesk`. Delegation
has its own routing trigger, proportionality judgment, brief contract, asynchronous state machine,
provider provenance, steering and resumption behavior, and evidence-review obligation. Ordinary
Rundesk management needs none of that reasoning. Keeping the workflows separate made the matched
candidate avoid a redundant handoff while still producing and managing a strong handoff when the
task genuinely required independent work.
