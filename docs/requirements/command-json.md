---
id: JSON
name: The machine-readable answer three listings give
last_verified: 2026-09-03
---

## What this is

`status`, `agents [list]` and `skills [list [<agent>]]` accept `--json` and answer with one JSON
document carrying `schema_version`, read off the same command and domain paths the tables read. Without
the flag every one of them prints exactly what it always printed.

## Why it exists

- A local interface or a script that drives Rundesk should not have to parse a table written for a
  person, and should be able to tell a shape change from a wording change.
- The states the tables keep apart — a record that is not there, one that cannot be read, a
  description nobody wrote — have to stay apart in the document, or a consumer reads one as another.

## Requirements

A ✅ names test methods observed to pass on 2026-09-03 on `/usr/bin/python3` (3.9.6) and Python
3.14.6, in `test_cli.py`, `test_agents_command.py` and `test_skills_command.py`. A ❌ is not a claim
that the behavior is absent — it is a claim that nothing here proves it.

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-JSON-1 | `status --json`, `agents [list] --json` and `skills [list [<agent>]] --json` each print exactly one JSON document on one line, carrying `schema_version: 1`, and nothing else on stdout; without the flag the human-readable output is unchanged. | `test_json_is_one_versioned_document_for_a_local_consumer`, `test_json_is_one_versioned_document_when_there_are_no_agents`, `test_json_is_one_versioned_document_when_there_are_no_skills` |
| ✅ | R-JSON-2 | An agent's document keeps its configuration typed and its absences distinct: provider name and alias, a description that is unavailable, not described, empty or available, a delegation scope of any, none or an allow list, and a record that is readable, not found or unreadable. | `test_json_keeps_configuration_typed_for_a_local_consumer`, `test_json_keeps_none_any_and_unavailable_records_distinct` |
| ✅ | R-JSON-3 | A skills document names each skill's catalog and the agents holding it; one agent's document names each grant's catalog, alias, required values and the same standing verdict the human listing reads from `doctor`. | `test_json_lists_the_library_and_its_grants_without_table_parsing`, `test_json_lists_one_agents_grant_and_standing` |
| ❌ | R-JSON-4 | A listing that fails still exits non-zero with its reason on stderr and prints no JSON on stdout. | not proven by a test — observed once by hand against an unsafe root, which exited 1 with nothing on stdout. A case that drives each of the three with `--json` against a root that cannot be read would settle it. |

## Open questions

- Whether `schema_version` should move to `2` for an additive key. It does not today: a consumer
  reading a document keeps working when a key is added, and the number is for a shape that changed.
- Which other listings should answer in JSON. `gateways`, `channels` and `schedules` print tables a
  local interface would want the same way; none does yet.
