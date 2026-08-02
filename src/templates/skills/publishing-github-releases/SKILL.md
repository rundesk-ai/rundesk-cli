---
name: publishing-github-releases
description: Cut a GitHub release under each repository's own rules. Use when a version is bumped, tagged or published, when deciding what version number merged work deserves, or when the default branch is ahead of the last tag — even if nobody says the word "release".
---

# Publishing a GitHub release

Tagging and publishing change state other people consume. Do only the actions the owner asked for.

## Establish the release contract

```sh
git fetch --tags <base-remote>
git describe --tags --abbrev=0
git log --oneline $(git describe --tags --abbrev=0)..<base-remote>/<default-branch>
```

Read the repository's release guide, `AGENTS.md`, `CONTRIBUTING.md`, and `.github/workflows/` for
what a tag actually triggers. Four answers decide everything below — find each, never assume it
from another repository:

1. **Where the version literal lives.** Search for the current tag's number.
2. **Whether releases go through an integration branch**, or straight off the default branch.
3. **What the repository's own validation gate is** — the one command it expects green. Run that,
   not a familiar toolchain in its place.
4. **Who clears the approval gate, and what they own after it clears.** The most commonly assumed
   wrong. Some repositories expect the author to tag and publish once approved; others reserve
   every step. If it says nothing, ask — do not assume either way.

**The repository's rules win** over every default here.

## One release, one batch

When the default branch is ahead of the last tag, **one** release PR bumps the version and makes
the case for the whole batch. Per-merged-PR releases turn a version into a changelog entry and
give the approver nothing to weigh. A batch of one urgent fix is still a release PR.

A release folds in *every* unreleased batch, not just the branch in front of you. Check for one
already open and supersede it rather than shipping two numbers for the same fix.

## Choosing the number

The **highest impact in the batch** sets the level, even when everything else is a fix.

| | |
|---|---|
| **patch** | Fixes only. Nothing new on any public surface — no command, flag, endpoint, config key, or persisted field. A user has nothing to learn. |
| **minor** | Any backward-compatible addition, including a changed default an existing configuration still works under. |
| **major** | Something removed or renamed, a config key whose meaning changed, or state an older version cannot read. Never propose one inside a routine release. |

**Between patch and minor, take the minor.** An undocumented new flag in a patch is worse than a
number that moved further than it had to. If the repository does not use semver, follow its scheme.

## The release PR

The approver signs off on **a version, not a diff** — they already reviewed the changes. So: one
screen, one line per pull request, each naming the outcome rather than the diff, plus which level
and why. Nothing else.

**No closing keyword on a release PR.** The issues were closed by the PRs that fixed them; `Closes`
here claims work this PR did not do. A bare `#153` is the right form, and this is the one place it
is.

Where an integration branch is used, the release PR is that branch → default, so its diff is the
whole release. A bump-only PR cut off the default branch is **not** the release PR — it shows a
one-line version change and strands whatever still targets the release branch:

```sh
gh pr list --base <release-branch>     # must be empty before you open or merge
```

## Gotchas

- **The tag must match the code.** A release workflow commonly refuses a tag whose number is not
  the version literal, so the bump lands on the default branch *first* — you cannot tag now and
  bump after.
- **A stacked PR closes nothing.** GitHub honors a closing keyword only when the base is the
  default branch, however the body is worded, so a PR targeting a release branch leaves its issue
  open. Retarget once the parent lands, then sweep the batch — an issue still open reads as a fix
  never made:

  ```sh
  "$RUNDESK_SKILLS/publishing-github-releases/scripts/issues-closed-by.py" --stale
  ```

- **A green publish workflow is not proof.** Read the published release, confirm it names every PR
  in the batch, and install the artifact rather than trusting the run's exit status.
- **What gets abandoned is everything after the tag.** The rollout the repository defines — a live
  upgrade, a restart, a store submission — is part of shipping. Not verified is not shipped.
- **Re-read the conversation before acting on an approval**, and confirm *which* PR it approved. A
  message sent mid-turn is not in that turn's context, and merging the wrong one ships a version
  without the work queued behind it.
- **A blocker in the batch leaves that PR behind — it does not delay the version.** Say which one
  you are dropping and let the owner decide.
- **A stale base hides in `git log`.** `<base-remote>/<base>..HEAD` lists only what the branch
  adds; read `HEAD..<base-remote>/<base>` too, or a sibling release that landed first becomes a
  conflicted PR and a wrong bump.
