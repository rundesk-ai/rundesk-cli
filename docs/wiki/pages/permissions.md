+++
title = "Permissions"
subtitle = "the macOS grants an agent needs, the silent tests for each, and whose grants they are"
status = "draft"
intent = """
Permissions exist so that an owner can see which macOS grants an agent actually has before a task fails
for want of one, and can be told where to give a missing grant. Asking should never raise a consent
dialog, and a grant that cannot be tested should never be reported as present.
"""

[[infobox]]
group = "Identity"
rows = [
  { label = "Commands", value = "rundesk permissions list, lineage, check", cite = "commands" },
  { label = "Groups", value = "control, screen, files, shell", cite = "groups" },
]

[[infobox]]
group = "Values"
rows = [
  { label = "Answers", value = "ready, blocked, unasked, closed, absent, unrunnable, unproven", cite = "verdicts" },
]

[[infobox]]
group = "Rules"
rows = [
  { label = "Asking", value = "never raises a consent dialog", cite = "nodialog" },
  { label = "A grant with no silent test", value = "answered unproven, never ready", cite = "nodialog" },
  { label = "A gateway's grants", value = "its own, never the terminal's", cite = "lineage" },
]
+++

macOS decides what an [agent](agents.md) may reach — the screen, the keyboard, the owner's files — and
grants it separately to every application. `rundesk permissions check` tests each one and says what to do
about a missing grant.[^commands]

## Groups

Grants fall into four groups, and each is tested one at a time rather than assumed from its
neighbor.[^groups]

| Group | Tests |
|---|---|
| control | driving other applications, posting and watching keystrokes[^groups] |
| screen | taking a screenshot, and the grant to capture in this process[^groups] |
| files | the Desktop, Documents and Downloads folders, full disk access, and other applications' data[^groups] |
| shell | whether software installs without a password[^groups] |

Two screen answers can honestly disagree, because taking a screenshot uses a tool with a grant of its own
while capturing inside this process needs the grant given to Rundesk CLI.[^groups]

## Asking

**Nothing here raises a consent dialog.**[^nodialog] Only tests that answer silently are used; where macOS offers no
silent way to ask, the answer is that the grant could not be proved rather than that it is
missing.[^nodialog]

Each test runs as a separate process, even where an answer could be had in this one, because a test macOS
decides to block waits on a dialog that cannot be interrupted.[^child] A file test reports whether it was
macOS or the file's own permissions that refused, which are different problems with different
fixes.[^child]

An answer is one of seven words, and a blocked grant comes with the System Settings pane that
fixes it.[^verdicts]

## Whose grants

**A gateway holds its own grants, not the terminal's.**[^lineage] The same program run from a terminal inherits that
terminal's grants; started by macOS at boot it is answerable for itself and starts with none — which is
why a task that worked by hand can fail once the agent runs it.[^lineage]

Rundesk CLI reads which of the two it is from the system rather than guessing, and keeps *unknown* and
*cannot tell* apart instead of folding either into an answer.[^lineage] Only a run from a terminal can be
asked to grant something.[^lineage]

[^commands]: `src/rundesk/commands/permissions.py` — `register()` declares `list`, `lineage` and `check`.
[^groups]: `src/rundesk/capabilities/proving.py` — `GROUPS` names the four, `_control()`, `_screen()`,
    `_files()` and `_shell()` build each one's probes, `every()` gathers them and raises when it finds
    none, and `_screen()`'s comment explains why a capture and the in-process grant can disagree.
[^nodialog]: `src/rundesk/capabilities/proving.py` — the module docstring states only silent tests are
    used and that the answer is `UNPROVEN` where no silent query exists.
[^child]: `src/rundesk/capabilities/proving.py` — the module docstring states every probe runs as a child
    process because a blocked read waits on a dialog that cannot be interrupted, and `A_LISTING` reports
    the error number so `REFUSED_BY_TCC` and `REFUSED_BY_THE_FILESYSTEM` stay apart.
[^verdicts]: `src/rundesk/capabilities/proving.py` — `READY`, `BLOCKED`, `UNASKED`, `CLOSED`, `ABSENT`,
    `UNRUNNABLE` and `UNPROVEN`, and `PANE`, which names the System Settings pane for a fix.
[^lineage]: `src/rundesk/capabilities/lineage.py` — `read()` asks the platform which process is
    answerable, `GATEWAY`, `TERMINAL`, `REMOTE`, `UNKNOWN` and `CANNOT_TELL` are the five answers with the
    last two never folded, `CAN_BE_ASKED` names the only one that may be asked to grant something, and the
    module docstring records that a gateway under macOS holds nothing the terminal held.
