# strangers/ — adapters written by somebody who has not read this code

**This directory is the evidence for R-PRV-2 and R-CAD-2**, and it is the only claim in
either seam that cannot be proved from the inside: *an adapter Rundesk has never heard of
carries a whole turn — or a whole conversation — with nothing here changed*.

Each one was written by an agent given **only the text of the guide it was told to follow**
— no repository, no source, no tests, and no conversation with anyone who had seen them.
Each is committed **exactly as it was handed over**. Nothing here has been tidied, corrected
or made to pass; if one of them fails, the guide is what moves.

| Adapter | Written against | What it was written for | From the guide as of |
|---|---|---|---|
| [`driftwood-adapter`](./driftwood-adapter) | [`the-contract.md`](../../docs/extending/provider-adapters/references/the-contract.md) | a fictional conversational CLI that steers, resumes, runs tools and reports a session's running totals | `2026-07-26` |
| [`semaphore-channel`](./semaphore-channel) | [`the-contract.md`](../../docs/extending/channel-adapters/references/the-contract.md) | a fictional chat platform with three markers, no typing indicator and no way to edit a message | `2026-07-25` |

`brains/` and `platforms/` hold the fake command each adapter's author was told about, so a
pair can be driven with nothing installed:

```sh
PATH="$PWD/tests/strangers/brains:$PATH" \
  python3 tests/test_provider.py --adapter tests/strangers/driftwood-adapter

SEMAPHORE_TOKEN=anything PATH="$PWD/tests/strangers/platforms:$PATH" \
  python3 tests/test_channel.py --adapter tests/strangers/semaphore-channel -- --station 1180
```

**Only `brains/` and `platforms/` ever go on that path, and never this directory.** An
adapter looks its brain or its platform up by name. Put the adapter somewhere reachable
under the name it is looking for and it finds *itself*, runs itself, and that copy does the
same — which took this machine to eight thousand processes and a load average of 641 before
anybody noticed, because every generation looks exactly like a legitimate adapter run.
`_nothing_of_ours_is_on` in `test_provider.py` now fails the case rather than the machine.

**What the first one found.** It followed the guide exactly, declared that it could be
steered, and then failed — because the conformance suite was sending it a plain-text prompt
rather than the records the guide promises a steerable adapter. The suite was wrong and the
adapter was right, which is the whole reason this directory exists. Its author's review also
found a token count being summed as nothing when a brain had never reported it, and a failed
turn with nowhere to say why. Both are fixed.

**What the second one found**, in [`semaphore-channel.NOTES.md`](./semaphore-channel.NOTES.md)
— all in the guide rather than in the code, which is what a specification being wrong looks
like:

- **The order of the last two records was contradictory.** The example showed the answer
  before the turn was marked finished; the prose said finished meant the answer was on its
  way. Both cannot be true, and it decides whether an adapter posts anything at all.
- **Nothing said which variables exist while a channel is being checked**, though the check
  is exactly where a credential has to be found and the file it falls back to lives in a
  directory the environment names.
- **Everything an adapter is *told* was specified by one example block**, while everything it
  *reports* had a table. The direction with more kinds in it had less written about it.
- **How the check is invoked was ambiguous** — the author read it three times and accepted
  both spellings — and the exit code for a refusal was never given.
- **The record has no file form for a credential**, though the guide requires a file to be
  the fallback.
