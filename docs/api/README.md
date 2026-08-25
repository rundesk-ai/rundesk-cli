# api/

The surface Rundesk publishes — every operation somebody can invoke, and what each one guarantees.

This is reference. You look something up here rather than reading it through. How a subsystem works,
why it behaves the way it does, and every state it can get stuck in are topic pages one level up.

| Page | What it answers |
|---|---|
| [commands.md](./commands.md) | Every operation the command offers, what each guarantees, and what it exits with |

`commands.md` is the complete operation list, and that is load-bearing rather than aspirational:
there is no verb on that page that does not work, and no verb in the command that the page does not
name. `tests/test_skills_bundled.py` holds both directions for the `skills` group, so a verb added
without its documentation, or documented without existing, fails a suite.

The adapter contracts are published surfaces too, but they are written as guides rather than
lookups — read [`../adapters.md`](../adapters.md) for the channel side and
[`../providers.md`](../providers.md) for the provider side.
