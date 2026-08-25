---
id: PAA
name: Additional provider accounts, and the alias that selects one
last_verified: 2026-08-25
---

## What this is

An alias names an additional account for a provider Rundesk already supports. Omitting it uses the
provider's existing default and changes nothing. Naming one selects that account for the work being
started, with its own private provider-owned home and its own session.

## Why it exists

- One person may hold more than one account with the same provider, and work should be able to say
  which one it runs under.
- Selecting an account must not quietly change an agent's defaults, and must not fall back to
  another account when the one named is missing.
- Rundesk never handles the credential itself. Signing in, checking, and signing out stay with the
  provider's own command.

## Requirements

A ✅ names the test methods observed to pass on 2026-08-25, across `test_provider_accounts.py`,
`test_providers_turns.py`, `test_ask_command.py`, `test_delegations_hosting.py`, and
`test_providers_command.py`. A ❌ is not a claim that the behavior is absent — it is a claim that
nothing here proves it. The two unproven rows are both policy: one asserts what Rundesk never does
with a credential, and the other asserts what it deliberately does not build.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-PAA-1 | An omitted or `NULL` alias is the existing provider default and changes no environment | `test_omission_is_the_implicit_provider_default_and_makes_nothing`, `test_a_scoped_alias_has_its_own_environment_session_and_never_changes_the_default` |
| ✅ | R-PAA-2 | `default` is reserved and can never be registered or stored as an alias | `test_default_is_reserved_and_never_a_registered_alias` |
| ✅ | R-PAA-3 | Aliases represent only additional accounts for one canonical provider | `test_an_alias_is_only_a_private_empty_provider_owned_home` |
| ✅ | R-PAA-4 | Explicit provider-plus-alias delegation keeps requested and effective provenance and the same child-turn, environment, continuation, and session identity without changing agent defaults | `test_a_scoped_alias_is_immutable_provenance_without_changing_the_target_default`, `test_a_scoped_alias_has_its_own_environment_session_and_never_changes_the_default`, `test_a_replacement_gateway_receives_the_same_scoped_account_alias` |
| ✅ | R-PAA-5 | An explicit missing or unsupported alias fails without fallback | `test_a_missing_alias_never_falls_back_to_default`, `test_a_missing_explicit_alias_is_refused_before_either_delegation_write` |
| ❌ | R-PAA-6 | Login, status, and logout are provider-owned. Rundesk reports normalized state only and never reads, copies, exports, prints, backs up, or synchronizes provider credentials | not proven — the credential suites cover Rundesk's own sealed store, not the provider CLI's login. No test names this boundary |
| ✅ | R-PAA-7 | Logout and removal cannot invalidate an active turn's account boundary; durable registry, configuration, reference, delegation, and turn-admission decisions serialize on the install lock, and removal refuses configured defaults and unsettled delegations | `test_alias_removal_waits_for_configuration_validation_and_its_write` |
| ❌ | R-PAA-8 | No rotation, pooling, quota or rate-limit evasion, or credential sharing is provided | not proven — an absence of behavior, with no check that would fail if one were added |
| ✅ | R-PAA-9 | Path adapter spellings retain requested and display provenance, while alias registries, account references, and aliased session identity use the adapter's canonical path | `test_relative_and_absolute_adapter_spellings_share_one_alias_registry`, `test_a_relative_adapter_alias_resolves_and_resumes_without_rewriting_provenance` |

## Open questions

- What would make `R-PAA-6` provable. It is the strongest privacy claim in this contract and rests
  on inspection alone; a test that fails if Rundesk ever reads a provider's own credential would be
  worth more than the sentence is.
- Whether `R-PAA-8` should be a requirement at all, or belongs in the brief's refusals where an
  unprovable non-goal can sit honestly.
- The manual two-account release check remains unrun: register and sign into one alias with two
  authorized accounts, confirm the omitted account is unchanged, delegate explicitly through the
  alias, confirm requested, effective, and terminal provenance and session isolation, then sign out
  and remove the alias. Offline stand-ins and captured streams cannot prove it.
