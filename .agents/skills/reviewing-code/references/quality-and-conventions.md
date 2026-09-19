# Conventions, maintainability, and the bar for reporting

The failure this pass exists to prevent is not a missed defect. It is a report nobody acts on,
because the reader has to sort three real problems out of twenty preferences. A review's authority
comes from every finding in it having been worth the reader's time; spend that once and the next
report is skimmed.

## The repository's own rules are the conventions

A convention is something the repository states — in `AGENTS.md`, a contributing guide, a style
configuration, a linter's committed settings, or a rule the code follows without exception. Nothing
else is a convention, however widely it is held elsewhere.

Aspects of design are almost never pure style: they rest on principles, and are weighed on those.
But a point of style that the repository has not settled is preference, and preference is not a
finding.

For a convention finding, give three things:

1. the rule, quoted or cited where it is stated;
2. the code that departs from it; and
3. the form that follows it.

A finding missing the first is an invented convention. Do not report it, and do not report a rule
whose only source is the change under review — a change cannot ratify its own standard.

Where the repository states nothing and the code is genuinely unclear, the finding is the
unclarity — what a reader cannot work out and what it costs — not the convention you would have
picked.

## Every finding must be worth fixing

There is no perfect code; there is only better code. A change that improves the health of the system
should not be held for polish. Ask of each finding: would an experienced engineer on this repository
agree this is worth changing right now? If the honest answer is that it is not worth a round trip,
it is not a finding.

This is a bar, not a licence to skim. Being selective about what to report and being thorough about
what to read are different commitments, and the second one is not negotiable.

## Do not report

- Style the repository has not codified, including whitespace, ordering, and layout.
- A rename, unless the current name misleads a reader about what the value holds.
- A comment on code that already reads clearly.
- Import, member, or property ordering.
- "Consider X instead of Y" where both are fine.
- A performance concern with no measurement and no reachable cost.
- Work for later: a TODO, a nice-to-have, or a refactor the change did not touch.
- A pre-existing problem the change did not introduce and does not block. Mention it separately if it
  matters; do not charge it to this change.

Where something is close to the line, the tie-break is the reader: a report of three findings that
all need acting on is worth more than one of twenty that need triaging.

## Be exhaustive the first time

Read the whole scope, apply one standard across it, and finish it. A second pass over unchanged code
should turn up nothing new — if it would, the first pass was sampling, and the report should have
said so.

Two habits break this, and both look like diligence:

- Reviewing the easy files closely and the large ones quickly. State what you sampled instead.
- Holding findings back as "next time". There is no next time; the change merges.

## Where naming, size, and structure become findings

*Too complex* means it cannot be understood quickly by the people who will read it. That is the
threshold for all three of these, and it is about the reader, not a metric:

- **Naming** is a finding where the name hides what the value holds, contradicts what it does, or
  breaks a stated rule — not where a different name would also have worked.
- **Length** is a finding where a reader cannot hold the unit's behavior at once, or where one unit
  now has two reasons to change. A line count is not the finding.
- **Structure** is a finding where following the behavior requires opening files in an order nobody
  could guess.

Each still needs the cost stated. "This function is long" is not a finding; "the retry and the
mapping now change for different reasons in the same function, and the last two corrections each
touched the wrong half" is.

## Zero findings is a result

A pass that finds nothing worth fixing reports that plainly, and names what it read. It does not
manufacture a finding to look diligent. Say what was reviewed, say nothing material was found, and
name any area the review could not cover — that last part is what makes the empty report checkable.
