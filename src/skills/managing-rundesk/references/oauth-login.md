# OAuth login

Use `"$RUNDESK_COMMAND" login --help` as authoritative. Provider-specific app creation, consent,
API, and scope instructions live in the installed provider skill.

```sh
"$RUNDESK_COMMAND" login <provider>
"$RUNDESK_COMMAND" login <provider> --profile work
```

A profile selects an OAuth app/client configuration, never a signed-in account. First use prompts
for the client ID and, when required, a no-echo secret. Never pass either in argv or store it in a
skill. Repeat login to add accounts. Integrations select an account with `--email` and the app with
`--profile`; a missing declared capability scope may reopen consent.

Unknown providers require an installed declaration. Retry declined, timed-out, wrong-account, or
concurrent consent failures. A changed declaration is refused until reviewed and reconnected. OAuth
state is sealed and excluded from provider turns, but backups include its local key and need
protection.
