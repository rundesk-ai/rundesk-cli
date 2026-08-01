---
id: PRF
name: A profile worker, and what it hands back
last_verified: 2026-08-01
---

## What this is

A profile is a shared specialist definition — what the specialty is, and the rules one
execution of it follows. A named agent hands a profile one bounded task, and that task runs
as an isolated execution on the agent's behalf, without the agent's identity, memory,
history or operational rules. The named agent reviews what comes back and answers the person
who asked.

## Why it exists

- An agent can hand heavy execution to a specialist without losing what it is.
- What a worker was allowed to do, and what it ran with, is answerable a fortnight later.
- No unreviewed work reaches the person who asked for it.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-PRF-1 | A profile worker runs as an execution of the named agent that delegated it, never as a durable identity | `a profile definition is never listed as an agent`, `a profile execution is a conversation of its own` |
| ✅ | R-PRF-2 | A profile is defined by a description, a set of skills, and a posture, and nothing else | `a profile is two files and the manifest holds three fields`, `a manifest field this release does not know is refused` |
| ✅ | R-PRF-3 | A profile definition is completely validated before any run of it is admitted | `a profile that says nothing about what it is for is refused`, `a posture that is not one is refused`, `a profile with no rules has nothing to run under`, `empty rules are refused as firmly as absent ones`, `rules that reach outside the profile are refused`, `a slug that is not one path component is refused`, `a profile that stands somewhere else is not this installs`, `a directory missing either file is not listed as a profile`, `an unusable profile is refused before anything is written` |
| ✅ | R-PRF-4 | A profile run is admitted only by a turn belonging to the agent it acts for | `a run is admitted by a turn belonging to the agent it acts for`, `what the records say a run was admitted with matches its bundle`, `handing work to a profile needs a turn of this agents own`, `a gateway is handed everything it does about profile runs` |
| ✅ | R-PRF-5 | Every profile run receives a Rundesk safety floor that the profile cannot remove or widen | `a profile execution is never told the named agent core rules`, `the profile layers are the floor then the rules then the task`, `the floor says whose behalf this is on and refuses impersonation`, `no named agent identity memory or operating rules reach the worker` |
| ✅ | R-PRF-6 | A profile run receives a bounded task brief rather than the parent agent's conversation | `the brief is the prompt and the conversation is never forwarded`, `a brief longer than the ceiling is refused`, `a run with no brief at all is refused` |
| ✅ | R-PRF-7 | A profile execution stands in its target project so that project's own rules load natively | `the execution stands in the target project`, `a run with no project stands in its own locked home`, `a target that is not a directory here is refused`, `a target that is not an absolute path is refused`, `an ordinary turn stands in the agents home with its own skills` |
| ✅ | R-PRF-8 | A profile run is presented the complete configured skill set and no other skill | `the execution is presented the runs own locked skill snapshot`, `the skills are a set and are read back in sorted order`, `a profile that names no skills is refused`, `a skill named twice is refused rather than collapsed`, `a skill this machine does not have is refused` |
| ✅ | R-PRF-9 | A profile's revision is computed from what the profile is rather than maintained by its author | `reordering the skills array does not make a new revision`, `editing the rules makes a new revision`, `editing a skill the profile exposes makes a new revision`, `a script losing the bit that makes it runnable is a new revision`, `adding a skill to the set makes a new revision` |
| ✅ | R-PRF-10 | What a profile run was admitted with never changes for that run | `admitting locks the rules the manifest the brief and every skill`, `editing the shared profile afterwards leaves this run alone`, `the profile rules reach the brain exactly as they were locked`, `a profiles own rules reach the brain exactly as they were written`, `a run whose locked skills were tampered with refuses rather than runs` |
| ✅ | R-PRF-11 | A profile run stays resumable for a retention window measured from its latest activity | `the retention window is measured from the latest activity`, `a run inside its window is resumable` |
| ✅ | R-PRF-12 | Expiring a profile run takes away its execution context and keeps its durable record | `expiring takes the execution context and keeps the record`, `an expired run can no longer be carried on` |
| ✅ | R-PRF-13 | Neither a profile run nor a turn woken to review one may admit another profile run | `a profile run cannot admit another profile run`, `a turn woken to review a handoff cannot start another profile run`, `a profile run cannot hand work to another profile`, `the recursion marker is told to the brain as well as recorded`, `a profile execution is told which run it is carrying`, `an ordinary turn is told nothing about a profile` |
| ✅ | R-PRF-14 | A provider-native subagent inside a profile run never settles that run | `a child agents completion does not end the parent turn`, `a subagents own conversation is not where this turn ended`, `a run that already finished is not carried again` |
| ✅ | R-PRF-15 | A terminal profile outcome owes its named parent exactly one review | `a terminal outcome owes its parent exactly one review`, `offering the same terminal outcome twice still owes one review`, `a run that failed owes the same one review as one that worked`, `a review stops being owed only once it has been delivered`, `a review is left owing while the surface is down`, `a review the surface refused is left owing rather than lost`, `a profile handoff is left owing when the room is already busy`, `a parent is told once and the review stops being owed`, `a gateway carries every admitted profile run it finds`, `a root already in flight is never started a second time` |
| ✅ | R-PRF-16 | Rundesk records a worker's report and asserts nothing read out of it | `the handoff is the workers own words and nothing read out of them`, `the handoff reports what the brain said it cost and nothing it did not`, `a run nothing reported a cost for says so rather than reporting none` |
| ✅ | R-PRF-17 | What a profile run shows a person carries no local path | `what a profile run shows carries no local path`, `a label is short safe and never the brief`, `a listing says which revision and which skills a run used` |
| ✅ | R-PRF-18 | Installing a release never replaces a profile definition that is already there | `laying down never replaces a profile that is already there`, `laying down puts a shipped profile where it is missing`, `the shipped profiles are read off the directory`, `taking back leaves a shipped profile an owner has edited`, `taking back removes a shipped profile nobody has touched`, `taking back never touches a profile the owner wrote`, `taking back leaves no empty directory where agents are kept`, `taking back keeps the directory an owners agents stand in` |
| ✅ | R-PRF-19 | A worker's report reaches nobody until the named parent has reviewed it | `a profile handoff is never posted where a person can read it`, `a profile handoff wakes the parent to review it` |
| ❌ | R-PRF-20 | An authorized person may steer a running profile execution from where the agent is reached | — |
| ❌ | R-PRF-21 | A profile run may be shown as its named parent acting through a specialist rather than as another identity | — |

## Open questions

- Whether a profile should be grantable per agent rather than available to every named agent on the install.
- Whether a profile run should be able to resolve a provider or model of its own rather than continuing the parent turn's.
