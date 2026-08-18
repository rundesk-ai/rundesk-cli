# Google login

Use `"$RUNDESK_COMMAND" login --help` and `"$RUNDESK_COMMAND" login google --help` as the
authoritative surface. A **profile** selects one Google OAuth app/client configuration. A signed-in
Google **account** is identified by its verified email for people and immutable Google `sub` in
storage.

## Configure the app

In a dedicated Google Cloud project, enable only the Google APIs required: Analytics, Search
Console, and/or Merchant. Configure the Google Auth Platform consent screen and audience; add every
intended account as a test user while the app is in Testing. Declare `openid`, `email`, and only the
needed API scopes. Testing grants can expire, and broader production use may require verification.

Create an OAuth client with application type **Desktop app**. Do not use Web application or the
removed copy/paste flow. Desktop clients support Rundesk's temporary
`http://127.0.0.1:<random-port>/<random-path>` loopback redirect without a fixed console callback.

Have the owner enter both values locally; never ask for them in chat or put them in arguments:

```sh
"$RUNDESK_COMMAND" env set GOOGLE_OAUTH_CLIENT_ID
"$RUNDESK_COMMAND" env set GOOGLE_OAUTH_CLIENT_SECRET
"$RUNDESK_COMMAND" login google
```

For another OAuth app profile, use the normalized environment suffix and forward its human name:

```sh
"$RUNDESK_COMMAND" env set GOOGLE_OAUTH_CLIENT_ID__WORK
"$RUNDESK_COMMAND" env set GOOGLE_OAUTH_CLIENT_SECRET__WORK
"$RUNDESK_COMMAND" login google --profile work
```

## Accounts, scopes, and recovery

Repeat login and choose another Google account to add another verified email under the same app
profile. Integrations select the app with `--profile` and the account with `--email`. One connected
account is selected automatically; several require `--email`. When Analytics, Search Console, or
Merchant first needs a missing scope, Rundesk reopens consent for that same immutable account.
PageSpeed remains API-key based. If two consent windows extend the same account concurrently, the
first completed grant wins; retry the integration request that reports a concurrent grant change.

If consent is declined or times out, retry. If access was revoked, the client rotated, Google
returned no refresh token, or scope extension failed, repeat the exact login command and choose the
intended account. Reauthorization replaces only that account under that app profile.

Rundesk seals the client configuration, verified identity metadata, scopes, and refresh tokens.
Neither client credentials nor grants enter provider-turn environments. Refresh tokens are never
printed or placed in arguments, environment variables, logs, or skill files; integrations receive
only short-lived access tokens through Rundesk's private anonymous-socket protocol. Protect backups:
they contain both sealed values and the key capable of opening them.
