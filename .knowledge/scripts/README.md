# scripts/ — tooling & your workspace

Code, not prose — stack-neutral, standard-library only, runs with nothing installed.

The **shipped tooling** below is versioned by `knowledge-template`: don't rewrite it per project, it updates
by version bump. Everything else you drop in here is yours.

## Contents

| Script | What it does |
|---|---|
| [`doc-lint`](./doc-lint) | Enforces the standard on `.knowledge/` — namespaces, IDs, citations, glyph tables, catalogs, research notes, and the payload's own integrity. A red lint is a broken doc. |
| [`test_doc_lint.py`](./test_doc_lint.py) | The linter's teeth-test: a valid project passes, each mutation fails on its own rule. If this fails, the linter has lost a tooth. |

### This project's

| Script | What it does |
|---|---|
| [`check-evidence`](./check-evidence) | Every ✅ in a contract names a test the suite actually declares. `doc-lint` cannot see that. |
| [`cli-reference`](./cli-reference) | Writes `CLI.md` from the parser, so the reference cannot drift from the command. `--check` fails when it has. |
| [`gate`](./gate) | Everything that has to be true before work here is finished, in one command. Finds the suites rather than listing them. |
| [`probe-claude`](./probe-claude) | Whether `--system-prompt` genuinely replaces what the Claude Code CLI was built with, which has only ever been read off a help string. Runs the append form beside it as the control, because without one "it ignored the rule" and "it ignores that kind of rule" are the same observation. |
| [`probe-codex`](./probe-codex) | What the installed Codex CLI really does, asked of it rather than assumed. Evidence for `research/`, never a test dependency — the live half reaches a real account. |
| [`probe-codex-instructions`](./probe-codex-instructions) | Where Codex reads standing instructions, and which of its two instruction fields replaces what the brain was built with. Both were established by probing, not by reading its schema, which describes neither. |
| [`probe-discord`](./probe-discord) | The canary. Prints what to do and what to watch for each channel row a fake cannot settle — a mark appearing, an indicator running, a bot showing online. It does not drive Discord: every row here is *what a person sees*, so a script reporting success would be asserting the one thing it cannot observe. |
| [`probe-grok`](./probe-grok) | The four things nobody measured about the Grok CLI: whether a resume round trip carries context, whether its usage is a turn's or a conversation's, whether `GROK_HOME` isolates a login, and whether the prompt can stay off the command line. Each settled by what happened rather than by how a reply read. |

## Usage

```
python3 .knowledge/scripts/doc-lint .knowledge     # lint this project's docs
python3 .knowledge/scripts/test_doc_lint.py        # prove the linter still works
```

Wire both into CI. A rule that matters is a check in `doc-lint`, teeth-tested beside it — prose that isn't
enforced is teaching, not law.

## Payload integrity

`../.payload-manifest` records a `sha256` for every file this project must never edit — the `docs-*.md`
standards and the two scripts above. `doc-lint` re-hashes them on every run, so a repo can **prove** it is
running the version stamped in `../.version` instead of taking it on trust. A drifted file is named in the
failure: restore it from that release, or upgrade the whole `.knowledge/` and re-stamp the version.

**Do not hand-edit the manifest.** Only the upstream release step rewrites it, after changing the payload:

```
python3 .knowledge/scripts/doc-lint --write-manifest .knowledge   # re-record the checksums (upstream only)
```

## Your scripts

This folder is also a workspace. Add project-specific helper scripts here — generators, build steps, one-off
checks, anything that helps an agent work in this repo. Keep the shipped `doc-lint` and `test_doc_lint.py`
unchanged (they're versioned); everything else here is yours to add and name.
