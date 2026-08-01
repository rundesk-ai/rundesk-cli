---
name: writing-rundesk-pull-requests
description: Apply Rundesk-specific proof, requirement, issue-closing, and identity rules to rundesk-ai/rundesk-cli pull requests. Use with writing-github-pull-requests for any Rundesk PR creation, update, summary, or review.
---

# Writing a pull request against Rundesk

Read and follow `writing-github-pull-requests` for repository discovery, branch and diff review,
fresh validation, evidence-rich writing, GitHub issue links, creation, and verification. This
page contains only the additions for **`rundesk-ai/rundesk-cli`**.

## Carry Rundesk's proof

Rundesk agents inherit live `RUNDESK_*` paths. A bare checkout command can therefore read or
change the owner's active install. Before validation, follow the current agent's governing
isolation instructions and inspect every inherited variable beginning `RUNDESK_`.

Run the gate only with those live variables absent, `PYTHONPYCACHEPREFIX` in scratch, and a
repository-compatible interpreter (the checkout's `.venv` when present):

```sh
<isolated environment> <repository python> .knowledge/scripts/gate
```

Perform the real install/uninstall check only after proving that install, bin, data, backup,
agent, run, log, job, and skill-library paths all sit below one disposable scratch root and the
launchd job prefix cannot collide with a live install. Use the feature checkout's own
`install.sh`; a station wrapper may resolve a different checkout. Check launchd registrations
before and after. If any boundary is unknown, report the check blocked rather than running it.
Cite the exact commands and fresh results in **Validation**, including anything blocked or
skipped.

New guaranteed behavior has a ratified `.knowledge/prd/` requirement and a regression test that
cites its `R-<AREA>-<n>`. Documentation remains true in the same change, and
`python3 .knowledge/scripts/doc-lint .knowledge` passes.

## Close what the change completes

Use one closing line per completed issue:

```md
Closes #12.
Closes #13.
```

Before merge, verify what GitHub will act on:

```sh
gh pr view <number> --repo rundesk-ai/rundesk-cli \
  --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
```

An empty result on a PR that fixes an issue is a delivery defect. Closing keywords do not attach
when the PR targets a non-default branch; recheck after every base change.

## Identify the agent, not its tools

End the PR body with exactly one identity footer:

```md
🤖 by <Agent>
```

Use the agent's display name. Remove provider, model, tool, session, and generated-by branding
from the title and body. If existing commits, trailers, or the branch contain tool branding,
report it and obtain authorization before rewriting history or renaming a published branch.
The case rests on the evidence; the agent footer supplies operational accountability.
