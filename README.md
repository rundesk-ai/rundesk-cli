<p align="center">
  <a href="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml"><img src="https://github.com/rundesk-ai/rundesk-cli/actions/workflows/build.yml/badge.svg" alt="Build"></a>
  <a href="https://github.com/rundesk-ai/rundesk-cli/releases/latest"><img src="https://img.shields.io/github/v/release/rundesk-ai/rundesk-cli?style=flat-square" alt="Latest release"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/macOS%20%C2%B7%20Linux-lightgrey?style=flat-square" alt="macOS and Linux">
  <img src="https://img.shields.io/badge/build%20step-none-green?style=flat-square" alt="No build step">
</p>
<p align="center">
    ✅ <a href="#-what-rundesk-does"><strong>What it does</strong></a>
    &nbsp;·&nbsp;
    🚀 <a href="#-install"><strong>Install</strong></a>
    &nbsp;·&nbsp;
    💬 <a href="#-reach-it-where-you-already-are"><strong>Channels</strong></a>
    &nbsp;·&nbsp;
    🧠 <a href="#-bring-your-own-brain"><strong>Brains</strong></a>
    &nbsp;·&nbsp;
    📖 <a href="#-documentation"><strong>Docs</strong></a>
</p>

# 🖥 rundesk

**Your AI coding agent, always running — and reachable on the channels you already use.**

## 💡 The problem

Your coding agent lives in a terminal window. Close the window and it's gone: the context, the
conversation, everything it knew. It can't work overnight, you can't check on it from
somewhere else, and there's no record of what it did.

## ✅ What rundesk does

rundesk keeps that agent running as a named thing on your machine, with its own home and its
own memory — and lets you reach it from a chat channel instead of a terminal.

**It doesn't replace your agent.** It runs the CLI you already have — Codex, Claude Code, or
one you wrote — so you keep its tools, its permissions and its login exactly as they are.

|  |  |
|---|---|
| 🏠 **It has a home** | Its own workspace, memory and rules, kept apart from every other agent |
| 💬 **You can message it** | Reach it on Discord from anywhere, and watch it work as it goes |
| ⏰ **It works while you don't** | Schedules that run on the clock — never late, never twice |
| ♻️ **It stays up** | Your machine restarts it after a crash or a reboot |
| 📝 **It remembers** | Every turn recorded — what was asked, what it did, what it cost |
| 📦 **Nothing to manage** | One directory under your home. No server to host, no build step |

## ⚡ How you use it

```sh
rundesk add ava --provider codex
rundesk ask ava "what changed in this repo today?"
```

That's a working agent. Two more commands and it's always on and reachable:

```sh
rundesk start ava                                                  # keep it running
rundesk channels ava add discord --kind discord --allow <your-id>  # and message it
```

## 🚀 Install

```sh
curl -fsSL https://github.com/rundesk-ai/rundesk-cli/releases/latest/download/install.sh | bash
```

Everything lands in **`~/.rundesk`** — one directory under your home, with the program in
`app/` and everything you make beside it:

```text
~/.rundesk/
  app/          rundesk itself — what an update replaces and an uninstall removes, whole
  data/         everything you make — your agents, your skills, and what your gateways wrote
```

That split is the point: removing rundesk takes `app/` and is structurally incapable of
reaching `data/`, rather than remembering a list of things to spare. Your shell profile is
left alone too; if the command isn't on your `PATH`, the installer shows you the line to add
rather than editing a file you own.

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
ava      RUNNING  4192   2h14m   LOADED       0.5.0    2 (a-conversation, another)
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

### Teach it how you do something

A skill is a folder with a `SKILL.md` in it — what to do, and one line saying when it applies.
Write it once into the library, then give it to the agents that should have it:

```sh
mkdir -p "$(rundesk skills --where)/release-notes"
$EDITOR "$(rundesk skills --where)/release-notes/SKILL.md"
rundesk skills grant ava release-notes
rundesk skills
```

```
SKILL           FROM      AGENTS
release-notes   yours     ava
writing-skills  built-in  ava, winston
```

**The brain finds it by itself.** Rundesk never puts a skill in a prompt — it costs one line
of context until the turn it is actually needed, and the agent decides that, not us. Every
agent starts with `writing-skills`, so you can ask one to write the next skill for you.

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

Nothing about your brain leaks into rundesk — there is no list of providers and no list of models
anywhere in the codebase. A brain nobody here has heard of is first-class rather than degraded:
[a stranger wrote one from the guide alone](.knowledge/guides/write-a-provider-adapter.md) and it
passed the same test suite the shipped one does, without a line of rundesk changing.

Channels work exactly the same way, which is why the same agent — same memory, same workspace —
can answer you in the terminal, on Discord and on a schedule, with a different model each time.

→ **[Write a provider adapter](.knowledge/guides/write-a-provider-adapter.md)** ·
**[Write a channel adapter](.knowledge/guides/write-a-channel-adapter.md)**

## 🧰 Everything it does

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

**Skills**
- Write one once; every brain that agent reaches finds it **by itself** — nothing is pasted
  into a prompt, so a skill costs a line of context until the moment it is actually used
- Give it to the agents that should have it and nobody else: `rundesk skills grant ava deploy`
- Built-in skills come with rundesk and move forward with it; yours are never touched

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
