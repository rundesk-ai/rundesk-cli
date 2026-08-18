# OAuth login

Use `"$RUNDESK_COMMAND" login --help` as authoritative. Provider-specific app creation, API
enablement, consent-screen scopes, and resource permissions live in the installed provider skill,
never here.

## The ordinary path

```sh
"$RUNDESK_COMMAND" env set <PROVIDER>_OAUTH_CLIENT_ID
"$RUNDESK_COMMAND" env set <PROVIDER>_OAUTH_CLIENT_SECRET
"$RUNDESK_COMMAND" login <provider>
```

The app client is the owner's value, placed with `env set` like any other and typed rather than
passed as an argument. `<PROVIDER>` is the declared provider ID as a shell variable, so `google`
gives `GOOGLE_OAUTH_CLIENT_ID`. Placing it first is normal, including before the provider's catalog
is installed; `login` then asks for nothing. It prompts only for a value that is genuinely missing.

Repeat `login` to connect more accounts to the same app. An account is filed under its immutable
subject, so a changed address is the same connection. Integrations select the account with
`--email`; a missing declared capability scope may reopen consent for that same account.

Never ask anyone for a refresh token, and never put a client secret in a skill, in argv, or in
output.

## Profiles are for a second app, and are rarely needed

`--profile <name>` selects a different OAuth *app client*, not a different account, and suffixes the
same names (`GOOGLE_OAUTH_CLIENT_ID__WORK`). One app with several connected accounts is the normal
shape — use `--email` to choose between them. Reach for `--profile` only when there are genuinely
two apps.

## Replacing an app client

```sh
"$RUNDESK_COMMAND" login <provider> --replace-client
"$RUNDESK_COMMAND" login <provider> --replace-client --confirm
```

Without `--confirm` this only previews: it counts the grants that would be discarded, prompts for
nothing, and changes nothing. With it, the new client signs in first and only then replaces the old
client and its grants together — a replacement that cannot sign in leaves everything as it was.
Only the named profile is touched. `--confirm` without `--replace-client` is refused.

## What the browser does

`login` prints the exact loopback address it is listening on, then opens a browser. The callback is
`http://127.0.0.1:<ephemeral-port>/<random-path>`: the literal address rather than `localhost`, a
port chosen per sign-in, and a path and state checked exactly. Stray local requests are answered and
ignored until the real redirect arrives or the deadline passes. The success page tells the person to
return to the terminal.

With no browser to open, the authorization URL is printed to follow by hand. It carries that flow's
short-lived state and PKCE challenge — that is the request — and never a client secret,
authorization code, refresh token, or access token. Manual copy-and-paste of a *code* is not
supported.

## When it refuses

Retry declined, timed-out, wrong-account, and concurrent-consent failures; none of them writes a
grant. A missing client is refused by name, saying exactly which values to set. A changed
declaration is refused until reviewed and reconnected. A revoked grant is reported as such and names
the login command that fixes it. One malformed installed declaration disables only its own provider.

Grants are sealed under a name no `rundesk env` verb reads or writes. App client values are ordinary
owner values, visible in `env list` as a hint, but withheld from what a turn is handed. Backups
include the local key beside them and need protection.
