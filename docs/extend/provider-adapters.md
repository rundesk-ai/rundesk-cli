---
title: Provider adapters
description: Put another brain behind a Rundesk agent by writing an executable that speaks newline-delimited JSON.
sidebar:
  order: 1
---

A provider adapter puts a brain behind an agent. It is **an executable, not a plugin** —
Rundesk runs it as a program and exchanges newline-delimited JSON records with it over
stdio.

That seam is the reason a custom adapter is not second-class. Write one in Python, Go, Rust,
or a shell script, and it receives the same agent homes, schedules, channels, turn records,
usage reporting, and lifecycle as the four that ship.

```sh
rundesk add ava --provider /opt/my-provider --model fast-1 --set effort=high
```

## The two questions an adapter answers

1. **Can you run?** Rundesk asks before it commits — this is what `rundesk doctor` surfaces,
   and what makes `configure --provider` safe to run on a live agent.
2. **What happened during this turn?** The adapter reports messages, tool activity, the
   outcome, and token usage as records, and Rundesk stores them in its own normalized form.

The second one is where adapters are usually left half-finished. An adapter that runs but
reports nothing produces an agent that works and has no history.

## The contract

The full record-by-record contract, including the traps that cost a feature, lives with the
code and ships as a skill:

→ **[The provider adapter contract](https://github.com/rundesk-ai/rundesk-cli/blob/main/src/templates/skills/building-a-provider-adapter/references/the-contract.md)**

If you are working with a Rundesk agent, grant it the `building-a-provider-adapter` skill and
it will follow the contract rather than improvising one.

## Changing an agent's brain

Adapters are swappable without touching identity:

```sh
rundesk configure ava --provider /opt/my-provider
```

Rundesk validates the adapter can run, then switches atomically. A turn already underway
finishes on the provider it started with.
