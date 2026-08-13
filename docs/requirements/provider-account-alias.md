# Provider account aliases

Status: implemented with offline fixture evidence; manual two-account validation remains.

## Contract

- R-PAA-1: An omitted/`NULL` alias is the existing provider default and changes no environment.
- R-PAA-2: `default` is reserved and can never be registered or stored as an alias.
- R-PAA-3: Aliases represent only additional accounts for one canonical provider.
- R-PAA-4: Explicit provider-plus-alias delegation keeps requested and effective provenance and the
  same child-turn, environment, continuation, and session identity without changing agent defaults.
- R-PAA-5: An explicit missing or unsupported alias fails without fallback.
- R-PAA-6: Login, status, and logout are provider-owned. Rundesk reports normalized state only and
  never reads, copies, exports, prints, backs up, or synchronizes provider credentials.
- R-PAA-7: Account removal/logout cannot change an active turn's boundary; removal also refuses
  configured defaults and unsettled delegations.
- R-PAA-8: No rotation, pooling, quota/rate-limit evasion, or credential sharing is provided.

## Acceptance

The automated suites use executable offline stand-ins and captured provider streams. Manual release
readiness additionally requires two authorized Claude accounts: register and log into one alias,
verify the omitted account remains unchanged, delegate explicitly through the alias, confirm
requested/effective/terminal provenance and session isolation, then log out and remove the alias.
