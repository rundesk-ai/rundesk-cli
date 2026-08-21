# Reusable workflow scripts

Read this when repeated agent work needs a deterministic local command and no external service,
credential, or remote side effect. Read [External-service integrations](integrations.md) instead
when the command crosses a service boundary.

## Make the script earn its place

Write a script for a repeated operation whose inputs, outputs, and failure states can be specified.
Keep judgment in `SKILL.md`; keep parsing, transformation, validation, and mechanical orchestration
in the script. The useful split is that the agent decides *whether and why* to run it, while the same
input produces the same output without the agent rewriting the mechanism.

Keep one-off project automation in the project. Keep a command in an agent's established scripts
area when only that agent owns and uses it. Ship it inside a skill when future turns need the skill's
routing, procedure, or assets to invoke it correctly. Do not add a script for a command an ordinary
tool already performs safely and clearly.

## Define a small command contract

State in the skill exactly when to run the command, its arguments, input formats, exit meanings,
side effects, and bounded output. Put executable entry points directly under `scripts/`; imported
modules may use subdirectories.

- Accept explicit paths or standard input. Do not depend on the caller's working directory, a
  remembered checkout, or an owner-specific absolute path.
- Validate all inputs before writing. Reject an unsupported input with a concise recovery action
  instead of guessing its format.
- Default to read-only behavior. When output files are required, refuse an existing destination
  unless replacement is an explicit documented option.
- Write a replacement through a temporary file in the destination directory, then rename it into
  place. Remove only temporary files created by this invocation when it fails.
- Make repeat behavior explicit. A read-only command should be safe to repeat; a writing command
  must be idempotent or must refuse a duplicate without corrupting prior output.
- Return `0` only for the documented completed result. Return non-zero on invalid input, partial
  output, or an incomplete operation, and send the concise reason to stderr.
- Keep successful output bounded and useful to the next agent decision. Summarize large results and
  offer an explicit limit rather than dumping an unbounded file or JSON document into context.

Rundesk installs no dependencies for a skill. Prefer the language's standard library. If a required
program is justified, check for it before work begins and name the supported installation route;
never download or execute a dependency implicitly.

## Separate orchestration from hidden authority

A workflow script may sequence ordinary local commands, but it does not gain permission from being
automated. Preserve preview and confirmation boundaries, pass exact targets as arguments, and stop
before a destructive or external action the user did not authorize. Never embed credentials,
private paths, repository identities, or environment dumps in examples, fixtures, or errors.

Avoid shell evaluation of user-controlled text. Pass argument arrays to child processes, set a
deadline where a child can block, preserve its exit status, and bound captured output. If several
steps can partially complete, either stage them before a single commit point or report exactly what
completed and what remains; never label partial output as success.

## Test the command contract

Automate the cases that define the interface. Use synthetic fixtures and a temporary directory so a
test cannot depend on or alter the working directory. Put tests in the owning catalog or project's
established test area; use the skill's own `tests/` only when no such harness exists. At minimum
cover:

- representative valid input and the exact promised output;
- empty input, malformed input, an unsupported input type, and a missing file;
- an unreadable input or unwritable destination when the platform can represent it reliably;
- an existing destination, interrupted write, and cleanup of invocation-owned temporary files;
- repeat the command and confirm the documented idempotent result or duplicate refusal;
- a large representative input that proves bounded output and the configured limit; and
- child-process failure, timeout, and partial output when the script orchestrates other commands.

Run every entry point directly, confirm it is executable, and test from a working directory outside
the skill so relative-path assumptions fail visibly. Inspect stdout, stderr, exit status, filesystem
effects, and preservation of pre-existing files. Then have a fresh agent use the skill from a
realistic request without naming the script; proof includes correct routing and invocation, not only
a green unit test.
