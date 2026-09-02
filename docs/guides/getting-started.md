# Set up your first agent

Install Rundesk, give an agent a name and a brain, ask it something, and keep it reachable after the
terminal closes. About ten minutes.

**You need** macOS, Python 3.9 or newer, and one [supported coding CLI](../api/providers.md) already
installed and signed in — `codex`, `claude`, `grok` or `antigravity`. Rundesk uses the login you
already have and never copies a provider credential.

## 1. Install

```sh
curl -fsSL https://get.rundesk.ai/rundesk | bash
```

Everything Rundesk keeps goes under one directory, `~/.rundesk`. Check it landed:

```sh
rundesk status
```

`fit to run` says `yes`, and `program` names the copy that answered. If `rundesk` is not found, the
installer printed where it put the command — add that directory to your `PATH`.

## 2. Make an agent

```sh
rundesk agents add ava --provider codex --describes "Owns research and summaries."
```

It reports the home, logs and records it made, and one note worth reading: **the provider is
recorded and not proven.** Adding an agent runs no adapter and checks no sign-in. Prove it
separately:

```sh
rundesk providers check codex
```

`--describes` is optional and worth setting: it is what *other* agents read when deciding whether a
piece of work is this one's to do.

## 3. Ask it something

```sh
rundesk ask ava "summarise what changed in this repository today"
```

The next `ask` continues the same conversation. `--fresh` starts a new one on the brain.

```sh
rundesk ask ava --read-only "what changed today?"
rundesk ask ava --model opus "review this"
```

`--read-only` is a request sent to the provider, not an operating-system sandbox.

## 4. Keep it available

So far the agent only exists while you are typing at it. A **gateway** is a supervised process that
holds the agent's name; `launchd` brings it back after a crash, a reboot or an update.

```sh
rundesk gateways start ava
rundesk gateways
```

`start` exits `0` only once a gateway has been shown to be holding the name — a job the supervisor
accepted is not a gateway that started. If it does not come up:

```sh
rundesk gateways logs ava
```

## 5. Reach it from somewhere else

A channel connects the agent to a platform. Discord is the adapter that ships:

```sh
rundesk channels add ava discord --allow <your-discord-user-id> --notify
rundesk gateways start ava
```

`--notify` makes this the channel adapter unprompted things go through — gateway notices, scheduled
results, delegation answers. Discord sends each one privately to every allowed user. The
[full Discord setup guide](./discord.md) walks through the Developer Portal and the permissions it
needs.

## 6. Schedule work

```sh
rundesk schedules add ava daily --when "0 4 * * *" --ask "review yesterday's changes"
```

The result is delivered through the agent's notified channel adapter; on Discord, every allowed user
gets a private copy. `rundesk schedules run ava daily` runs it now, in this terminal, without using
up the moment it was due for.

## Where to go next

| You want | Read |
|---|---|
| to run the install day to day | [managing-an-install.md](./managing-an-install.md) |
| named specialists instead of one agent | [teams.md](./teams.md) |
| one agent to hand work to another | [delegation.md](./delegation.md) |
| every verb and flag | [../api/](../api/) |
| how a subsystem works, and how it fails | [../concepts/](../concepts/) |
