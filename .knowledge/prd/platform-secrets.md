---
id: SEC
name: The values every program is given
last_verified: 2026-08-02
---

## What this is

One set of named values this install keeps, handed to every program rundesk starts. A value
is either held here in a file only its owner can read, or fetched by a command rundesk runs
again each time a program starts. Nothing rundesk shows ever gives a whole value back.

## Why it exists

- Every integration command and every brain an agent reaches finds the credential it needs,
  with nobody having exported anything in a shell a gateway will never see.
- A credential is placed once for the whole install, replaced in one command, and told apart
  from another without anybody reading either.
- Nothing rundesk itself shows gives a value back — not a listing, not a record, not a log —
  and no copy of this install carries one.

**Where that stops, said plainly.** R-SEC-1 gives every value to every program rundesk
starts, which is the whole point of the feature, so an agent whose turn runs under them can
print one and its transcript stands under the data directory. What this is for is placing a
credential without it passing through the process table or a shell history, telling one from
another without reading either, replacing it in one command, and keeping every one of them
out of what a backup carries. It is not confidentiality against an agent that has been given
one.

## Requirements

|  | ID | Requirement | Evidence |
|:--:|---|---|---|
| ✅ | R-SEC-1 | Every program rundesk starts is given every value this install keeps (R-PROC-1) | `every program is given every value this install keeps`, `a brain and every command it runs is given them`, `every adapter is given the values this install keeps` |
| ✅ | R-SEC-2 | The values are the install's, resolved from where it keeps them rather than from any agent | `every kept value is produced`, `its own variable says where things are kept` |
| ✅ | R-SEC-3 | A value is either held by this install or fetched by a command rundesk runs | `a held value is kept where nothing else can read it`, `the command is kept and what it printed is not` |
| ✅ | R-SEC-4 | What this install records about a value never holds the value | `what is kept holds no value` |
| ✅ | R-SEC-5 | A value is identified by a masked hint of it rather than by the value | `a hint shows the end of a long value and none of a short one` |
| ✅ | R-SEC-6 | Two names holding one value carry one mark, and two holding different values do not | `two names holding one value share a mark`, `two names holding different values do not` |
| ✅ | R-SEC-7 | A mark taken by one install says nothing about the same value on another | `a mark from one install does not match another`, `this installs own key is made once and kept to its owner` |
| ✅ | R-SEC-8 | A value being kept is never an argument to the command that keeps it | `a value given as an argument is refused`, `no option on the command takes a value` |
| ✅ | R-SEC-9 | A value is taken from a terminal that does not echo it, or from what is piped in | `a value is taken from a pipe`, `a value is typed without being echoed` |
| ✅ | R-SEC-10 | A value nobody is there to supply is refused rather than waited for | `a value nobody can supply is a refusal rather than a wait` |
| ✅ | R-SEC-11 | A name rundesk itself decides for the programs it starts is refused | `every name rundesk decides for a program is refused` |
| ✅ | R-SEC-12 | A name that would change what code a program loads or runs is refused | `a name that changes which code a program loads is refused` |
| ✅ | R-SEC-13 | A name that could reach outside where values are kept is refused | `a name that could reach outside where values are kept is refused`, `taking a value away cannot be made to unlink anything else` |
| ✅ | R-SEC-14 | A value rundesk was not allowed to keep is left out of what a program is given | `a value rundesk was not allowed to keep is left out`, `what a gateway already decided survives a value claiming its name` |
| ✅ | R-SEC-15 | A command that gives nothing back leaves nothing kept under that name | `a command that gives nothing back keeps nothing` |
| ✅ | R-SEC-16 | A value that cannot be produced when a program starts is left out rather than emptied | `a value that cannot be fetched is left out rather than emptied`, `a held value whose file went missing is said rather than passed over` |
| ✅ | R-SEC-17 | A command that could not answer is told apart from one that answered that there is no value | `a command that will not answer is not a command that said no`, `a command that is not there is a definite answer`, `what a keeper said went wrong never reaches the gateways own log` |
| ✅ | R-SEC-18 | Replacing a kept value says which value was replaced | `replacing a value says which one it replaced` |
| ✅ | R-SEC-19 | Keeping the value already held under a name leaves what is recorded about it unchanged | `keeping the value already there changes nothing` |
| ✅ | R-SEC-20 | Taking a value away removes both the value and what was recorded about it | `taking a value away names the one that went`, `what is recorded never outlives the value it names` |
| ✅ | R-SEC-21 | Asking about a name nothing is kept under is refused rather than answered | `asking about a name nothing is kept under is refused` |
| ✅ | R-SEC-22 | An owner can ask whether each kept value can still be produced, without one being shown | `every kept value can be proved reachable without being shown`, `a check that could not reach one ends unsuccessfully` |
| ✅ | R-SEC-23 | Listing what is kept produces no value, and asking after one runs no other one's command | `a listing fetches nothing`, `checking one value runs only that ones command` |
| ✅ | R-SEC-24 | What is kept is readable only by the owner of this install | `a held value is kept where nothing else can read it` |
| ✅ | R-SEC-25 | What is kept is never written into the job the machine keeps a gateway running from | `no kept value reaches the job the machine holds` |
| ✅ | R-SEC-26 | What is kept stands outside everything a copy of this install holds | `what is kept stands outside everything a copy of this install holds`, `the default stands outside the installs own data` |
| ✅ | R-SEC-27 | What is kept and cannot be read is refused rather than read as nothing being kept | `what is kept and cannot be read is said rather than taken as nothing` |
| ✅ | R-SEC-28 | What is kept cannot grow past what a program can be started with | `what is kept cannot grow past what a program can be started with` |
| ✅ | R-SEC-29 | A value a caller already has its own answer for is left out of what it is given | `what the caller already has an answer for is left out`, `a surface is never given the value it reads its own credential from` |
| ✅ | R-SEC-30 | Producing the values never runs a fetching command on the loop a gateway is carrying work on | `the same answer is given off the event loop` |
| ✅ | R-SEC-31 | Where values are kept stands where an integration command already looks for its own | `it stands where every integration command already looks`, `a relative configuration home is ignored rather than resolved`, `where values are kept is printed and nothing else` |

| ✅ | R-SEC-32 | A turn keeps a value only under a name plainly shaped like a credential — a guard on the ordinary path, not a boundary | `a turn keeps only what is plainly a credential`, `what a turn may never place is refused however it is named` |

## Open questions

- Whether an owner may run a program under these values from their own terminal, given that
  such a program can print one back.
- Which name endings count as plainly a credential, and whether an owner may extend that set.
- Whether the length of a kept value may be shown beside its hint.
- Whether a change to what every program is given belongs in the account of every agent, of
  the one it was made from, or of none.
- How often a value fetched by a command is produced, when many programs start at once.
