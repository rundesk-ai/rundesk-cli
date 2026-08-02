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

## When something is not there

A command that does not exist means an older rundesk than this file describes — check
`rundesk version`. A command that reports `NOT AVAILABLE` is registered and not built yet;
rundesk declares its whole surface from the outset so nothing pretends to have worked. Either
way, say what you found rather than working around it.
