# Providers and sign-in

## providers

An omitted account alias is the provider's ordinary account and preserves previous behavior.
`default` is reserved. `login` and `logout` are interactive official provider commands; Rundesk does
not accept or display credentials. Removal and logout refuse an account used by an active turn, and
removal also refuses configured agent defaults and unsettled delegations. Login and ordinary default
changes remain available during active work; prior admission stays fixed and later turns see the
new selection. Destructive account changes serialize with durable references and turn admission.

The brains this install can run. A provider is a **program rundesk runs**, never code it loads, so
this asks about programs — where each one is, and what it says it can do. All three verbs are
offline: none runs a turn, needs an account, or reaches a network.

```console
$ rundesk providers
providers in /Users/you/.rundesk/app/src/providers and /Users/you/.rundesk/data/providers
PROVIDER     PROGRAM
a-stand-in   /Users/you/.rundesk/data/providers/a-stand-in
antigravity  /Users/you/.rundesk/app/src/providers/antigravity
claude       /Users/you/.rundesk/app/src/providers/claude
codex        /Users/you/.rundesk/app/src/providers/codex
grok         /Users/you/.rundesk/app/src/providers/grok
```

A bare name resolves among the ones that ship and then among the ones this install has been given, in
that order — a release's own adapter is what somebody gets by typing its name, and an install cannot
quietly shadow it. Anything with a separator in it is used as a path, so an adapter being written
right now needs nothing installed anywhere.

```console
$ rundesk providers check a-stand-in
a-stand-in
  program   /Users/you/.rundesk/data/providers/a-stand-in
CAN     IT SAYS
tools   yes
resume  yes
model   no
usage   yes
steer   no

it also said, and rundesk did not ask:
NAME     VALUE
version  "0.146.0"
```

**Absent means no.** An adapter that answers `{}` can do none of it, which is a complete and honest
answer rather than an error — a plain conversational CLI is a first-class brain here, not a degraded
one. Anything it reported that rundesk did not ask about is shown as it said it, because a version an
adapter volunteers is what somebody reads a month later to find out what changed under them.

```console
$ rundesk providers instructions ava --layers
LAYER           BYTES
core            510
a_person_asked  593

1105 bytes in 2 layers, 3fe0d980fc34
```

What a brain is told before it reads a word of the task, with what each layer costs. Without
`--layers` it prints the prompt itself; with `--trigger` it renders a different situation. Naming no
agent leaves the placeholders standing, which is how to read the shape of a layer on an install with
no agents in it.

The number at the end is a fingerprint of the whole. Every turn records it, so what a brain was told
is provable afterwards without a copy of it being kept — and a prompt that changed between releases
says so rather than leaving somebody to guess.

## OAuth login and the private token bridge

`rundesk login <provider>` is one verb for every provider, and rundesk knows none of them. The name
typed on the command line is looked up among the `oauth-provider.json` declarations installed
catalogs shipped, and every endpoint, scope, identity field and consent parameter comes from that
file. A catalog adds a provider by publishing a declaration; no release of rundesk changes.

### The ordinary path

Two values, then one command:

```sh
rundesk env set GOOGLE_OAUTH_CLIENT_ID          # typed, never passed as an argument
rundesk env set GOOGLE_OAUTH_CLIENT_SECRET
rundesk login google
```

The app client belongs to the owner and is placed like any other value they keep — usually while
they are still in the provider's console with it on screen, and often before the provider's catalog
is even installed. `login` uses what is already there and asks for nothing; it prompts only for a
value that is genuinely missing, and keeps what it was given under the same name. So connecting a
second account, or reconnecting after a revocation, is one command and no typing.

**What the names are is derived, not compiled in.** A declaration's provider ID becomes the name in
the spelling a shell variable takes: `google` gives `GOOGLE_OAUTH_CLIENT_ID` and
`GOOGLE_OAUTH_CLIENT_SECRET`, and `some-provider` gives `SOME_PROVIDER_OAUTH_CLIENT_ID`. No
provider name appears anywhere in rundesk. The grammar is recognised on the name alone, so a client
placed before any catalog is installed is treated as a client from the moment it lands.

**One app, many accounts.** Repeat `login` to connect another account to the same client. An account
is filed under the provider's immutable subject, so somebody who changes their address keeps one
connection rather than gaining a second. Integrations pick the account with `--email`.

### `--profile` is for a second app, and most installs never need one

`--profile <name>` selects a *different OAuth app client*, not a different account. It exists for
the uncommon case of genuinely separate apps — two cloud projects, or a personal and a work app —
and it suffixes the same names: `GOOGLE_OAUTH_CLIENT_ID__WORK` for `--profile work`. If you have
one app, do not use it. Choosing between several connected accounts is `--email`, always.

### What the browser is sent to, and what answers it

The callback is bound to `http://127.0.0.1:<ephemeral-port>/<random-path>`, and the command prints
the exact address it is listening on before it opens anything:

```console
$ rundesk login google
Listening for the sign-in callback on http://127.0.0.1:52431/8f1Qb2yv7pKcR0mN4tEwZs6uJhLxAo9d
Connected someone@example.test
```

- **`127.0.0.1`, not `localhost`.** A provider matches a registered redirect as text, and that name
  can resolve to `::1` or to whatever a `hosts` file says.
- **An ephemeral port, chosen per sign-in.** There is no fixed port to register, and none for
  something else on the machine to be holding.
- **A random path, and a random state, both checked exactly.** Every other program on the machine
  can reach a loopback port; the path plus the state is what makes a callback this flow's own.
- **Stray requests are answered and ignored.** A favicon fetch, a preconnect, or anything else that
  is not the exact path does not end the wait — only the real redirect or the overall deadline does.
- **The success page is inert**: no scripts beyond a countdown, no network references, no echo of
  the code or state, and it tells the person to return to the terminal.

When no browser can be opened, rundesk prints the authorization URL for you to follow yourself.
That URL carries this one flow's short-lived authorization mechanics — the client ID, the redirect,
the state, and the PKCE challenge — because it *is* the request you are making; they mean nothing
except to the loopback server behind them, for one flow, for at most three minutes. It never
carries the client secret, the authorization code, a refresh token, or an access token: the secret
is a field of a POST rundesk makes, and the code comes back over the loopback socket.

That fallback is not an out-of-band flow. Manual copy-and-paste of a *code* — which some providers
used to offer and have retired — is not supported. Use a provider-supported Desktop/native app
whose loopback policy permits this callback.

### Replacing an app client

```console
$ rundesk login example --replace-client
login: FAILED — replacing the example app client will discard 2 connected account grant(s); nothing
else is touched. Repeat with --confirm to be prompted for the new client, sign in with it, and
replace both together

$ rundesk login example --replace-client --confirm
EXAMPLE_OAUTH_CLIENT_ID (client ID):
EXAMPLE_OAUTH_CLIENT_SECRET (client secret):
Connected someone@example.test
```

Four guarantees, each the answer to a way a rotation goes wrong:

- **Preview first.** Without `--confirm`, nothing is prompted for and nothing is written. The count
  is read from what is really stored.
- **Only that app profile.** Grants under any other profile of the same provider are untouched.
- **Consent before replacement.** The new client is taken through a complete sign-in *first*. A
  replacement that cannot produce a reusable grant leaves the old client and every grant under it
  byte-for-byte as they were.
- **Both together or neither.** The client values and the grants live under different names and are
  written in one transaction under the install lock — a client written without its grants is an
  install whose stored refresh tokens belong to a client that is gone.

Both values are asked for, never half of them: reusing one half of the client being replaced
produces a pair that was never issued together. `--confirm` on its own is refused rather than
ignored.

### What is refused, and what to do about each

| What happened | What rundesk does |
|---|---|
| no client is placed yet | refused, naming the exact `rundesk env set` calls to make |
| consent declined, or the flow timed out | nothing is written; run `login` again |
| the browser sent back another account | nothing is written; the grant it would have overwritten is intact |
| a second terminal changed the client or the declaration mid-consent | the later write is refused; run `login` again |
| a grant was made with a client that has since been replaced | refused, naming `rundesk login <provider>` |
| the installed declaration changed since the grant was made | that app profile is refused until it is reviewed and reconnected |
| the provider says the stored grant is gone (`invalid_grant`) | reported as revoked, naming `rundesk login <provider>` |
| one installed declaration is malformed | only *that* provider is unusable; every other one still works |
| a catalog being installed carries a malformed declaration | the install itself is refused |

### The private token bridge

An integration never receives a refresh token or a client secret. What it can ask for is one
short-lived access token, for one declared capability, down a socket it made itself.

```sh
rundesk _oauth accounts <provider> [--profile <name>] --response-fd <fd>
rundesk _oauth access <provider> <capability> [--profile <name>] [--email <address>] --response-fd <fd>
```

Hidden from `rundesk --help` because it is a protocol between two programs rather than a verb
somebody types. The caller creates a `socket.socketpair()`, passes one end to the child, and
**closes its own copy of the child's end immediately after spawning** — otherwise the pair never
reaches end-of-file and the caller waits on a descriptor it is holding open itself.

The response FD must be one end of an inherited anonymous local socket: never 0, 1 or 2, and never
a pipe, a named socket or a regular file. Each frame is a four-byte unsigned big-endian length
followed by at most 65,536 bytes of compact UTF-8 JSON, and both directions have a deadline — a
peer that stops reading, or that never writes, is refused rather than allowed to hold a command
open.

```text
{"version":1,"ok":true,"accounts":["someone@example.test"]}
{"version":1,"ok":true,"access_token":"…","token_type":"Bearer","expires_at":1750000000,"email":"…","subject":"…"}
{"version":1,"ok":false,"error":"no OAuth capability 'invented' is declared"}
```

A refusal is framed as well as printed, so the caller learns why without parsing prose. `access`
asks for exactly what the account already has plus the one declared scope of the capability
requested, so one integration's consent never quietly widens another's; it reopens consent in a
browser when that scope is missing, and refuses rather than writes if a different account comes
back. A refresh token the provider rotates during an ordinary refresh is kept. Tokens never cross
stdout, stderr, `argv`, environment variables, logs, or skill files.

### What a turn is not handed

Two kinds of value are held back from every provider subprocess: the sealed grant document, and any
OAuth app client ID or secret. `RUNDESK_OAUTH_STATE` is rundesk's own and no `rundesk env` verb
touches it at all — `list` does not show it, and `check`, `set` and `unset` refuse it by name. An
app client is the owner's: they set it, list it and replace it exactly like any other value, and it
is withheld only from a turn.

The rule is matched on the name, not looked up in a catalog, so it holds before any provider skill
is installed. It is narrow: `OAUTH_CLIENT_ID` with no provider in front of it,
`GOOGLE_OAUTH_CLIENT`, `GOOGLE_OAUTH_CLIENT_IDENTITY` and `GOOGLE_ANALYTICS_CLIENT_ID` are ordinary
owner values and stay visible to a turn, because a rule that hid a value somebody set for their own
script would be a rule that silently broke it.

**On an install carried forward from before this release**, a client already stored under one of
these names *was* handed to every turn. Upgrading stops that from now on; it cannot undo what a
brain already read. An owner who ran a brain they would not trust with that client should rotate it
in the provider's console.

None of this claims to contain an agent that can already read the owner's files — a brain under
`work` access reads the sealed store like any other file. What it stops is a client secret arriving
in every turn's environment, and an ordinary command replacing or emptying every grant by name.
Protect backups: the key that opens these values is stored beside them.
