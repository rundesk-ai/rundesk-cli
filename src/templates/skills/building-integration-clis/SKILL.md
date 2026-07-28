---
name: building-integration-clis
description: Build and install custom CLI integrations that Rundesk agents invoke through the shared script library. Use when someone asks to create, add, package, improve, or debug an agent-accessible script, API wrapper, service integration, or command-line tool.
---

# Building integration CLIs

An integration is an ordinary executable in the directory printed by:

```sh
rundesk scripts --where
```

Every agent receives that directory first on `PATH` and as `RUNDESK_SCRIPTS`. A companion
skill teaches an agent when and how to use the command; it is not a second implementation.

## Check first

Run `command -v <name>` and `rundesk scripts` before building. Extend an existing command
when it already owns the service or data source.

## Shape

Keep one command name at the script-library root. Put support code beside it under a
directory named `<command>.d/`:

```text
scripts/
├── example
└── example.d/
    ├── example.py
    └── test-example.py
```

Make `example` a small executable launcher using paths relative to its own resolved
location. Do not depend on the agent's current working directory.

Prefer the standard library. If a dependency is unavoidable, keep it inside the
integration's support directory and provide one installation command that places it
there; never install into the machine's Python.

## Command contract

- Provide a credential-free `--help`.
- Provide `profiles` or `status` when the service has accounts or credentials.
- Keep list and search operations bounded by default.
- Print compact text for agent context; reserve `--json` for explicit structured output.
- Write errors to stderr and exit non-zero when the requested work did not happen.
- Make mutations dry-run by default and require `--confirm` for the exact action.
- Reject overwrites, broad deletes, and ambiguous account or project selection.
- Add offline tests with synthetic fixtures. Tests never reach the live service.

## Credentials and configuration

Rundesk deliberately gives programs a small environment, so an integration must not rely
on variables exported in the owner's interactive shell reaching an agent.

Use this order:

1. Explicit process environment, when present.
2. A command-specific credential file under
   `${XDG_CONFIG_HOME:-$HOME/.config}/<command>/env`.
3. The macOS Keychain when the service or organization already uses it.

Keep credential values outside the script library and skills library because Rundesk
backs up everything under its data directory. Accept a named environment-file override
such as `<COMMAND>_ENV_FILE` when development or an existing workspace keeps credentials
elsewhere.

Require the credential file to be owner-readable only and warn when group or other
permission bits are present. Commit only variable names and synthetic examples. Never
print tokens, authorization headers, cookies, or raw configuration.

## Companion skill

Create a separate skill in the directory printed by `rundesk skills --where`. The skill
contains:

- the situations that should trigger it;
- the stable command names and safest defaults;
- profile or project routing rules;
- mutation and confirmation boundaries;
- provider-specific gotchas that an agent could not infer.

Keep setup, credentials, implementation detail, and copied `--help` output out of the
skill. Grant it with:

```sh
rundesk skills grant <agent> <skill>
```

## Validation

Run the offline suite, then invoke the installed command from a directory outside its
source tree. For a live check, use only the smallest read-only `status`, `profiles`, or
bounded listing command. Never confirm a mutation as a smoke test.

Run `rundesk scripts` last and verify the command is listed under the name used by its
companion skill.
