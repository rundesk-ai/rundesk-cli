---
id: AGT
name: An agent, and the home it loads from
last_verified: 2026-07-26
---

## What this is

An agent is a named identity rundesk runs work for, and its home is the directory holding the rules,
memory, workspace and skills it loads. Two agents are separate in what each discovers, how each is
configured, what each remembers, and where each works by default — but not by the operating system, so a
provider's own tools still reach whatever their owner reaches.

## Why it exists

- An owner runs several agents on one machine without one of them finding another's rules or history.
- What an owner writes for an agent outlives updating and removing rundesk itself.
- An agent that cannot do work says why before a provider is ever started.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-AGT-1 | Every agent has a name that is its own on a machine | `an agent is named by the one who made it`, `two agents never stand in one place` |
| ✅ | R-AGT-2 | An agent has a home holding the knowledge it loads | `an agent is made with the files it loads`, `what an agent loads holds nothing rundesk keeps`, `what a home holds is what there is a template for`, `a template is copied with the agents own name in it`, `the file every provider loads names the ones none of them do`, `what an agent loads is reached by being told rather than by a link`, `an agent is only one that has a home` |
| ✅ | R-AGT-3 | An agent's home outlives the copy of rundesk that created it | `removing rundesk keeps every agents home`, `purging takes every agents home as well` |
| ✅ | R-AGT-4 | Creating an agent that already exists leaves the knowledge edited in its home unchanged | `making an agent again leaves what was written in it`, `making an agent again puts back only what is missing`, `making an agent that exists leaves its home alone`, `making an agent again leaves the records it already had` |
| ✅ | R-AGT-5 | A name that would reach outside where agents are kept is refused | `a name that is a path is refused`, `a name that is no name at all is refused`, `a name standing on a link out of where agents are kept is refused`, `a name that cannot be an agents is refused before anything is made` |
| ✅ | R-AGT-6 | A name a gateway would take for something it wrote is refused | `a name a gateway would take for something it wrote is refused`, `a name that merely has a dot in it is still a name`, `what a gateway writes is asked of it rather than listed` |
| ✅ | R-AGT-7 | No two agents resolve to one workspace | `no two agents resolve to one workspace`, `two agents never stand in one place` |
| ✅ | R-AGT-8 | No two agents share the private home a provider is given | `no two agents share the private home a provider is given`, `one agent keeps two providers apart`, `the private home a provider is given stands outside what the agent loads` |
| ✅ | R-AGT-9 | An agent the machine keeps running resolves the home the command that made it resolved | `the job carries the directories it was given rather than its own`, `a verb asks where the agent it names keeps things`, `where an agent keeps things is its own`, `nothing is adopted while a gateway of that name is running`, `what a stopped gateway wrote is adopted once it lets the name go` |
| ❌ | R-AGT-10 | An agent loads what stands in its own home rather than what its owner keeps | src/rundesk/turn.py — codex was asked, standing there, a question only the scaffolded AGENTS.md answers, and answered it with no tools; a case needs a real provider and a credential, which the suite has neither of |
| ✅ | R-AGT-11 | An agent is diagnosed without a provider being started | `an agent that has everything is diagnosed with nothing`, `an agent missing what it loads says which file`, `an agent that was never made is said to be missing`, `an agent that cannot be written to says so`, `an install that does not fit stands between an agent and a turn`, `an install with nothing to make an agent from says so`, `an agent with nothing wrong is ready`, `an agent with something wrong says what and fails`, `diagnosing with no name asks after every agent`, `diagnosing where there are no agents says so`, `asking after an agent that is not there says so` |
| ✅ | R-AGT-12 | Diagnosing an agent changes nothing about it | `diagnosing an agent changes nothing about it`, `diagnosing an agent that is not there changes nothing`, `diagnosing an agent never builds the records it reads` |
| ✅ | R-AGT-13 | A name that has no agent is reached where it always was | `a name with no agent keeps things where it always did`, `a name with no agent is asked after where it always was` |
| ✅ | R-AGT-15 | A turn stands in the agent's own home, so what stands there is what a brain reaches | `a turn stands where its own agents rules stand` |
| ✅ | R-AGT-17 | Rundesk's own words reach every turn, and what an owner says is added to them rather than replacing them | `the agents own name is filled in`, `every place the name appears is filled in`, `rundesks own words reach a turn that was told nothing else`, `what an owner says is added to rundesks rather than replacing it`, `rundesks own words come first`, `what rundesk says is the same words every turn`, `a turn is told how to find what it did` |
| ✅ | R-AGT-18 | An agent is not made without a brain, and one that has none is not ready | `an agent with no brain is not ready`, `what is wrong says how to put it right`, `an agent with a brain is not complained about`, `making an agent with no brain is refused`, `making an agent that exists leaves its home alone` |
| ✅ | R-AGT-16 | What a turn is told about its situation is the nearest thing that said anything, apart from R-AGT-34, and the order is one place | `what a turn was told itself wins`, `the agents own is next`, `rundesks own line is last`, `nothing anywhere is nothing rather than a guess`, `what an agent is told is kept and read back`, `taking what an agent is told off leaves nothing behind`, `a channel that says nothing falls to what the agent says`, `what this channel says still wins`, `a schedule that says nothing still gets what the agent says`, `a channel that says nothing falls to what the agent says`, `what this channel says still wins over the agents` |
| ✅ | R-AGT-14 | Every place an agent resolves is readable without opening the source | `one agent says every place it resolves` |
| ✅ | R-AGT-19 | Everything a diagnosis complains about says what to type to put it right | `what is wrong says how to put it right`, `every complaint says what to type next` |
| ✅ | R-AGT-20 | A diagnosis says where an agent's records stand against what this install expects | `records behind what this install expects are reported with the way out` |
| ✅ | R-AGT-21 | An agent whose gateway is running code no longer installed is told so | `a gateway running code that is no longer installed is reported`, `a gateway on the installed version is nothing to report`, `a gateway that is not running is not asked what version it is` |
| ✅ | R-AGT-22 | A new agent takes each page from its owner's template where there is one, and the install's otherwise | `a home made with no overrides is what the install ships`, `one overridden page is the owners and the rest are shipped`, `an override directory that is empty changes nothing`, `an override directory that cannot be read is not a half made agent` |
| ✅ | R-AGT-23 | A template an owner wrote survives an update | `an update replaces the shipped templates and leaves every override`, `what an owner wrote is not under anything a release ships` |
| ✅ | R-AGT-24 | An owner may add a page the install does not ship, and agents made earlier are not faulted for lacking it | `a page the install does not ship reaches a new agent`, `an agent made before a page was added is not reported as missing it` |
| ✅ | R-AGT-25 | A template that never names the agent still makes a working one | `an override that never names the agent still makes a working agent` |
| ✅ | R-AGT-26 | A diagnosis says, for each page, whether it came from the install or the owner and from where | `a diagnosis says which pages are the owners and where from` |
| ✅ | R-AGT-27 | A skill written once into the library can be given to any agent | `a directory with no skill file is not a skill`, `a library that is not there is an owner who has made none`, `every skill is named by the directory it stands in`, `a name the brains would refuse is refused here`, `a skill that says nothing about when to use it is refused`, `a skill naming itself something else is refused`, `a description past the limit is refused`, `a skill with no frontmatter at all is refused`, `a skill that is all of those things is one` |
| ✅ | R-AGT-28 | An agent loads the skills it was given and no others | `an agent is given a skill by it standing in its own directory`, `a grant is a link so editing the library reaches every agent`, `a grant survives the agent directory being moved`, `granting a skill nobody has says so`, `granting something no brain would index is refused`, `granting twice leaves one grant`, `one agents skills are never anothers` |
| ✅ | R-AGT-29 | Giving a skill and taking one away change only what rundesk placed | `revoking takes the grant and leaves the skill`, `revoking what was never granted says so`, `revoking will not remove a directory somebody wrote by hand`, `revoking will not follow a link out of the library`, `granting over something rundesk did not place is refused` |
| ✅ | R-AGT-30 | A skill this release ships is brought to the version installed, and one an owner wrote is never touched | `what a release ships is read off the directory`, `installing lays the built ins down`, `installing again leaves what is already there`, `updating brings a built in forward`, `updating never touches a skill an owner wrote`, `a library that cannot be written to does not break the install` |
| ✅ | R-AGT-31 | An existing agent can change its default brain without being recreated | `changing an existing agents brain clears the old brains defaults`, `model and settings can be changed without changing provider`, `an empty settings object clears existing settings`, `a new provider can receive replacement model and settings atomically`, `a running turn keeps its brain and the next uses the new default`, `changing a brain preserves everything the agent already owns` |
| ✅ | R-AGT-32 | An invalid new default brain configuration leaves the agent unchanged | `an unrunnable new brain changes nothing`, `malformed settings change nothing` |
| ✅ | R-AGT-33 | Defaults specific to the previous brain do not silently reach the new one | `changing an existing agents brain clears the old brains defaults` |
| ✅ | R-AGT-34 | What rundesk says about a turn the clock started reaches it whatever an owner wrote, and an owner's words are added to it | `what rundesk says about a scheduled turn is there whatever the owner wrote`, `what an owner says about a scheduled turn is added to rundesks own`, `a schedule told what to do is still told nobody is watching` |
| ✅ | R-AGT-35 | A built-in a release renames is taken out of the library, and an agent holding it holds the new name instead | `every rename names a skill this release ships`, `a renamed built in is taken out of the library`, `a grant of a renamed built in becomes a grant of the new name`, `a rename never hands the new skill to an agent without the old`, `a skill the owner wrote under the old name is never retired`, `nothing is carried until the new name is in the library`, `uninstalling takes a renamed built in too` |

## Open questions

- Which of an agent's files each provider is proven to *load*, rather than merely to find. Probes of the
  build this replaces found that only the two named after a provider are picked up where they stand, that
  one of them expands an import and none follows a link, and that a bare skills directory is discovered by
  nobody. None of it is re-proven against the versions installed now, which is what R-AGT-10 waits on.
  One half of it is now settled and is R-AGT-15: a turn stands in the agent's home, beside the files
  scaffolded for it. Until this phase it stood one directory *below* them, so an agent asked who it was
  answered, truthfully, that there was nothing there to tell it — the scaffolding was written, and out of
  reach of the only thing meant to read it. What R-AGT-10 still waits on is the other half, and it is two
  questions rather than one: whether a provider standing there actually loads what stands beside it, and
  what it makes of the owner's own files, which are still reachable because `HOME` is deliberately still
  the owner's (see the sign-in question below). Neither is rundesk's behaviour to assert.
- Whether agents share the owner's provider sign-in or each holds its own. Redirecting a provider's home
  isolated its credentials too in that build, so two agents needed two sign-ins — a cost worth stating
  before it is chosen rather than discovered.
- Whether what a run recorded belongs with the agent or with the gateway that admitted it.
- Where rundesk's own account of itself stands, now that everything else belongs to an agent.
