# Delegation operations

Read this reference before starting a handoff or acting on one already in progress. It is the
command and state contract; the main skill owns the judgment about whether to delegate and how to
review the result.

## Start and inspect

Inside an agent turn, `ask` hands work to another agent and returns immediately:

```sh
"$RUNDESK_COMMAND" ask <agent> '<brief>'
```

The target must be within this agent's delegation scope and its gateway must be running. A turn
already answering a delegation cannot delegate again. Do not bypass either boundary with an
attended `ask`.

An optional provider, account alias, or model applies only to this handoff and does not reconfigure
the target:

```sh
"$RUNDESK_COMMAND" ask <agent> '<brief>' --provider <provider> [--alias <alias>] [--model <model>]
```

Keep the returned delegation id. Use the management surface to inspect it:

| Need | Inside the delegating agent's turn | From an attended terminal |
|---|---|---|
| List delegated work | `"$RUNDESK_COMMAND" asked` | `"$RUNDESK_COMMAND" asked --agent <delegator>` |
| Show one in full | `"$RUNDESK_COMMAND" asked show <id>` | `"$RUNDESK_COMMAND" asked --agent <delegator> show <id>` |

`show` distinguishes what provider, alias, and model were requested; what was fixed at admission;
and what the target provider actually reported. Do not turn an unreported terminal model into the
requested or configured one.

## Steer, stop, or resume

Use a separate verb for each state transition:

| Operation | Command inside the delegating turn | Valid state and effect |
|---|---|---|
| Steer | `"$RUNDESK_COMMAND" asked say <id> '<words>'` | `working`; offers guidance to the live provider and keeps it for the next turn if missed |
| Stop | `"$RUNDESK_COMMAND" asked stop <id>` | `working`; records a stop request, then shows `stopping` until the target settles as `stopped` |
| Resume | `"$RUNDESK_COMMAND" asked resume <id> '<more>'` | `answered`; reopens the same delegation, conversation, provider selection, and provider session |

From a terminal, put `--agent <delegator>` immediately after `asked`. `say`, `stop`, and `resume`
cannot change the provider or model chosen when the handoff was admitted.

Do not infer success from the management command alone. `say` proves guidance was stored, not that
the active provider accepted it. `stop` proves a request was recorded, not that the process has
ended. `resume` proves answered work was reopened, not that the additional result is complete.

A steered turn may answer the new guidance while omitting work required by the original brief.
Review the return against both. If the delegation is now `answered` and required evidence is still
missing, resume the same delegation with a bounded correction instead of accepting the partial
answer or opening a duplicate handoff.

## Follow the asynchronous return

The target works from its own home, instructions, memory, and skills. Its answer returns verbatim and
unchecked to the delegating agent. If the original provider turn is still active and steerable, the
answer may reach it there; otherwise Rundesk wakes a review turn.

Do not poll. While the target owns the next action, either continue independent in-scope work or end
with the delegated answer as the event that resumes the parent outcome. When the answer arrives,
review it before adopting any claim or artifact.

The states name the only valid next actions:

- `working`: inspect, steer, or request stop.
- `stopping`: wait for the terminal stop; do not claim it is already stopped.
- `stopped`: closed without an answer; start a new delegation if more work is needed.
- `answered`: review the result, or resume it with a bounded follow-up.

Two handoffs to the same target are separate delegations and conversations. Resume only when the
follow-up depends on the prior context; otherwise create a new bounded handoff.
