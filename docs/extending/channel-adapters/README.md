# Building a channel adapter

A channel adapter is how an agent is reached from somewhere — a chat app, a board, a webhook,
anything that can carry a message. Like a provider adapter it is **a program rundesk runs**,
never code it loads, so it can be written in anything.

**Read [`references/the-contract.md`](./references/the-contract.md) before writing the
code.** It is the whole contract and is authoritative where this page disagrees: every
record, every field, what is required and what is optional, and a working adapter in
twenty lines. This page is what you need to *start* and to avoid the expensive
mistakes — it is deliberately not the reference.

## Your adapter answers two questions

### One: can you reach it?

Run with `--check` and whatever the owner typed. Connect, sign in, verify you can actually see
the place you were given, print one JSON object, exit `0`:

```json
{"ok": true, "settings": {"space": "9930", "room": "1180"},
 "secret": {"env": "MY_TOKEN"}, "describes": "#operations in Acme"}
```

| | |
|---|---|
| `ok` | whether this channel should be allowed to exist at all |
| `settings` | everything you need next time, in your own words — handed back and never read |
| `secret` | *where* the credential was found, so it can be shown as present without being shown |
| `describes` | one line naming what you can see, for a person deciding if it is the right place |
| `why` | when `ok` is false, what was wrong and what to do about it |

**Nothing is written down until you say `ok`.** A misconfigured channel must be found while
somebody is standing at a terminal, not at three in the morning when somebody asks the agent
something. Cannot sign in, cannot see the room, given options you do not understand? Say
`ok: false` — a channel that was never added beats one that is silently deaf.

**Say what you understood, not what you were told.** Normalise `settings` here: resolve a name
to an id, drop what you ignored, fill in what you defaulted. What you return is what an owner
will still be running on in a year.

**Say `ok: false` and still exit `0`** when the refusal was considered. What is read is the
answer, not the code — but a program that dies without printing one failed rather than refused,
and an owner is shown the difference.

### Two: carry one conversation

You hold the connection open and pass messages both ways as JSON records, one per line.

**Rundesk decides what state a turn is in. You decide only how it looks.** Five states arrive
as `state` records, in this order:

| | |
|---|---|
| `taken` | picked up — the first thing that happens, and the one worth showing fastest |
| `running` | under way; `run` and `can` first appear here |
| `finished` | it worked, and the answer has already been handed to you |
| `stopped` | somebody stopped it |
| `failed` | it did not work, and `why` says what went wrong |

Never work one out for yourself. An adapter that decided when a message had been *seen* would
be re-implementing the turn, and two surfaces would eventually disagree about the same run
while the run's own account matched neither.

## The rules that will bite you

**Work goes out early, prose does not.** What the agent *did* — a tool it ran, a thought it
closed — arrives while it is happening and is worth showing then. What it *says* arrives once,
at the end, as a single `answer`. You are never handed a part-written one, so you cannot post
half a sentence. If your platform can edit, edit the running commentary — **never the answer**.

**Show what you have and skip what you have not.** There is no capability declaration. No
reactions? Never mark anything. No typing indicator? Never type. Cannot edit? Post again. The
turn completes regardless: correctness never degrades, only fidelity. **A surface that can only
post text is a first-class channel, not a broken one.**

**Ask what the brain can do before offering it.** The opening `state` carries `can`, which is
what the *brain* declared. Offering somebody a way to interrupt a turn whose brain said
`steer: false` offers something that cannot happen.

**Gateway inspection is closed and read-only.** An adapter may report a `query` for
`status`, `version`, `agents`, or `help`; Rundesk authorizes it and answers with the
correlated `query-result`. Never turn a platform command into arbitrary CLI arguments.

**A tool's verb is one of a closed list** — `read`, `search`, `run`, `edit`, `list`, `make`,
`delegate` — or absent. Never render your own word for one; a channel that recognised a
vendor's tool names would carry that vocabulary forever.

**Never a credential as a command-line argument.** Read it from an environment variable or a
file the owner already controls, and report only *where* it was found.

## Proving it

The same suite every shipped channel passes:

```sh
python3 tests/test_channel.py --adapter /path/to/your-adapter
```

It reaches no platform and needs no token — the adapters it drives are small programs, which is
what yours is. Then:

```sh
rundesk channels ava add ops --kind /opt/my-channel --allow someone -- <your options>
```

Everything after `--` reaches you exactly as typed. Rundesk does not parse it, does not
validate it, and has no list of what your platform needs.

## Gotchas

**A gateway holds the adapter it imported when it started.** Editing your adapter and
restarting *it* is not enough — the gateway is a separate, longer-lived process. Restart the
gateway after changing anything it loads, or you will be debugging a version that is no longer
on disk.

**A second connection with the same credential silently wins.** Running your adapter by hand to
diagnose it, while a gateway is already serving that channel, makes one of the two stop
receiving with no error on either side. Stop the gateway first, or accept that what you are
watching is not what the gateway sees.

**Who may use it is rundesk's decision, not yours.** Every channel names who is allowed when it
is added. Do not implement your own allowlist; carry who spoke and let rundesk refuse.
