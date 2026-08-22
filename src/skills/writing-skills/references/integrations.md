# External-service integrations

Read this in addition to [Reusable workflow scripts](workflow-scripts.md) when a command uses
credentials, profiles, OAuth, a network, or remote effects. Define the outcome, remote resource,
allowed operations, account selection, least privilege, and observable proof before choosing
endpoints. Keep read and write capabilities separate when possible.

Put provider mechanics in scripts. `SKILL.md` tells the agent which command to run, which account
and resource it affects, whether it reads or writes, and what observed result proves success.

## Declare required values

Put `rundesk.json` beside `SKILL.md`; its only key is `needs`:

```json
{
  "needs": {
    "JIRA_BASE_URL": "your Jira site, e.g. https://acme.atlassian.net",
    "JIRA_EMAIL": "the account the token belongs to",
    "JIRA_API_TOKEN": "an API token from id.atlassian.com"
  }
}
```

Declare only required plain names, ordered service, account, credential. Explain how to obtain each
value; `doctor` repeats the text when missing. Never put a credential in the skill. Rundesk derives
named profiles from suffixes such as `JIRA_API_TOKEN__ACME`.

The owner configures values at their terminal:

```sh
"$RUNDESK_COMMAND" skills configure <catalog>/<skill>
"$RUNDESK_COMMAND" skills configure <catalog>/<skill> --profile <name>
```

New values reach the next turn, not the running process.

## Declare OAuth

An OAuth-backed catalog puts `oauth-provider.json` beside the owning `SKILL.md`. Schema 1 has exactly
these fields:

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

Use lowercase hyphenated provider and capability IDs. Endpoints are HTTPS with no credentials,
query, or fragment; extra parameters go in `authorization_parameters` and cannot override client,
redirect, response, scope, state, or PKCE fields. Base scopes establish a verified immutable subject
and email; each capability adds exactly its needed scope. Strings are at most 1,024 characters,
collections 32 or 64 entries, and the file 64 KiB.

Only one installed package may declare a provider ID. A malformed declaration is refused at install
or disables only its own installed provider. Grants fingerprint behavior fields, so endpoint, scope,
identity, parameter, or capability changes require review and reconnection; `display_name` changes do
not.

Set the default app client, then sign in:

```sh
"$RUNDESK_COMMAND" env set EXAMPLE_OAUTH_CLIENT_ID
"$RUNDESK_COMMAND" env set EXAMPLE_OAUTH_CLIENT_SECRET
"$RUNDESK_COMMAND" login example
```

Document the derived names and this order. Teach only the default app: `--profile` is the rare
second app client and suffixes both names; one app may hold many accounts, selected with `--email`.
Distinguish enabled provider APIs, consent scopes, the signer's existing permissions, and the
runtime account and resource. Explain any scope that appears broader than read-only.

## Request a short-lived token

The turn receives neither refresh token nor client secret. Create `socket.socketpair()`, pass one end
to a Rundesk child, and request accounts or one capability token:

```sh
"$RUNDESK_COMMAND" _oauth accounts <provider> --response-fd <fd> [--profile <app-profile>]
"$RUNDESK_COMMAND" _oauth access <provider> <capability> --response-fd <fd> [--profile <app-profile>] [--email <address>]
```

Close the parent's copy of the child's socket end immediately after spawning or EOF never arrives.
Read a four-byte big-endian length followed by at most 65,536 bytes of version-1 JSON. `accounts`
success contains only account email addresses; `access` success contains only a bearer token, type,
expiry, email, and subject. Refusal contains `ok:false` and an error while the child exits nonzero.
Prefer that framed reason to stderr and bound the whole exchange; interactive consent may take up to
180 seconds.

Never expose the token through stdout, stderr, argv, environment, logs, or files. Pass the FD only as
the required numeric command argument; do not print or log it.

## Select ordinary profiles

Read ordinary values from the environment at point of use. Rundesk does not remap a named profile
onto unsuffixed names:

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

List complete profiles and ask which one to use when the request does not select one:

```sh
"$RUNDESK_COMMAND" skills profiles <catalog>/<skill>
```

Pass the selected profile to the script. Never fall back to unsuffixed values; that can combine one
account's URL with another account's token. Never write values into files or logs.

## Handle and test the service boundary

Follow the generic script contract, then add service behavior:

- Set finite timeouts. Follow pagination to the requested boundary; never call one page complete.
- Retry only documented transient failures with a small bound and backoff. Retry mutations only with
  a provider idempotency guarantee or key.
- Refuse ambiguous accounts or resources instead of guessing.
- Return a redacted error naming the operation and recovery action, without credentials, headers,
  response bodies, or private content.

Use offline contract tests with injected transports or synthetic fixtures. Test the OAuth bridge
with socket pairs and injected authorization and token boundaries so framing, EOF, and FD transfer
are real. Cover accepted success shapes; missing or incomplete configuration; authentication and
permission refusal; ambiguity; timeouts, rate limits, server failure, and malformed responses;
empty results, pagination, and partial pages; mutation refusal, duplicates, and safe retries; OAuth
account selection, unknown capabilities, malformed or duplicate declarations, identity mismatch,
revoked grants, and concurrent scope extension; plus output bounds and redaction.

Run a real-service smoke test only with explicit authority. Prefer disposable or read-only data,
verify mutation through an independent read, and clean up only when authorized.

Before diagnosing the service, run both:

```sh
"$RUNDESK_COMMAND" skills doctor <agent>
"$RUNDESK_COMMAND" env check <NAME>
```

`doctor` proves skill, profile, and command readiness; `env check` distinguishes missing from
unreadable values.
