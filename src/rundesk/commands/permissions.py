"""`rundesk permissions` — what this Mac lets rundesk do, and what is still not allowed.

**This is not about a brain's tool permissions.** Every provider adapter already runs its CLI with
that switched off, and `docs/extending/providers.md` says so. What stops an agent taking a screenshot, clicking
a button or driving a browser is macOS TCC, and that is what this asks about.

## The bare verb reports, the named one checks

`rundesk permissions` runs nothing. It shows what the last check found, when, and in which lineage —
which is the question *"what is still not allowed"* really is, and it means nothing happens on
somebody's machine because they typed the verb to see what it was. `rundesk skills` and
`rundesk channels` already work this way.

## Nothing is proved when nobody can say whose grants it would be about

`check` refuses under a lineage of `cannot tell`. Not a caveat printed above the answers — the reason
there are no answers. A table of verdicts with no process named is a claim about nobody, and the
measured damage is specific: run from a terminal, every probe reports the *terminal's* grants, and a
gateway that cannot capture the screen is reported ready.

May depend on `capabilities`, `core` and `utils`. It is the layer that may reach both `capabilities`
and `gateways`, which is why the shim prefix and the agent name are resolved here and handed down —
`capabilities` may not import either.
"""

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from rundesk.capabilities import lineage, proving
from rundesk.core import config
from rundesk.exits import FAILED, OK
from rundesk.gateways import job
from rundesk.providers import environment
from rundesk.utils.terminal import as_table, bold

#: What the stored report is keyed under, and the three things it holds.
KEPT = "permissions"
CHECKED_AT = "checked_at"
LINEAGE = "lineage"
FOUND = "found"

#: What a lineage looks like once it is written down. Only what a later reader has to compare.
HOW, NAMED = "how", "named"

#: Said where a fix names a System Settings pane. **The panes are recalled rather than measured** —
#: `docs/research/2026-08-08-what-this-mac-lets-a-process-do.md` §8.2 records that checking one would
#: put a window on the owner's desktop — so the command says so rather than presenting a deep link as
#: a certainty.
ABOUT_THE_PANES = ("the pane each line opens is what this release believes macOS still answers to; "
                   "if one does not open, the setting is under Privacy & Security")

#: Said under a gateway lineage, because both are true, surprising, and the owner acts on them.
ABOUT_A_GATEWAY = (
    "one grant covers every agent on this machine — they are one client, not one each. "
    "The client is the interpreter at the path above, so a `brew upgrade` of it takes the grants "
    "away with no warning and this is what finds out")


def register(sub: argparse._SubParsersAction) -> None:
    """`rundesk permissions [list|lineage|check]`, built beside the verb."""
    kept = sub.add_parser("permissions", help="what this Mac lets rundesk do")
    what = kept.add_subparsers(dest="what", metavar="<what>")
    what.add_parser("list", help="every probe, what it is for, and what it touches")
    what.add_parser("lineage", help="whose grants an answer here would be about")
    asking = what.add_parser("check", help="prove them now, and write down what was found")
    asking.add_argument("probes", metavar="<probe>", nargs="*",
                        help="a group (control) or one probe (files/full-disk); "
                             "nothing means everything needed")
    asking.add_argument("--everything", action="store_true",
                        help="also prove the ones that are not needed to operate the machine")
    asking.add_argument("--verbose", action="store_true",
                        help="also print what each program really said")


def cmd_permissions(args: argparse.Namespace,
                    running: Optional[proving.Running] = None) -> int:
    """One verb in, one exit code out.

    `running` is what starts a program, and it is an argument for a sharper reason than the rule
    usually has: there is no closed port for `osascript`, and a case that reached the real one could
    put a consent dialog on somebody's screen whose wrong button denies a grant permanently.
    """
    what = getattr(args, "what", None)
    if what == "lineage":
        return _lineage()
    if what == "check":
        return _checked(list(args.probes), args.everything, args.verbose, running)
    if what == "list":
        return _listed()
    return _reported()


def _mine() -> lineage.Lineage:
    """Whose grants an answer would be about, asked of this very process.

    The shim prefix and the agent are resolved **here** and handed down: `capabilities` may not
    import `gateways`, and spelling `rundesk-gateway-` a second time inside it is the drift
    `tests/test_layers.py` already guards against elsewhere.
    """
    return lineage.read(os.getpid(), shim=f"rundesk-{job.GATEWAY}-",
                        agent=os.environ.get(environment.AGENT) or None)


def _lineage() -> int:
    """Say whose grants an answer here would be about, and how that was decided."""
    whose = _mine()
    print(bold(f"{whose.how}") + (f" — {whose.named}" if whose.named else ""))
    print(f"  {whose.said}")
    if whose.agent:
        print(f"  started for agent {whose.agent}")
    if whose.chain:
        print(f"  below: {' ← '.join(whose.chain)}")
    if whose.how == lineage.GATEWAY:
        print(f"  {ABOUT_A_GATEWAY}")
    if not whose.certain:
        print("nothing can be proved while this is the answer", file=sys.stderr)
        return FAILED
    return OK


def _listed() -> int:
    """Every probe, what it is for, and what settling it does. Runs nothing."""
    rows: List[Tuple[str, ...]] = []
    for one in proving.every():
        rows.append((one.address, "yes" if one.needed else "no", one.about))
    as_table(("PROBE", "NEEDED", "WHAT IT IS FOR"), rows)
    print()
    print("what settling each one does to this machine:")
    for one in proving.every():
        print(f"  {one.address:<26} {one.touches}")
    return OK


def _reported() -> int:
    """What the last check found. **Runs nothing**, which is what the bare verb is for."""
    kept = _kept()
    if not kept:
        print("nothing has been checked on this install", file=sys.stderr)
        print("  rundesk permissions check", file=sys.stderr)
        return FAILED

    whose, found = kept.get(LINEAGE) or {}, kept.get(FOUND) or {}
    print(f"as of {kept.get(CHECKED_AT) or 'an unrecorded moment'}, about "
          f"{whose.get(HOW) or 'a lineage nobody wrote down'}"
          + (f" ({whose.get(NAMED)})" if whose.get(NAMED) else ""))
    mine = _mine()
    if whose.get(HOW) and mine.certain and whose.get(HOW) != mine.how:
        # A terminal's answer is not a gateway's. Saying so, rather than letting somebody read a
        # stored `ready` as though it were about the process they are asking on behalf of.
        print(f"  this is a {mine.how} — what is below was proved somewhere else and may not "
              "hold here")
    elif whose.get(HOW) and mine.certain and whose.get(NAMED) and mine.named \
            and whose.get(NAMED) != mine.named:
        # Same kind of lineage and a different client, which the kind alone cannot show: two
        # terminals are two rows in a privacy pane, and an interpreter that moved is the hazard
        # this command exists to find.
        print(f"  this process is {mine.named}, and what is below was proved by "
              f"{whose.get(NAMED)} — a different client, holding its own grants")
    if whose.get(HOW) and whose.get(HOW) != lineage.GATEWAY:
        # **Measured, and the reason this line is unconditional.** A `permissions check` run by a
        # brain's tool call inside a turn was expected to be a descendant of the gateway shim and
        # reported `unknown` — the tool re-parents what it starts, so the shim is gone from the
        # chain — and it wrote down `ready` for a lineage that is not the gateway's. Read back from
        # any lineage but the one it was proved in, the row above would otherwise be taken for what
        # a gateway may do, and a gateway holds whatever *it* was granted and nothing lent to it.
        print(f"  nothing here was proved in a gateway, so none of it says what a gateway may do — "
              f"it is about {whose.get(NAMED) or whose.get(HOW)}")
    print()
    rows: List[Tuple[str, ...]] = []
    for one in proving.every():
        # A probe that has never been run is absent from the mapping, and says so rather than
        # borrowing a verdict: never asked and asked-and-unanswerable are different answers.
        rows.append((one.address, str(found.get(one.address) or "not checked")))
    as_table(("PROBE", "IS"), rows)
    outstanding = [name for name, said in sorted(found.items()) if said in proving.TROUBLE]
    if outstanding:
        print(f"permissions: {len(outstanding)} still not allowed — "
              "rundesk permissions check to prove them again", file=sys.stderr)
        return FAILED
    return OK


def _checked(wanted: Sequence[str], everything: bool, verbose: bool,
             running: Optional[proving.Running]) -> int:
    """Prove them now, say what was found, and write it down."""
    whose = _mine()
    if not whose.certain:
        # Structural, not a caveat: a table of verdicts with no process named is a claim about
        # nobody, so there is no table.
        print(f"permissions: {whose.said}", file=sys.stderr)
        print("  nothing was probed — a verdict with no process named is a claim about nobody",
              file=sys.stderr)
        return FAILED

    probes = proving.named(wanted) if wanted else (proving.every() if everything
                                                   else proving.needed())
    if wanted and not probes:
        print(f"permissions: nothing here is called {' or '.join(wanted)}", file=sys.stderr)
        for one in proving.every():
            print(f"  {one.address}", file=sys.stderr)
        return FAILED

    print(_about(whose))
    if whose.how == lineage.GATEWAY:
        print(ABOUT_A_GATEWAY)
    print()

    into = Path(tempfile.mkdtemp(prefix="rundesk-permissions-"))
    try:
        found = proving.looked_over(probes, whose, into, running)
    finally:
        # Whatever a probe left, and the directory itself. A capture of somebody's screen is not a
        # thing to leave lying in a temporary directory because a probe raised on the way out.
        for one in sorted(into.glob("*")):
            one.unlink(missing_ok=True)
        into.rmdir()

    _print_found(found, verbose)
    _write_down(found, whose)

    trouble = proving.counted(found)
    sys.stdout.flush()
    if not trouble:
        return OK
    print(f"permissions: {len(trouble)} of {len(found)} cannot be used by "
          f"{whose.named or whose.how}:", file=sys.stderr)
    for one in proving.fixes(found):
        print(f"        {one}", file=sys.stderr)
    if any("systempreferences" in one for one in proving.fixes(found)):
        print(f"        ({ABOUT_THE_PANES})", file=sys.stderr)
    return FAILED


def _about(whose: lineage.Lineage) -> str:
    """The line that qualifies every row below it. **Stdout, and first.**

    A script reading only stdout has to see it, because without it every row below is an answer
    about an unnamed process — and the measured failure is a check run at a terminal reporting a
    gateway's capabilities using the terminal's grants.
    """
    named = f" ({whose.named})" if whose.named else ""
    if whose.how == lineage.GATEWAY:
        return f"these answers are about this gateway{named}"
    # **Said for every lineage that is not a gateway, and `unknown` is the one that had to be
    # measured.** Running this from inside a turn was documented as the way to ask on a gateway's
    # behalf; asked through a brain's tool call it answered `unknown`, named the brain's own
    # program, and proved that program's grants. Whatever this is a descendant of, it is not the
    # gateway unless it says `gateway`.
    return (f"these answers are about {whose.how}{named}, which this command was started under — "
            "a gateway is a different process and may be answered differently")


def _print_found(found: Sequence[proving.Proof], verbose: bool) -> None:
    """The verdicts, grouped, with widths measured against what is actually there."""
    for group in proving.groups():
        mine = [one for one in found if one.probe.group == group]
        if not mine:
            continue
        print(bold(group))
        wide = max(len(one.probe.name) for one in mine)
        for one in mine:
            print(f"  {one.probe.name:<{wide}}  {one.verdict:<11} {one.said}")
            if one.fix:
                print(f"  {'':<{wide}}      {one.fix}")
            if verbose and one.ran is not None:
                print(f"  {'':<{wide}}      it said: {one.ran!r}")


def _kept() -> Dict[str, object]:
    """What the last check wrote down, or `{}` where nothing has been checked.

    An unreadable configuration is not an unchecked install, so it is left to raise rather than
    answered as empty — the same rule `config.read` is written to.
    """
    said = config.read().get(KEPT)
    return dict(said) if isinstance(said, dict) else {}


def _write_down(found: Sequence[proving.Proof], whose: lineage.Lineage) -> None:
    """Keep what was found, so that what is still not allowed can be asked without running anything.

    **Only what was actually proved.** A `check control` updates four probes and leaves every other
    exactly as it was, with its older answer — because saying nothing about a probe this run never
    ran is honest, and overwriting it with an absence would throw away a real answer.

    A probe that has never been run is **absent from the mapping**, never `unproven`: never asked
    and asked-and-unanswerable are different, and this is the file a later reader trusts.
    """
    kept = dict(_kept())
    said = dict(kept.get(FOUND) or {})
    said.update({one.probe.address: one.verdict for one in found})
    config.stated(KEPT, {
        CHECKED_AT: config.moment_of(),
        LINEAGE: {HOW: whose.how, NAMED: whose.named},
        FOUND: said,
    })
