# External-service integrations

Read this before adding credentials, profiles, OAuth, network access, or remote side effects. A skill
that only teaches a workflow needs none of this. A deterministic local command without an external
service uses [Reusable workflow scripts](workflow-scripts.md) instead.

## Define the integration contract

Name the user outcome, remote resource, allowed operations, account-selection rule, and proof before
choosing endpoints. Request the least privilege that can produce that outcome. Keep read and write
capabilities separate when the provider permits it; a broad grant makes every agent holding the
skill broader than the task that caused it to load.

Put provider mechanics in scripts and the decision to invoke them in `SKILL.md`. The skill must tell
the agent which command to run, which account and resource it affects, whether the command reads or
writes, and what observed result counts as success. Do not make the agent assemble requests or
interpret an undocumented response shape ad hoc.

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

## Declare an OAuth provider

When a catalog supplies an OAuth-backed integration, put `oauth-provider.json` beside the owning
`SKILL.md`. It is declarative data, never executable code. Schema 1 has exactly these fields:

```json
{
  "schema": 1,
  "provider": "example",
  "display_name": "Example",
  "authorization_endpoint": "https://identity.example/authorize",
  "token_endpoint": "https://identity.example/token",
  "identity_endpoint": "https://identity.example/me",
  "base_scopes": ["identity"],
  "identity": {"subject": "subject", "email": "email", "email_verified": "verified"},
  "authorization_parameters": {"prompt": "consent"},
  "client_secret": true,
  "capabilities": {"read-reports": "reports.read"}
}
```

Provider and capability IDs are lowercase hyphenated names. Endpoints must be HTTPS with no embedded
credentials, **no query string and no fragment** — an extra parameter a provider requires goes in
`authorization_parameters`, which may not override Rundesk's client, redirect, response, scope,
state, or PKCE fields. Base scopes establish a verified immutable subject and email; each capability
maps to exactly the additional scope its integration needs. Strings are bounded at 1,024 characters,
collections at 32 or 64 entries, and the file at 64 KiB.

Exactly one installed skill may declare a given provider ID; two make both unusable. A malformed
declaration is refused when the catalog is installed, and if one is already on disk it disables only
its own provider. The grant is pinned to a fingerprint of the behaviour fields, so changing an
endpoint, scope, identity field, parameter, or capability requires the owner to review and reconnect;
changing `display_name` does not.

Owners place the app client as ordinary sealed values and then sign in once:

```sh
"$RUNDESK_COMMAND" env set EXAMPLE_OAUTH_CLIENT_ID
"$RUNDESK_COMMAND" env set EXAMPLE_OAUTH_CLIENT_SECRET
"$RUNDESK_COMMAND" login example
```

The names are derived from the declared provider ID in the spelling a shell variable takes, so
document exactly those two for your provider. `login` uses what is already placed and prompts only
for what is missing. Write the setup instructions in that order — an owner is normally in the
provider's console with both values on screen before your catalog is installed.

**Document the default app and nothing else.** `--profile` selects a second OAuth *app client* and
suffixes both names (`EXAMPLE_OAUTH_CLIENT_ID__WORK`); it is an escape hatch for the rare install
with two apps, not the shape to teach. One app holds any number of connected accounts, and
`--email` is how an integration chooses between them.

Provider-specific instructions belong in this skill, not in Rundesk, and four different things must
be told apart plainly: which **APIs** to enable in the provider's console; which **consent-screen
scopes** the app requests; which **permissions the signing-in person must already hold** on the
resources; and which **account and resource** a command selects at run time. Say why any scope that
looks broader than "read" is required. Rundesk requests the minimum: the declared base scopes at
login, and one capability's scope when an integration first needs it.

## Ask for a token over the bridge

An integration never receives a refresh token, and never receives a client secret: both the sealed
grant document and every `<PROVIDER>_OAUTH_CLIENT_ID`/`_SECRET` value are withheld from what a turn
is handed. It creates `socket.socketpair()`,
passes one end to a Rundesk child, and asks for one short-lived access token:

```sh
"$RUNDESK_COMMAND" _oauth accounts <provider> --response-fd <fd> [--profile <app-profile>]
"$RUNDESK_COMMAND" _oauth access <provider> <capability> --response-fd <fd> [--profile <app-profile>] [--email <address>]
```

**Close the parent's copy of the child's socket end immediately after spawning.** Held open, the
pair never reaches end-of-file and the caller waits on a descriptor it owns itself.

Read a four-byte big-endian length, then that many bytes of version-1 JSON, bounded at 65,536.
Success carries only a bearer token, its expiry, and the account's email and subject; a refusal
arrives as `{"version":1,"ok":false,"error":"…"}` and the process also exits non-zero. Prefer the
framed reason over parsing stderr. Give the whole exchange a deadline of your own: Rundesk allows a
person 180 seconds at the browser when consent has to be widened.

Never put the inherited FD or the token in stdout, stderr, argv, the environment, a log, or a skill
file. Contract tests must use socket pairs and injected offline authorization/token boundaries;
cover multiple accounts, a single-account default, an unknown capability, a malformed or duplicated
declaration, a consent identity mismatch, a revoked grant, and concurrent scope extension.

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

Never write a value into the agent's files or logs. Rundesk keeps values in its private credential
store; backups carry the sealed store and its key, so their location must be protected.

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

Treat timeouts, rate limits, pagination, retries, and partial remote results as contract behavior:

- Set a finite timeout for every request. A network wait with no deadline is an unbounded agent
  turn.
- Follow documented pagination until the requested boundary is satisfied. Never report the first
  page as the complete resource.
- Retry only documented transient failures, with a small bound and backoff. Do not retry a mutation
  unless the provider supplies an idempotency guarantee or key.
- Refuse an ambiguous account or resource instead of choosing one by position, recency, or a partial
  name.
- On failure, return a redacted error that identifies the operation and recovery action without
  exposing a credential, authorization header, response body, or private resource content.

## Test the service boundary offline

Use offline contract tests with injected transports or recorded synthetic fixtures; the test suite
must never depend on a live account. Cover the documented success response and each response shape
the parser accepts, then cover:

- missing configuration and an incomplete named profile;
- authentication refusal and insufficient permission;
- account or resource ambiguity;
- timeout, rate limit, server failure, and malformed response;
- empty results, multiple pages, and a partial page failure;
- mutation refusal, duplicate submission, and safe retry behavior where writes exist; and
- output bounds and redaction of tokens and sensitive remote fields.

Run one explicitly authorized smoke test against the real service only when publication rules or the
request require it. Use a disposable or non-destructive resource where possible, verify the remote
result through an independent read, and clean up only when that cleanup is authorized.

## Diagnose configuration

```sh
"$RUNDESK_COMMAND" skills doctor <agent>
"$RUNDESK_COMMAND" env check <NAME>
```

`doctor` names the unusable profile, missing value, or non-executable command and prints the repair.
`env check` distinguishes a missing value from one the install cannot read. Do not report the service
broken until both checks pass.
