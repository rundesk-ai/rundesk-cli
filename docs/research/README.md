# Research

**What was found out, kept where it can be read after the thing that taught it is gone.**

This is not part of the product's documentation. [`docs/`](../) describes rundesk as it is, and a page
appears there when the thing it describes is built and works. A page appears *here* when somebody
spent an afternoon establishing something and the next person would otherwise spend the same
afternoon.

Two kinds of thing belong here, and nothing else:

- **What a previous build learned the hard way.** The build this one replaces is in `src_old/` and
  friends, which are gitignored, reference-only, and will be deleted. Everything in them that cost a
  real incident to discover is worth more than the code is, and it does not survive the deletion
  unless somebody writes it down.
- **What the platform actually does**, as opposed to what its manual says or what anybody
  remembers — verified by running it, with the output kept.

Two rules for a page here:

1. **Say how you know.** Measured, read in a manual, or recalled are three different claims, and a
   reader deciding whether to trust a line needs to know which it is. Mark the ones you are unsure
   about rather than leaving them level with the rest.
2. **Date it, and say what it was true of.** A platform note is true of a version. A lesson from a
   previous build is true of that build. Neither ages well silently.

| Page | What it holds |
|---|---|
| [`the-old-build.md`](the-old-build.md) | how the previous build did agents and gateways, and every incident it recorded |
| [`launchd-on-macos.md`](launchd-on-macos.md) | what `launchctl` really does, and every state a job can get stuck in |
