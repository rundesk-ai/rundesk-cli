# Cutting a release

What the `publishing-github-releases` skill asks each repository to tell it, answered for this one.
Read that skill for the process — batching, choosing the level, what the release PR must say. Read
this for the four facts it cannot know, and for what has already gone wrong here.

## The four answers

**Where the version literal lives.** `__version__` in `src/rundesk/__init__.py`. Nothing else
carries a number; `rundesk version` reports that one.

**Releases go through an integration branch.** `release/vX.Y.Z` is where the work for a version
collects: pull requests for that version target the release branch, not `main`. The release PR is
then `release/vX.Y.Z` → `main`, and its diff is the whole release.

**The validation gate is one command**, and it must be green on the bumped tree before the release
PR exists:

```sh
python3 .knowledge/scripts/gate
```

**Who clears the approval gate.** The owner. The release PR is his gate and he merges it — nothing
is tagged before that. Once its checks pass and he has merged, the rest is the agent's: tagging,
pushing, publication, the live update, the restart, and independent verification, without asking
him to perform or reconfirm a step. Release PRs are **not** limited to one per day.

## What the tag must match

`.github/workflows/release.yml` refuses a tag whose number is not `__version__` — it runs
`updater.tag_matches(tag, __version__)` and fails the release with an error naming both. So the
bump lands on `main` first; you cannot tag now and bump after.

## After it publishes

The run is not finished when the release page appears. Queue the live self-update and the gateway
restart, and verify: `rundesk update --check` says UP TO DATE, and every gateway is back online.
A queued `rundesk update` waits for every active turn on every agent, so it is queued and read
back on a later turn rather than polled inside this one.

Before tagging, re-read the conversation — `rundesk messages winston --conversation <id>`. A
message sent mid-turn is not in that turn's context.

## What has gone wrong here

Three releases, three different failures. Each one is why a rule above is worded the way it is.

- **A bump-only PR split the batch.** On 2026-07-29 a version bump cut straight off `main` was
  merged while `#164` was still targeting `release/v0.19.0`. The batch shipped in two pieces and
  the owner never saw one view of what was going out. Run `gh pr list --base release/vX.Y.Z` and
  confirm it is empty before opening the release PR.
- **v0.18.5 was tagged and then abandoned.** The live install sat two hours on the old version
  because the run ended at "released". Publication is not the last step.
- **v0.19.0 shipped without the work queued behind it**, because "please merge" was read as the
  wrong pull request. Before acting on an approval, confirm the PR is `release/vX.Y.Z` → `main`
  and that nothing else targets that branch.

## An issue a merged PR left open

GitHub links an issue only when the base is the default branch, so a PR that targeted
`release/vX.Y.Z` closes nothing on merge however its body is worded. Retarget to `main` once the
parent lands, then check the whole batch with the command the skill ships:

```sh
"$RUNDESK_SKILLS/publishing-github-releases/scripts/issues-closed-by.py" --stale
```

An issue still open reads to the owner as a fix that was never made.
