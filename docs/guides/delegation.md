# Have one agent hand work to another

Delegation is one agent asking another to do something and being owed an answer. It needs two things:
a scope that allows it, and a gateway running on **both** sides.

How it works underneath is [`../concepts/delegation.md`](../concepts/delegation.md); the verbs are
[`../api/conversations.md`](../api/conversations.md).

## 1. Describe each agent

The description is what the *other* agents read when deciding whose work something is. An agent
nobody has described is left out of that listing rather than named blank.

```sh
rundesk agents configure ava --describes "Owns research and synthesis."
rundesk agents configure bob --describes "Owns bounded implementation and review."
```

## 2. Set who may delegate to whom

Scope has three states, and the empty one is not the missing one.

```sh
rundesk agents configure ava --delegate-to-any        # every other agent (the default)
rundesk agents configure ava --delegate-to bob --delegate-to cole   # exactly these
rundesk agents configure bob --delegate-to-none       # inbound-only: may receive, may not delegate
```

```sh
rundesk agents      # the DELEGATES TO column shows any, none, or the names
```

## 3. Start a gateway on both sides

```sh
rundesk gateways start ava
rundesk gateways start bob
```

**The target's gateway picks the work up, and the delegator's gateway collects the answer.** A
delegation to an agent nothing is running is refused outright, naming the command to fix it — but
only when that agent is *known* to be stopped, because refusing on uncertainty is the worse error.

## 4. Hand work over

There is no separate verb. `ask` typed by a person is an ask; `ask` run by an agent **from inside its
own turn**, naming somebody else, is a delegation and returns at once:

```sh
rundesk ask bob "audit the exporter retention policy and report what you find"
```

The agent that asked carries on with its turn. When bob finishes, the answer is delivered into ava's
conversation as an ordinary message, which wakes ava to review it.

## 5. Watch and steer it

```sh
rundesk asked --agent ava        # from a terminal; inside a turn the agent is already known
rundesk asked show <id>
```

| Verb | Acts on | Does |
|---|---|---|
| `asked say <id> <words>` | work still going | stores guidance and offers it to the active turn |
| `asked stop <id>` | work still going | records an early end; the next gateway beat carries it out |
| `asked resume <id> <words>` | work already answered | carries the same ask on, in the session it had |

**`say` never fails for being late** — if the turn has just ended, the guidance waits for its next
turn on the same delegation. **`stop` is not instant**: the listing reads `stopping` until the
terminal outcome comes back, then settles as `stopped`, never `answered`. **Stopped work cannot be
resumed.**

All three are shown where the work was handed out, as one line of small print — *updated bob*,
*asked bob to stop*, *carried on with bob*. Never the words themselves: guidance is between two
agents.

## What is deliberately not possible

**The depth is one.** An agent answering a delegation is shown no team and is refused if it tries to
delegate anyway, so `ava → bob → ava` cannot be built. A turn woken to *review* an answer is an
ordinary turn and may hand out new work.

An agent cannot delegate to itself — that is a turn, not a delegation — and a person cannot delegate
at all; a person just asks.

## When one is not moving

| What you see | Usually |
|---|---|
| it stays working and the target never starts | the target's gateway is not running |
| the target answered and nothing came back | the *delegator's* gateway does the collecting, so it must be running too |
| `stopping` for more than a beat | the next pass has not happened, or the provider is still going down |
| refused with "not configured to delegate to" | the scope excludes the target |
