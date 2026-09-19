+++
title = "Providers"
subtitle = "the four shipped adapters, what each declares, and the records a turn reads"
status = "draft"
intent = """
A provider exists so that Rundesk CLI can drive a coding CLI the owner already pays for without owning the
model, the context or the tools. Adding support for another CLI should mean writing one program, and a
failure should always come back as a word Rundesk CLI already knows.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Adapters", value = "claude, codex, grok, antigravity", cite = "known" },
  { label = "Commands", value = "rundesk providers, rundesk login", cite = "commands" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Record kinds", value = "8", cite = "protocol" },
  { label = "Silence before giving up", value = "30 minutes", cite = "bounds" },
  { label = "Longest turn", value = "48 hours", cite = "bounds" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "An unreadable record", value = "dropped, never raised", cite = "protocol" },
  { label = "Access mode", value = "passed to the adapter, enforced by the provider", cite = "access" },
]
+++

A provider adapter is a separate program that Rundesk CLI starts and talks to over a pipe in
newline-delimited JSON.[^known] Rundesk CLI never holds the model or the conversation; the adapter runs the
vendor's own command under the login already on the machine.[^known] `rundesk providers` lists them and shows one account, and `rundesk login` connects
one in the browser.[^commands] What an adapter is told each turn, and how one turn travels from a terminal to an answer, is
described on [asking](asking.md).

## Invocations

Each adapter answers `--capabilities` offline, and runs one turn when called with no argument.[^known] An
adapter that holds more than one account answers three more, for reading, connecting and disconnecting
one.[^login]

## Adapters

What an adapter declares decides what Rundesk CLI does with it.[^known]

| Adapter | Vendor command | Chooses a model | Takes mid-turn words |
|---|---|---|---|
| `claude` | `claude -p` | yes | yes[^claude] |
| `codex` | `codex app-server` | yes | yes[^codex] |
| `grok` | `grok agent stdio` | yes | yes[^grok] |
| `antigravity` | `agy --output-format stream-json` | no | no[^antigravity] |

The `grok` adapter's own comment says it declares no mid-turn words, and the value it returns says
otherwise; the returned value is what runs.[^grok]

## Records

An adapter speaks eight kinds of record: text, thinking, a tool it used, a result, usage, a file, a limit
it met, and done.[^protocol] A record Rundesk CLI cannot parse is dropped rather than raised, so one
malformed line never ends a turn.[^protocol] A tool is reported in one of ten words Rundesk CLI owns, never
the vendor's own name for it.[^protocol]

Failure comes back as one of twelve words, and Rundesk CLI adds only three of them itself — `cancelled`,
`timed_out` and `crashed`.[^protocol] Each word carries whether retrying is worth it and what a person should do
about it.[^protocol]

A turn carries one of two access postures, which Rundesk CLI passes to the adapter and the provider
enforces.[^access]

## Bounds

A turn ends when the adapter has said nothing for 30 minutes, and in no case runs past 48 hours.[^bounds]
Rundesk CLI tells a give-up apart from a stream it could not read.[^bounds]

## Credentials

A provider may hold more than one account, named by an alias, and `default` is reserved.[^accounts]
`rundesk login` and the account verbs run the adapter's own login attached to the owner's terminal, then
ask it again what the account is.[^login] Rundesk CLI never copies a credential out of the provider.[^login]


[^known]: `src/rundesk/providers/adapters.py` — `known()` finds the shipped adapters, `capabilities()`
    asks one offline, and `talking_to()` starts one for a turn with the agent's home as its working
    directory.
[^commands]: `src/rundesk/commands/providers.py` — `register()`;
    `src/rundesk/commands/login.py` — `register()`.
[^claude]: `src/providers/claude` — `what_this_can_do()` declares tools, resume, model, usage, steering
    and account aliases, and `main()` answers `--capabilities` and the account verbs.
[^codex]: `src/providers/codex` — `what_this_can_do()` and `main()`.
[^grok]: `src/providers/grok` — `what_this_can_do()`, whose docstring says steering is declared as a no
    while the returned mapping sets it true.
[^antigravity]: `src/providers/antigravity` — `what_this_can_do()` declares model and steering false.
[^protocol]: `src/rundesk/providers/protocol.py` — `RECORDS` names the eight kinds, `parse_record()`
    returns nothing for a line it cannot read, `DID` names the ten words for a tool, `FAILURE_CODES`
    names the twelve failures, `OBSERVED_BY_RUNDESK` names the three Rundesk CLI adds, and `is_retryable()`
    and `what_to_do_about()` answer for one.
[^access]: `src/rundesk/providers/protocol.py` — `ACCESS_MODES`;
    `src/rundesk/providers/environment.py` — `for_turn()` passes `RUNDESK_ACCESS_MODE` to the adapter.
[^accounts]: `src/rundesk/providers/accounts.py` — `RESERVED`, `alias_trouble()` and `known()`.
[^login]: `src/rundesk/providers/adapters.py` — `account_login()` and `account_logout()` run the
    adapter's own verbs attached to the terminal and then call `account_status()` again.
[^bounds]: `src/rundesk/providers/streaming.py` — `SILENCE_SECONDS` and `CEILING_SECONDS`, and
    `ENDED_BY_RUNDESK` and `COULD_NOT_BE_READ`, which separate a give-up from a read fault.