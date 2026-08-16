---
id: CAP
name: What this machine lets rundesk do
status: draft
owner: Rundesk product owner
last_updated: 2026-08-08
---

# Machine permissions product contract

## Problem and evidence

An agent that owns the Mac it runs on can only do what macOS lets its process do. Nothing in rundesk
has ever asked, so the first anybody learns that a gateway cannot take a screenshot or drive a
browser is a task that fails weeks later, in the middle of something else, with nobody watching.

**This is the first page here written for the current build.** Everything else in this directory is
the predecessor's contract, carried across; see [README.md](README.md). It is written the same way so
the two read alike, and it is separated only by being true of code that exists.

Evidence is [`research/2026-08-08-what-this-mac-lets-a-process-do.md`](../research/2026-08-08-what-this-mac-lets-a-process-do.md),
which was measured against a real machine using a throwaway launchd job — the only harness that can
produce a *denied* answer on a developer's own Mac. The command is described in
[`permissions.md`](../permissions.md).

## Outcome and success

Somebody can ask what this machine currently permits, get an answer that says which process it is
about, and be handed the exact thing to do about each refusal. Nothing about asking changes the
machine, and nothing that could not be settled is reported as settled.

Success is accepted through the scenarios below. Two rows ship unmet and say what kind of proof is
missing, which is the more useful half.

## Requirements

| | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-CAP-1 | Every answer says which process lineage it is a fact about | `the lineage line is on stdout and comes first`, `every proof carries its lineage` |
| ✅ | R-CAP-2 | Nothing is proved when the lineage cannot be read | `nothing is proved when nobody can say whose grants it would be` |
| ✅ | R-CAP-3 | A lineage read whole that matched nothing is not a lineage nobody could read | `a chain read whole that matched nothing is unknown`, `a chain that could not be read cannot tell`, `no two lineages are the same word` |
| ✅ | R-CAP-4 | A probe that could not be answered is never reported as one that was | `a program that never started is unrunnable and never blocked`, `no two verdicts are the same word`, `a probe that could not be settled also fails` |
| ✅ | R-CAP-5 | A capture is proved by reading the picture back, never by the exit code | `a capture that wrote something unreadable is unproven`, `a capture of the wrong size is unproven`, `a capture that wrote nothing is unproven` |
| ✅ | R-CAP-6 | A missing application, a closed one and a denial are three answers with three fixes | `no two verdicts are the same word` |
| ✅ | R-CAP-7 | Being refused Accessibility and being refused Apple Events are two findings with two fixes | `apple events denied and accessibility denied are two fixes` |
| ✅ | R-CAP-8 | Every blocked verdict names one thing to type, and identical fixes are said once | `one pane is named once however many probes want it`, `fixes come in the order they are first needed` |
| ✅ | R-CAP-9 | No probe opens a window, types, moves a file, or leaves anything behind | `every probe says what it touches`, `the picture is never left behind` |
| ✅ | R-CAP-10 | The command exits non-zero when anything asked for is not ready, including what could not be settled | `anything not ready exits non zero`, `a probe that could not be settled also fails` |
| ✅ | R-CAP-11 | What the last check found is kept and shown with when and in which lineage it was found, and nothing reads it to decide whether it may act | `what was found is written down with its lineage`, `a stored answer from another lineage is marked`, `a partial check leaves every other answer alone` |
| ✅ | R-CAP-12 | A probe never run is absent from what is kept, never a verdict | `a probe never run is absent rather than unproven`, `the bare verb reads it back without running anything` |
| ✅ | R-CAP-13 | A group or probe nobody has is a refusal naming what there is, never an empty pass | `a name nobody has is refused with the list` |
| ✅ | R-CAP-14 | A gateway answer names the client the owner will find in the pane, never the agent | `it is named for the interpreter and never for the agent`, `the interpreter being a bundle does not make it a terminal` |
| ✅ | R-CAP-16 | Driving the machine is four grants and each is answered separately | `the four control grants are four findings`, `accessibility without post events is blocked on posting` |
| ✅ | R-CAP-18 | A probe with no non-prompting way to ask answers unproven and never raises a dialog | `the bare verb runs nothing at all`, `listing runs nothing and says what each probe touches` |
| ✅ | R-CAP-19 | Needed and not-needed are told apart, and the exit code reflects only what was asked for | `a bare check leaves out what is not needed`, `everything includes it`, `needed and not needed are told apart` |
| ✅ | R-CAP-21 | Asking whether something is permitted never grants it | `an ungranted capture is never attempted`, `a granted capture is attempted` |
| ❌ | R-CAP-15 | A grant this machine has never been asked for is told apart from one it refused | Designed as *a timeout in a lineage where a dialog can appear*, which is an inference and not a measurement. Settling it needs `tccutil reset` against a real client, which destroys a grant the owner gave. See research §8.4. |
| ❌ | R-CAP-17 | Every scriptable application is its own grant, and the targets are discovered from the machine | The `apps` group is not built. Apple Events is confirmed per (client, target) and 26 scriptable applications were counted on the reference machine, but the classification rests on an error string that could not be measured without raising a consent dialog. See research §7 and §8.1. |
| ❌ | R-CAP-20 | Every provider this install can run is asked whether its brain is installed and reachable | The `brains` group is not built. It needs a `--check` invocation on the provider adapter contract, mirroring the one channel adapters already have — a protocol change across four shipped programs. Deferred deliberately rather than guessed at from inside `capabilities`, which may not hold provider knowledge. |

## Open questions

- **Rundesk has no name of its own in a privacy pane.** The client is the interpreter, shared with
  every other script that runs it, and a `brew upgrade` of that interpreter revokes every grant
  silently. Documented as a hazard, named in every fix line, and detected by the command. Fixing it
  needs the named thing to be what python runs *as*, which is a build step this project does not
  have.
- **Nothing re-checks on its own.** No probe at gateway start, no notice when a grant disappears.
  Adding one is cheap and needs none of this.
- **There is no reliable way to ask on a gateway's behalf, and the documented one was wrong.**
  Measured on 2026-08-15: `"$RUNDESK_COMMAND" permissions check files/downloads`, run through a
  brain's tool call inside a live turn, answered `unknown (…/codex)` and `ready` — the tool starts
  what it runs in a way that leaves the gateway shim out of the parent chain, so the probe measured
  the brain's own program and the stored verdict is not about the launchd interpreter a gateway
  runs as. `permissions.md` and `commands.md` said to ask this way and no longer do; the command now
  says unprompted that a stored answer proved outside a gateway is not about one. What is still
  missing is a way to *cause* a probe inside the gateway's own process — the honest surface would be
  a probe the gateway runs itself, which is the open question above.
- **Whether the shell-out attribution that applies to `screencapture` also applies to `osascript`.**
  If it does, an `apps` group would be measuring `osascript`'s grants rather than rundesk's. This is
  why R-CAP-17 is unmet rather than approximated. See research §8.11.
