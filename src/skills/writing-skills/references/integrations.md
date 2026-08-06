# Skills that reach something outside this machine

Read this when the skill you are writing has to sign in to something — an API, a ticket tracker, a
deploy service. A skill that only tells an agent *how* to do something needs none of it.

The whole contract is one optional file beside your `SKILL.md`, and it has one key.

## Say what it needs, and why

```json
{
  "needs": {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com"
  }
}
```

That is `rundesk.json`, and it drives everything: the install preview, the guided
`"$RUNDESK_COMMAND" skills configure`, which accounts exist, every listing, and every `doctor`
verdict.

**The reason against each name is the load-bearing part.** It is what somebody reads when `doctor`
says a value is missing, and the only thing telling them where to go and get one. "the API token" is
not a reason. "an API token from id.atlassian.com" is.

**Declare them in the order somebody would set them up** — the site, then the account, then the
token. `configure` asks in the order you wrote them.

**Never put a credential in a skill.** Name the variable; the owner places it themselves at their own
terminal, where nothing writes it down:

```sh
"$RUNDESK_COMMAND" env set JIRA_API_TOKEN
```

## How your scripts get the values

Every value the install keeps is in the environment of the turn. A script you ship reads it the
ordinary way and does nothing special to get it:

```python
import os
import urllib.request

base = os.environ["JIRA_BASE_URL"]
token = os.environ["JIRA_API_TOKEN"]
```

**Read them at the moment you use them, and never write one into a file.** What a turn records stands
under the data root, which a backup copies whole — the one place that must stay free of credentials.

**A value placed now reaches the *next* turn.** The environment was built when this turn started, and
nothing can change a running program's. An agent that has just been told to set something has to be
told that too.

## More than one account is free

An owner with three Jira sites sets `JIRA_BASE_URL__ACME`, `JIRA_EMAIL__ACME`, `JIRA_API_TOKEN__ACME`
and the same again for `__BETA`, and rundesk finds those profiles from the plain names you already
declared. **You declare the plain names and nothing else** — no profile list, no edit to your catalog
when a fourth account appears.

Two things follow, and both are somebody else's problem rather than yours:

- **A profile carries all of its own values or it is reported incomplete.** A named profile never
  falls back to the plain value, because that is how one site's URL comes to be used with another
  site's token and the request succeeds against the wrong company. Nothing you write has to handle a
  half-configured account.
- **Which account to use is the turn's decision, not the skill's.** Say in your body that a profile
  may be named, and let the agent ask.

## Shipping commands

Anything in `scripts/` is a command your skill ships. Only what stands directly in it — anything
deeper is a library your own script reaches for, and offering those as commands tells an agent to run
files nobody meant to be run.

```text
jira/
├── SKILL.md
├── rundesk.json
└── scripts/
    └── search.py        chmod +x
```

**Make them executable.** A script that is present and not executable looks exactly like one that
works, right up until something tries it — `doctor` reports the skill `UNRUNNABLE` and names the
`chmod`, but that is a round trip nobody needed.

Write them in the standard library of whatever they are. A script that needs a package the install
does not have is a script that fails on the first machine that is not yours.

## When it does not work

```sh
"$RUNDESK_COMMAND" skills doctor <agent>
```

It says which value is missing, which account it belongs to, what that value is *for* — your reason,
carried through — and the one command that fixes it. It exits non-zero when anything is wrong, so it
can be gated on.

`BLOCKED` means no account is usable. `PARTIAL` means some are and some are not, which is the state
three accounts produces and the one worth looking at: something works, and something fails at three
in the morning.

Before reporting an integration broken, check `"$RUNDESK_COMMAND" env check <NAME>`. "Cannot be read"
and "was never set" are different faults with different fixes, and it says which.
