<p align="center">
  <a href="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml"><img src="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases/latest"><img src="https://img.shields.io/github/v/release/rundesk-ai/rundesk-cli?style=flat-square" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/macOS%20%C2%B7%20Linux-lightgrey?style=flat-square" alt="macOS and Linux">
  <img src="https://img.shields.io/badge/build%20step-none-green?style=flat-square" alt="No build step">
</p>
<p align="center">
    🚀 <a href="#-quick-start"><strong>Quick start</strong></a>
    &nbsp;·&nbsp;
    ✨ <a href="#-what-it-does"><strong>What it does</strong></a>
    &nbsp;·&nbsp;
    🧠 <a href="#-bring-your-own-brain"><strong>Brains</strong></a>
    &nbsp;·&nbsp;
    💬 <a href="#-reach-it-where-you-already-are"><strong>Channels</strong></a>
    &nbsp;·&nbsp;
    📖 <a href="#-documentation"><strong>Docs</strong></a>
</p>

# 🖥 rundesk

**Give your AI coding agent a name, a home, and a phone number.**

rundesk turns the provider CLI you already have — Codex, Claude Code, or one you wrote
yourself — into a named agent that stays running, works on a schedule, and answers you on
Discord. It uses the CLI you're already signed in to, so there are no API keys to manage,
nothing to host, and no build step.

## ⚡ It's this simple

```sh
rundesk add ava --provider codex
rundesk ask ava "what changed in this repo today?"
```

That's a working agent. `ava` has her own workspace, her own memory files, and her own
conversation history — kept apart from every other agent on the machine.

## 🎯 Highlights

- **Your CLI is the brain.** rundesk runs Codex, Claude Code, or your own program. It never
  reimplements the agent loop, so you keep the tools, permissions and session you already have.
- **Reachable from Discord.** Message your agent from your phone. It opens a thread, shows you
  what it's doing as it works, and posts the answer when it's done.
- **Works while you don't.** Schedules run on the clock — never late, never twice, never
  overlapping.
- **Stays up.** Your machine keeps each agent running and brings it back after a crash or a reboot.
- **Remembers everything.** Every turn is recorded — what was asked, what it did, what it cost.
- **Nothing to manage.** Standard-library Python and one directory under your home. The single
  package Discord needs goes into rundesk's own virtualenv — never your system Python.

## 💡 Why rundesk?

Provider CLIs are excellent and they all stop at the same place: they run in your terminal,
and when you close it, they're gone. rundesk is the part around them.

- **One agent, many ways in.** The same `ava` — same memory, same workspace — answers you in
  the terminal, on Discord, and on a schedule. Which model answers is decided per entry point,
  not baked into the agent.
- **Swap anything, change nothing.** A brain is a program rundesk runs, not a plugin it loads.
  So is a channel. A brain nobody here has heard of is first-class, not degraded —
  [a stranger wrote one from the guide alone](.knowledge/guides/write-a-provider-adapter.md) and
  it passed the same test suite the shipped one does.
- **Honest about what it doesn't do.** A command that isn't built says so and exits with its own
  code, so a script can tell "this version doesn't have that" from "you typed it wrong".

## 🚀 Quick start

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
```

Everything lands in **`~/.rundesk`** — one directory under your home. Your shell profile is left
alone; if the command isn't on your `PATH`, the installer shows you the line to add rather than
editing a file you own.

### Make an agent

```sh
rundesk add ava --provider codex     # a brain this machine already has
rundesk doctor ava                   # what stands between ava and a working turn
```

### Ask it something

```sh
rundesk ask ava "summarise what's still failing in CI"
```

Answers stream to your terminal. Ask again and it remembers — same conversation, same session.

### Keep it running

```sh
rundesk start ava        # your machine keeps it up, and brings it back after a reboot
rundesk agents           # every agent, and what each is doing
rundesk logs ava         # everything it's said
```

```
AGENT    STATE    PID    UPTIME  LAUNCHD JOB  VERSION  WORK
ava      RUNNING  4192   2h14m   LOADED       0.4.0    2 (a-conversation, another)
codex    STOPPED  -      -       NOT LOADED   -        -
```

### Give it work that starts itself

```sh
rundesk schedules ava add nightly --when "0 3 * * *" -- rundesk ask ava "what changed today?"
rundesk schedules ava
```

```
SCHEDULE  STATE  WHEN       NEXT              LAST RUN          OUTCOME
nightly   ON     0 3 * * *  2026-07-27 03:00  2026-07-26 03:00  finished
```

## 💬 Reach it where you already are

```sh
rundesk channels ava add discord --kind discord --allow <your-user-id>
```

One command sets up both direct messages and rooms. **Nothing to look up** — the adapter signs
in and asks Discord which servers your bot is in, so you never copy an ID out of a URL.

Then just message it. It opens a thread, marks your message seen, shows its work as it goes, and
posts the answer whole when it's finished.

Three things worth knowing:

- **You must say who may use it.** There's deliberately no way to say "anybody" — an agent that
  answers whoever speaks to it, on a machine where it runs tools, is a mistake and not a mode.
- **Your token is never an argument.** It's read from an environment variable or a file you
  already control. Anything on a command line is readable through the process list.
- **Adding a channel proves it works first.** It connects, signs in, and checks it can see what
  it was pointed at. If it can't, nothing is saved and you're told why.

Tell it where it is, so it doesn't answer a room of forty people the way it answers a DM:

```sh
rundesk channels ava instructions discord-rooms \
    "You are {agent} in {where.channel}, and {called} is asking. Anyone can read this — keep it short."
```

## 🧠 Bring your own brain

```sh
rundesk add ava --provider /opt/my-brain --model fast-1 --set effort=high
```

A brain is **a program rundesk runs**, not code it loads — so it can be written in any language,
and a shell script is enough. rundesk hands it the working directory, the model and the prompt,
and reads back one JSON record per line.

Nothing about your brain leaks into rundesk: there is no list of providers and no list of models
anywhere in the codebase. → **[Write a provider adapter](.knowledge/guides/write-a-provider-adapter.md)**

Channels work exactly the same way. → **[Write a channel adapter](.knowledge/guides/write-a-channel-adapter.md)**

## ✨ What it does

**Agents**
- One name, one home — rules, memory, workspace and skills, kept apart from every other agent
- Its own private provider home, so two agents never share a session or a config
- `doctor` tells you what's missing before you need it at three in the morning

**Staying up**
- One gateway per agent, so restarting one never disturbs another
- Owns everything it starts — ending it ends the provider and every tool it spawned
- Comes back after a crash or a reboot; a gateway that *can't* run stops cleanly instead of looping

**Schedules**
- Never late, never overlapping, and exactly once for the minute it's due — across restarts and
  across the hour the clock goes back
- A program that can't be found is refused when you write the schedule, not at 3am

**Channels**
- Threads, reactions and typing on Discord; a plain surface still carries the whole turn
- Work shown as it happens; the answer posted whole rather than rewriting itself
- Stop or forget a conversation from the chat itself

**History**
- Every turn recorded — what was asked, what the brain did, how it ended, what it cost
- Kept apart from what the brain printed, so diagnostics can be deleted and the record survives

## 📟 Every command

```sh
rundesk --help
```

Read off the command itself, so it can never disagree with what you have installed. The full
reference is **[CLI.md](CLI.md)**, generated from the parser.

```sh
rundesk version --check    # what you have, and whether it's current
rundesk update             # move to the newest release
rundesk status             # how rundesk itself is on this machine
rundesk remove ava         # take an agent away  (--purge takes its home too)
rundesk uninstall          # take rundesk off this machine
```

Removing rundesk stops every agent first, and refuses outright if one won't stop — half-removed
is worse than not removed. What your agents *wrote* is kept unless you ask for `--purge`.

## 📖 Documentation

- **[CLI.md](CLI.md)** — every operation and argument, generated from the command
- **[Write a provider adapter](.knowledge/guides/write-a-provider-adapter.md)** — put your own brain behind an agent
- **[Write a channel adapter](.knowledge/guides/write-a-channel-adapter.md)** — reach an agent from your own platform
- **[Contracts](.knowledge/prd/README.md)** — what rundesk guarantees, row by row, each naming the test that proves it
- **[Roadmap](ROADMAP.md)** — what's built, what's next, and why in that order
- **[Architecture](.knowledge/CODEMAP.md)** — where everything lives

## 🧪 Tests

No runner to install, nothing reaches the network, and no provider is ever started:

```sh
python3 .knowledge/scripts/gate     # every suite, both doc linters, and a real install
python3 tests/test_store.py         # or any one on its own
```

Every ✅ in the [contracts](.knowledge/prd/README.md) names the test that proves it, and the build
fails if a row names a test that doesn't exist.
