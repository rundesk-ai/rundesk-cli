# Reusable workflow scripts

Read this before shipping a reusable script. It owns the generic command contract; also read
[External-service integrations](integrations.md) for credentials, profiles, OAuth, network access,
or remote effects.

## Make the script earn its place

Script repeated work whose inputs, outputs, and failures can be specified. Keep judgment in
`SKILL.md`; put parsing, transformation, validation, and mechanical orchestration here so the same
input produces the same output without re-deriving the mechanism. Do not duplicate an ordinary tool
that already performs the operation safely.

## Define the contract

Document when to run the command, arguments, input formats, exit meanings, side effects, and bounded
output. Put executable entry points directly under `scripts/`; imported modules may use
subdirectories.

- Define the semantic unit: record, keyed entity, relationship, ordered sequence, field
  distribution, or whole file. Aggregates can stay equal while important relationships change;
  preserve needed identity and correlation or narrow the promised outcome.
- Accept explicit paths or standard input. Do not assume a working directory, remembered checkout,
  or owner-specific path. Validate every input before writing and reject an unsupported input with
  a recovery action.
- Reject the same resolved input more than once when inputs represent independent runs, votes, or
  evidence; repetition can manufacture stability or distort a ratio.
- Default to read-only. Refuse an existing destination unless replacement is explicit. Stage a
  replacement in the destination directory, rename it into place, and remove only temporary files
  created by this invocation.
- Make repeat behavior explicit: read-only commands are safe to repeat; writing commands are
  idempotent or refuse duplicates without damaging prior output.
- Return `0` only for the completed documented result. Return nonzero with a concise stderr reason
  for invalid input, partial output, or incompletion. Empty input or a no-op is success only when it
  genuinely completes the promised outcome.
- Bound every data-dependent section: headers, labels and paths, identifiers, samples, omitted-item
  metadata, JSON arrays, warnings, and errors—not only the main list. Give an explicit limit and
  omitted count where useful.

Rundesk installs no dependencies for a skill. Prefer the standard library. If another program is
required, check for it before work and name its supported installation route; never download or
execute a dependency implicitly.

## Preserve authority and failure state

Automation adds no permission. Preserve preview and confirmation boundaries, accept exact targets,
and stop before destructive or external work the user did not authorize. Never embed credentials,
private paths, repository identities, environment dumps, or user-controlled shell evaluation.

Pass argument arrays to child processes, set deadlines, preserve exit status, and bound captured
output. Stage multi-step work before one commit point when possible; otherwise report exactly what
completed and remains, never partial success as complete.

## Test the contract

Use synthetic fixtures and temporary directories in the owning catalog or project test area. Use a
skill-local `tests/` only when no owner exists. Cover:

- representative valid input and exact promised output;
- empty input, malformed input, unsupported input, missing and unreadable files;
- duplicate resolved inputs, repeat behavior, and idempotency or duplicate refusal;
- existing or unwritable destinations, interrupted writes, and invocation-owned cleanup;
- large input, long paths or identifiers, many inputs and metadata values, and complete bounded
  output; and
- child failure, timeout, and partial output when subprocesses are used.

Add an adversarial oracle for meaning, not only implementation mutations. For record comparison,
for example, preserve each field's values and counts while swapping which values share a record; a
record-equivalence claim must detect the change. Mutation checks cannot repair a wrong oracle.

Run every entry point directly and from outside the skill. Confirm the executable bit, stdout,
stderr, exit status, filesystem effects, cleanup, and preservation of pre-existing files.
