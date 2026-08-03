# Operating rundesk

The exact commands behind each area. Everything here is built.

## Agents and the gateways that run them

```sh
rundesk agents [<name>]        every agent, or one: what it is and where it keeps things
rundesk doctor <name>          what stands between an agent and a working turn
rundesk add <name>             make an agent, and the gateway that runs it
rundesk configure <name>       change its provider, model, settings or instructions
rundesk remove <name>          take one away for good
rundesk start|stop|restart <name>
```

`add` makes the agent *and* its gateway; `remove` takes both — you cannot end up with one
without the other. `configure --provider` clears provider-specific model and settings unless
replacements are given.

## Reaching one

```sh
rundesk ask <name> "…"         one turn, streamed back
rundesk channels <name>        add · show · remove · instructions
```

On a single-user Discord channel, `/provider <provider>` changes the agent-wide default after
Rundesk checks authorization and the adapter; the next message starts fresh and a running turn
finishes on the provider it began with. Shared channels cannot change a default.

**A credential is never an argument.** Anything on a command line is in the process list and in
shell history. Rundesk takes a token on standard input or from a file the owner controls.

## The install

```sh
rundesk status                 how rundesk is on this machine
rundesk version                what is installed, and whether it is current
rundesk config                 every install-wide value in force
rundesk skills                 every skill here, and who has which
rundesk usage [<name>]         what it has cost
rundesk logs <name>            what a gateway has been saying, when something failed
```

## The values every program here is given

```sh
rundesk env                    every value kept, and never one of them
rundesk env show <NAME>        how one is kept, and what tells it apart
rundesk env check [<NAME>]     whether each can still be produced
rundesk env --where            the directory they are kept in
```

One set for the whole install. Every brain, every channel adapter, every schedule and every
integration command is given all of it — which is why an integration command finds its
credential without anybody exporting anything: the shell you run it in descends from a
program rundesk started with these in its environment.

A value is either **held** by this install or **fetched** by a command whose words are kept
and run again each time a program starts. A listing never runs one, so it is free; `check`
does, which is why it may take a moment — and `env set --from` runs one once, when it is
placed, to prove it works before anything is written down. Nothing else does.

**No form of this shows a value.** The last few characters and a mark are what you get, and
the mark is taken with a key of this install's, so two names showing one mark hold one
value and the same value on another machine marks differently. There is no flag for the
rest — asked what a value is, say that nothing on this machine can answer that.

`check` tells two failures apart and so must you. **`could not answer`** means the command
timed out or would not start — that says nothing about whether the value is good, so never
advise replacing a credential on it. Anything else it prints is the command's own words for
why there is no value to give. Neither is the same as a name being *refused*, which is
`env set` rejecting a name outright and is a different situation entirely.

Placing one is the owner's at a terminal — `rundesk env set <NAME>`, typed with echo off.
You may run it for a value **you** minted; never ask a person to send you one, because
anything said to you is in the record and possibly in a chat room.

## When something is not there

A command that does not exist means an older rundesk than this file describes — check
`rundesk version`. A command that reports `NOT AVAILABLE` is registered and not built yet;
rundesk declares its whole surface from the outset so nothing pretends to have worked. Either
way, say what you found rather than working around it.
