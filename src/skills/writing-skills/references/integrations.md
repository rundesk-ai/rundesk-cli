# Skills that reach external services

Read this before adding credentials, profiles, or a script that calls an API or service. A skill that
only teaches a workflow needs none of this.

## Declare required values

Put `rundesk.json` beside `SKILL.md`. Its only key is `needs`, mapping each environment variable to an
actionable explanation:

```json
{
  "needs": {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com"
  }
}
```

- Declare only required values. Omit `rundesk.json` when nothing is required.
- Use plain names. Rundesk derives named profiles from suffixed values such as
  `JIRA_API_TOKEN__ACME`.
- Order values as an owner should enter them: service, account, then credential.
- Explain where to obtain each value. `doctor` repeats this text when the value is missing.
- Never put a token or credential in the skill.

An owner configures the declared values at their own terminal:

```sh
"$RUNDESK_COMMAND" skills configure <catalog>/<skill>
"$RUNDESK_COMMAND" skills configure <catalog>/<skill> --profile <name>
```

New values reach the next turn, not the current one; a running process cannot receive a changed
environment.

## Read values in a script

Read values from the ordinary process environment at the moment they are used. Accept a profile as
input; rundesk does not remap a named profile onto the unsuffixed names:

```python
import argparse
import os

parser = argparse.ArgumentParser()
parser.add_argument("--profile", default="")
profile = parser.parse_args().profile.strip().upper()

def env_name(name):
    return f"{name}__{profile}" if profile else name

base = os.environ[env_name("JIRA_BASE_URL")]
token = os.environ[env_name("JIRA_API_TOKEN")]
```

Never write a value into the agent's files or logs. The agent's data is backed up; secrets are kept
outside it so backups cannot contain them.

For multiple accounts, list the complete profiles and ask which one to use when the request does not
decide:

```sh
"$RUNDESK_COMMAND" skills profiles <catalog>/<skill>
```

A named profile carries all of its own suffixed values. Pass the selected name to the script's
`--profile` option. Do not fall back to an unsuffixed value; that can combine one account's URL with
another account's token.

## Ship commands deliberately

Put runnable commands directly under `scripts/`; use subdirectories only for code those commands
import. Tell the agent exactly when to run each command and which arguments it takes.

Rundesk installs no dependencies for a skill. Keep a script self-contained with its language's
standard library, or explicitly check for an external program and report how to obtain it. Make each
command executable, return non-zero on failure, send the reason to stderr, and keep successful output
bounded and token-lean.

Prefer concise plain text over JSON when an agent will read the result. Emit structured data only when
another program, rather than the model, needs it.

## Diagnose configuration

```sh
"$RUNDESK_COMMAND" skills doctor <agent>
"$RUNDESK_COMMAND" env check <NAME>
```

`doctor` names the unusable profile, missing value, or non-executable command and prints the repair.
`env check` distinguishes a missing value from one the install cannot read. Do not report the service
broken until both checks pass.
