# GitHub releases

## Discover the release contract

Read applicable repository instructions, `CONTRIBUTING.md`, `RELEASING.md`, changelog, version files,
release workflows, and `.github/release.yml`. Determine the release branch, version source,
validation, artifacts, notes policy, and whether pushing a tag creates the GitHub Release. When
automation owns creation, use it; never also run `gh release create`.

Fetch the release branch and tags, then inspect existing releases:

```sh
git fetch <release-remote> <release-branch> --tags
gh release list --repo <owner/repo> --limit 20
```

Stop if the worktree is dirty, required content is not merged and pushed, validation is incomplete,
or the release branch, commit, repository, account, remote, tag owner, or automation is uncertain.

## Classify the branch before reconciling it

Determine purpose from repository instructions and deployment workflows, never the branch name
alone:

- A live website deployment branch represents code deployed to production. Its canonical
  integration branch is the repository's documented default, often `main`.
- An isolated product-version branch exists to build or support a specific release line.

For a live deployment branch, post-production reconciliation is part of release completion when the
repository contract requires it. After production verification, fetch both branches, compare the
deployed commit with the canonical branch, and return deployment-only content through the required
pull-request, review, and check path. Do not merge the canonical branch into the deployment branch
and call that reconciliation. Prove the deployed commit is reachable from the updated canonical
branch; under squash or rebase policy, instead prove no deployment-only content remains.

Do not automatically apply that back-merge rule to an isolated product-version branch. Follow its
documented merge-forward or maintenance policy.

If authority does not include the required pull request or merge, prepare the authorized artifacts
and report reconciliation as an explicit remaining delivery step.

## Choose an exact version

Inspect all changes since the last published release. Follow the repository's established version,
tag, title, and prerelease scheme. Do not replace Calendar Versioning, a product prefix, an absent
`v`, or another published convention with SemVer merely for consistency.

When no version policy or established pattern exists, use stable SemVer with a `v`-prefixed tag:

| Bump | Fallback meaning |
|---|---|
| Patch | Backward-compatible fixes, documentation corrections, or internal changes with no new public capability. |
| Minor | Backward-compatible public functionality or deprecation. |
| Major | Any incompatible API, CLI, schema, configuration, data, or behavior change. |

Reset lower components after a minor or major increment. One breaking change makes the fallback
release major. For `v0.Y.Z`, use minor for incompatible change or new capability and patch for a
compatible correction. Use `v1.0.0` only when the project deliberately declares its contract stable.

Confirm the proposed tag does not exist and resolves inside the intended release line.

## Prepare and authorize the release

Update every required version source, changelog, generated artifact, migration note, and
compatibility instruction. Run complete release validation, wait for required CI on the exact
commit, inspect the release range, and record artifact digests when required.

Before a push, tag, draft, upload, or publication, present:

- repository, account, release branch, previous release, and comparison range;
- exact version, tag, title, target commit, and compatibility rationale;
- validation, CI, release automation, notes source, artifacts, and checksums; and
- each failed check, uncertainty, recovery requirement, or remaining reconciliation step.

Authorization must cover that exact repository, version, commit, and effect.

## Tag and prepare notes

Follow the repository's annotated, signed, lightweight, or automation-owned tag contract. When no
contract exists, create an annotated tag on the recorded commit and push only that tag:

```sh
tag=<approved-tag>
release_commit=$(git rev-parse <approved-release-commit>)
git tag -a "$tag" "$release_commit" -m "$tag"
git push <release-remote> "refs/tags/$tag"
```

If automation owns the release, monitor it and continue at verification. Otherwise create a draft
from the already pushed tag:

```sh
gh release create "$tag" --repo <owner/repo> \
  --draft \
  --verify-tag \
  --generate-notes \
  --fail-on-no-commits \
  --title '<approved title>'
```

Add `--prerelease` when approved. Add `--notes-start-tag <previous-tag>` when GitHub would compare the
wrong release line. Inspect the draft and correct missing breaking changes, migrations, security
instructions, or misleading summaries through a reviewed notes file:

```sh
gh release view "$tag" --repo <owner/repo> \
  --json url,name,tagName,targetCommitish,body,isDraft,isPrerelease,assets
gh release edit "$tag" --repo <owner/repo> \
  --notes-file <reviewed-release-notes.md>
```

Attach required artifacts and checksums before publication. Never use `--clobber` without explicit
approval and proof that replacing the draft asset is recoverable.

## Publish, verify, and recover

Publish only after the tag target, draft, notes, and assets match the approved release:

```sh
gh release edit "$tag" --repo <owner/repo> \
  --draft=false \
  --verify-tag \
  --title '<approved title>'
```

Fetch the remote tag and prove it resolves to the recorded commit. Read the published release back
and verify exact tag, title, target, stable or prerelease state, non-draft state, notes, URL, and
assets.

`gh release verify` and `gh release verify-asset` verify GitHub attestations and matching asset
digests. Use them when the release has attestations; they do not by themselves prove release notes,
tag policy, deployment health, or branch reconciliation.

After a failure, inspect the remote tag, workflow runs, draft, and published release before retrying.
Never delete, move, or recreate a published tag to conceal an error. Follow repository policy for a
corrective release, or use the next patch under the fallback policy. Report success only with the
stored URL, tag, target commit, compatibility rationale, and observed verification.
