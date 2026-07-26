# strangers/ — adapters written by somebody who has not read this code

**This directory is the evidence for R-PRV-2**, and it is the only claim in the whole seam
that cannot be proved from the inside: *an adapter Rundesk has never heard of carries a
whole turn, with nothing here changed*.

Each one was written by an agent given **only the text of
[`write-a-provider-adapter.md`](../../.knowledge/guides/write-a-provider-adapter.md)** — no
repository, no source, no tests, and no conversation with anyone who had seen them. Each is
committed **exactly as it was handed over**. Nothing here has been tidied, corrected or made
to pass; if one of them fails, the guide is what moves.

| Adapter | The brain it was written for | Written from |
|---|---|---|
| [`driftwood-adapter`](./driftwood-adapter) | a fictional conversational CLI that steers, resumes, runs tools and reports a session's running totals | the guide as of `2026-07-26` |

`brains/` holds the fake CLI each adapter's author wrote to test against, so a pair can be
driven with nothing installed:

```sh
PATH="$PWD/tests/strangers/brains:$PATH" \
  python3 tests/test_provider.py --adapter tests/strangers/driftwood-adapter
```

**Only `brains/` ever goes on that path, and never this directory.** An adapter looks its
brain up by name. Put the adapter somewhere reachable under the name it is looking for and
it finds *itself*, runs itself, and that copy does the same — which took this machine to
eight thousand processes and a load average of 641 before anybody noticed, because every
generation looks exactly like a legitimate adapter run. `_nothing_of_ours_is_on` in
`test_provider.py` now fails the case rather than the machine.

**What the first one found.** It followed the guide exactly, declared that it could be
steered, and then failed — because the conformance suite was sending it a plain-text prompt
rather than the records the guide promises a steerable adapter. The suite was wrong and the
adapter was right, which is the whole reason this directory exists. Its author's review also
found a token count being summed as nothing when a brain had never reported it, and a failed
turn with nowhere to say why. Both are fixed.
