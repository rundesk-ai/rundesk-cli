---
name: publishing-github-releases
description: Cut a GitHub release under each repository's own rules — batching everything merged since the last tag into one release pull request, choosing patch, minor or major, and tagging and publishing once its approval gate clears. Use whenever a version is bumped, a release is prepared, proposed, tagged or published, when deciding what version number a batch of merged work deserves, or when the default branch is ahead of the last tag and nothing has shipped it — even if nobody says the word "release".
---

# Publishing a GitHub release

A release is the case for putting a batch of merged work on somebody's machine. The repository
owns how that is done here: read its rules before using anything below. Tagging, merging and
publishing change external state that other people consume — do only the actions the owner asked
for.

## Establish the release contract

Never assume a release convention from another repository. Confirm this one from the checkout:

```sh
gh repo view --json nameWithOwner,defaultBranchRef
git fetch --tags <base-remote>
git describe --tags --abbrev=0
git log --oneline $(git describe --tags --abbrev=0)..<base-remote>/<default-branch>
```

Read the repository's own release guide, `AGENTS.md`, `CONTRIBUTING.md`, and any documentation
directory that describes releasing. Then read `.github/workflows/` to learn what actually happens:
which workflow a tag triggers, what it validates before publishing, whether it generates notes,
and whether it refuses a mismatched tag.

Four facts decide everything that follows. Find each rather than guessing:

1. **Where the version literal lives** — a package manifest, an `__init__.py`, a `VERSION` file.
   Search for the current tag's number to find it.
2. **Whether releases go through an integration branch** or straight off the default branch.
3. **What the repository's own validation gate is** — the single command it expects green before
   a release. Run that, never a familiar toolchain substituted for it.
4. **Who clears the approval gate, and what they own after it clears.** Some repositories expect
   the author to tag and publish once approved; others reserve every step. This is the question
   most often assumed wrong. Find the answer, and if the repository does not state one, ask —
   **do not assume the author never merges, and do not assume they always may.**

**The repository's rules win** over every default below.

## A release is a batch, never one per merged PR

Issues become pull requests, pull requests merge. When the default branch is ahead of the last
tag, **one** release PR bumps the version and makes the case for the whole batch. Cutting a
release per merged PR turns a version number into a changelog entry and gives the person
approving it nothing to weigh.

A batch of one urgent fix is still a release PR.

**Check for an open release PR before cutting one.** A release folds in every unreleased batch,
not just the branch in front of you. Where one is already open, supersede it rather than shipping
two numbers for the same fix:

```sh
gh pr list --search "release in:title" --state open
```

## Choosing the number

Read every pull request merged since the last tag. **The highest impact in the batch sets the
level**, even when everything else is a fix.

| | When |
|---|---|
| **patch** `1.4.2 → 1.4.3` | Fixes only. Nothing new on any public surface — no command, flag, endpoint, config key, or persisted field. A user has nothing to learn. |
| **minor** `1.4.3 → 1.5.0` | Any backward-compatible addition: a new command or subcommand, a new flag, a new config key, a new field crossing a public boundary, a bundled resource, a changed default that an existing configuration still works under. |
| **major** `1.5.0 → 2.0.0` | Breaking: something removed or renamed, a config key whose meaning changed, persisted state an older version cannot read, an install that cannot upgrade in place. Rare. Never propose one inside a routine release — raise it separately. |

Between patch and minor, take the minor. A user finding an undocumented new flag in a patch is
worse than a number that moved further than it had to.

If the repository does not use semantic versioning, follow its scheme and ignore this table.

## The release PR is the version

The person approving signs off on **a version, not a diff**. They already reviewed the individual
changes; the release PR is the single page that says *this is vX.Y.Z, and here is why it is
reaching your machine*. Title it the way the repository titles releases — `chore(release):
prepare vX.Y.Z` where it uses Conventional Commits.

**Where the work lives.** Where the repository uses an integration branch, pull requests for that
version target the release branch and the release PR is `release/vX.Y.Z` → default branch, so its
diff is the whole release. A bump-only PR cut straight off the default branch is **not** the
release PR: it shows a one-line version change, says nothing, and strands whatever was still
targeting the release branch. Before opening or merging, ask what else is aimed at the version:

```sh
gh pr list --base release/vX.Y.Z
```

Anything open there is part of the release or has to be explicitly dropped.

The body is the deliverable. **One screen — around 25 lines, one line per pull request, no
sub-bullets, no mechanics.** They are deciding whether to ship, not reviewing the diff again:

```md
## Summary
v1.5.0 — <one line: what somebody gets by upgrading>

## Why now
- <the problem the batch solves, in the user's terms>
- <two or three bullets, no more>

## What it carries
- #153 — an answer lands under the message that asked, not at the end of the channel
- #144 — `show` and `edit` verbs; a record can be read back and changed in place
- <one line each: the outcome, never the diff>

## Level
Minor — #144 adds two verbs to the public surface. Nothing persisted changed, so an existing
install upgrades with nothing to do.
<or: name the migration, and what happens to an install that skips it>

## Validation
- ✅ <the repository's own gate command> on <sha>
- ✅ CI proves a fresh install and an upgrade from <previous version>
- ✅ Every issue in the batch closed by its own PR
```

**No closing keywords on a release PR.** The issues were closed by the pull requests that fixed
them; a `Closes` here claims work this PR did not do, and on a repository that squashes it will
close issues twice over. A bare `#153` is a reference rather than a promise, and this is the one
place it is the right form.

## The sequence

Not to be varied.

1. **Confirm the batch is complete.** Where an integration branch is used, `gh pr list --base
   release/vX.Y.Z` must be empty. Confirm each merged pull request actually closed its issue — an
   issue still open reads as a fix that was never made:

   ```sh
   "$RUNDESK_SKILLS/publishing-github-releases/scripts/issues-closed-by.py" --stale
   ```

2. **Bump the version literal** on the branch the release PR comes from.
3. **Run the repository's validation gate** on the bumped tree — green *before* the PR exists.
4. **Open the release PR**, post the link, and say in one sentence which version and why. Then
   stop at the approval gate the repository defines.
5. **Re-read the conversation before acting on approval.** A message sent mid-turn is not in that
   turn's context, and a release built on a stale view ships without something that was asked for.
6. **Tag the merge commit and push it**, once the gate has cleared and the repository's rules put
   this step with you:

   ```sh
   git tag v1.5.0 <merge-sha> && git push <base-remote> v1.5.0
   ```

7. **Verify the publish.** A green workflow is not proof: read the published release and confirm
   it names every pull request in the batch, and that the artifact it produced is actually
   installable — download or install it rather than trusting the run's exit status.
8. **Finish the rollout the repository defines** — an upgrade of a live install, a service
   restart, a store submission. It is not shipped until that is verified, not merely queued.

## Gotchas

- **The tag must match the code.** A release workflow commonly refuses a tag whose number is not
  the version literal, so the bump has to land on the default branch first — you cannot tag now
  and bump after. Confirm which way this repository's workflow reads it.
- **A stacked pull request closes nothing.** GitHub honors a closing keyword only when the base is
  the default branch, however the body is worded. A PR targeting a release branch leaves its issue
  open on merge; retarget once the parent lands, then re-check with the script in step 1.
- **Steps 5–8 are what gets abandoned.** The run ends at "released" while the tag is unpublished
  or the live install is still on the old version. Not shipped is not shipped.
- **"Please merge" needs the specific pull request confirmed.** Before acting on an approval,
  check the PR you are about to merge is the release PR and that nothing else targets its branch.
  Merging the wrong one ships a version without the work queued behind it.
- **A blocker found in the batch does not delay the version — it leaves that PR behind.** Say
  which one you are dropping and why, and let the owner decide, rather than holding a good release
  for one bad change or shipping the bad change to keep the batch whole.
- **A stale base hides in `git log`.** `git log <base-remote>/<base>..HEAD` lists only what the
  branch adds. Read `HEAD..<base-remote>/<base>` as well, or a sibling release that landed first
  becomes a conflicted PR and a wrong version bump.
