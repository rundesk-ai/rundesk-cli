"""The skills this install has, where they came from, which agent holds which, and what they need.

Eleven sub-verbs, and the shape of the group is the shape of the thing: a **catalog** is what you
install, update and remove, and a **skill** is what you grant. Nothing installs one skill and nothing
removes one, because a catalog is what somebody publishes and follows.

**A skill is addressed `<catalog>/<skill>`, always.** Two catalogs may both hold `writing-plans`, so a
verb that took the bare name would have to guess — and a guess that is unambiguous today stops being
so the moment a second catalog is installed. The refusal names every catalog holding that name, so
being wrong costs one copy-paste.

## Where `--confirm` is and is not

Anything that changes what is installed says what it would do, does none of it, and exits non-zero
without `--confirm`: `install`, `update`, `remove` and `forget`. Not `grant` and not `revoke` — those
are one link in one directory and a person who typed the wrong one types the other verb. The line
between them is "would somebody want to read this before it happened", and for a catalog update that
retires three grants the answer is yes.

`doctor` is the odd one and deliberately so: it exits non-zero when anything is wrong, the way
`env check` does, so it can be the thing a script gates on.

**No value is ever printed.** `configure` reads what is typed and never echoes it, `profiles` and
`doctor` say only whether something is set, and nothing here can read a value even if it wanted to —
`tests/test_layers.py` holds `skills/` to that.
"""

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rundesk.agents import directory
from rundesk.commands import Subcommands, env, failed, print_json
from rundesk.core import paths, secrets
from rundesk.exits import FAILED, OK
from rundesk.skills import catalogs, doctor, grants, library, needs
from rundesk.teams import catalogs as team_catalogs
from rundesk.utils import archives, locking
from rundesk.utils.terminal import NOTHING, as_table

#: Everything a verb here can be stopped by. One tuple, because six verbs catch the same set and six
#: copies of it is five chances for one to fall behind.
TROUBLE = (library.Refused, catalogs.Refused, catalogs.HalfInstalled, grants.Refused,
           grants.HalfCopied,
           needs.Refused, archives.Refused, directory.Refused, secrets.Refused, locking.Stuck,
           OSError)


def register(sub: Subcommands) -> None:
    """Put `skills` on the parser, one sub-verb at a time.

    `--confirm` is `store_true` and checked by the verb rather than `required=True`, the way it is
    everywhere else here: argparse's own refusal is a usage error, and a person who left it off did
    not make a usage error — they asked to be told what would happen, which is what they get.
    """
    said = sub.add_parser("skills", help="the skills this install has, and who holds which")
    said.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                      help="write one machine-readable JSON response")
    what = said.add_subparsers(dest="what", metavar="<what>")

    shown = what.add_parser("list", help="every skill, or the ones one agent holds")
    shown.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                       help="whose skills to show; without one, every skill there is")
    shown.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                       help="write one machine-readable JSON response")

    what.add_parser("catalogs", help="every catalog, its version and where it came from")

    new = what.add_parser("install", help="install a catalog of skills")
    new.add_argument("repository", metavar="<repository>",
                     help="a GitHub repository URL, or a directory on this machine")
    new.add_argument("--confirm", action="store_true",
                     help="required — without it, nothing is installed")

    moved = what.add_parser("update", help="check a catalog against where it came from")
    moved.add_argument("catalog", metavar="<catalog>", help="which catalog to check")
    moved.add_argument("--confirm", action="store_true",
                       help="required — without it, nothing is changed")

    gone = what.add_parser("remove", help="take a catalog away, and every skill in it")
    gone.add_argument("catalog", metavar="<catalog>", help="which catalog to remove")
    gone.add_argument("--confirm", action="store_true",
                      help="required — removal does nothing without it")

    given = what.add_parser("grant", help="give an agent a skill")
    given.add_argument("agent", metavar="<agent>", help="who gets it")
    given.add_argument("skill", metavar=f"<{library.ADDRESS}>", help="which skill, and from where")
    given.add_argument("--as", dest="alias", metavar="<name>", default="",
                       help="stand it under another name, so an agent can hold two of one name")

    taken = what.add_parser("revoke", help="take a skill away from an agent")
    taken.add_argument("agent", metavar="<agent>", help="who loses it")
    taken.add_argument("skill", metavar="<skill>", help="which one, as it stands in that agent")

    every = what.add_parser("profiles", help="the accounts one skill is configured for")
    every.add_argument("skill", metavar=f"<{library.ADDRESS}>", help="which skill")

    set_up = what.add_parser("configure", help="set the values one skill needs")
    set_up.add_argument("skill", metavar=f"<{library.ADDRESS}>", help="which skill")
    set_up.add_argument("--profile", metavar="<name>", default="",
                        help="which account; without one, the default set")

    forget = what.add_parser("forget", help="empty the values of one account")
    forget.add_argument("skill", metavar=f"<{library.ADDRESS}>", help="which skill")
    forget.add_argument("--profile", metavar="<name>", default="",
                        help="which account; without one, the default set")
    forget.add_argument("--confirm", action="store_true",
                        help="required — without it, nothing is emptied")

    checked = what.add_parser("doctor", help="what cannot be used, and exactly why")
    checked.add_argument("agent", metavar="<agent>", nargs="?", default=None,
                         help="whose skills to check; without one, every agent's")


def cmd_skills(args: argparse.Namespace, fetching: Optional[catalogs.Fetching] = None) -> int:
    """Answer whichever sub-verb was asked for; with none of them, list what there is.

    `fetching` is the one thing here that leaves the machine, resolved inside the body rather than
    bound in the signature so that the whole group is driven offline in a test.
    """
    try:
        paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    what = getattr(args, "what", None)
    if what in (None, "list"):
        return _listed(getattr(args, "agent", None), getattr(args, "json", False))
    if what == "catalogs":
        return _catalogs()
    if what == "install":
        return _installed(args.repository, args.confirm, fetching)
    if what == "update":
        return _updated(args.catalog, args.confirm, fetching)
    if what == "remove":
        return _removed(args.catalog, args.confirm)
    if what == "grant":
        return _granted(args.agent, args.skill, args.alias)
    if what == "revoke":
        return _revoked(args.agent, args.skill)
    if what == "profiles":
        return _profiles(args.skill)
    if what == "configure":
        return _configured(args.skill, args.profile)
    if what == "forget":
        return _forgotten(args.skill, args.profile, args.confirm)
    if what == "doctor":
        return _doctored(args.agent)

    # Unreachable while every sub-verb above is answered, and that is the point: one added to the
    # parser and wired to nothing fails here loudly rather than exiting zero in silence.
    raise AssertionError(f"skills {what} is registered on the parser and answered by nothing")


def refreshed(refreshing: Optional[catalogs.Fetching] = None) -> List[str]:
    """Bring every catalog up to date, and hand back the sentences a caller has to print.

    **Called by `install` and by `update`, after each has already succeeded**, which is what makes it
    a separate boundary rather than a step. Placing the catalog rundesk ships needs no network at
    all — it comes out of the release — so a machine that cannot reach GitHub still finishes with
    working skills, and the check against the published repository is the part allowed to fail.

    **A catalog that could not be checked does not change the caller's exit code**, and the reasoning
    is the one this product is built around rather than an exception to it. What `install` and
    `update` report is whether *they* worked, and they did: the release landed, the data was carried,
    the command answers. A repository somebody deleted last week is a true thing to say and a false
    reason to tell a script that the update failed — `install.sh` would then treat a healthy machine
    as a broken one. So it is said plainly, on stderr, with the command that retries just it.

    Public because two command modules need exactly this and there is one right way to do it. The
    build this replaces had `update` reach into the skills group for a *private*, and its own notes
    recorded that as a trap.
    """
    said: List[str] = []
    try:
        outcomes = catalogs.refresh(refreshing, _out_loud, _dependency_catalog)
    except TROUBLE as why:
        return [f"the skill catalogs could not be checked: {why}",
                "rundesk skills catalogs says what is installed"]

    try:
        return _retired_and_remade(outcomes, said)
    except TROUBLE as why:
        # Inside a guard, like the fetch above it. Remaking the grants ran outside one, so an
        # ordinary `OSError` while remaking a single stale copy came out of `rundesk update` as a
        # traceback with no exit code at all — turning a release that had already landed and settled
        # into a hard crash. That is a sharper break of this function's own contract than any
        # catalog being unreachable.
        said.append(f"the grants could not all be brought up to date: {why}")
        said.append("rundesk skills doctor says which agent is affected")
        return said


def _retired_and_remade(outcomes: List[catalogs.Refreshed], said: List[str]) -> List[str]:
    """Take away grants of skills that left their catalog, remake stale copies, and report."""
    for one in outcomes:
        if one.why:
            said.append(f"{one.name} could not be checked: {one.why}")
            said.append(f"rundesk skills update {one.name} --confirm tries just that one")
            continue
        # The version move is *not* announced here. `catalogs.update` was handed this same `saying`
        # and has already said it, so printing it from the outcome as well put the line out twice on
        # every real update that found a change — with the retirements sandwiched between the copies.
        # One fact, one place that renders it.
        went = grants.retired(one.name, one.retired)
        for agent in sorted(went):
            _out_loud(f"{agent} no longer holds {', '.join(went[agent])}")
    grants.refreshed(_out_loud)
    return said


def _listed(agent: Optional[str], as_json: bool = False) -> int:
    """Every skill this install has, or the ones one agent holds."""
    if agent is not None:
        return _held_by(agent, as_json)
    try:
        every = library.every()
    except TROUBLE as why:
        return _failed(str(why))

    if as_json:
        print_json({"skills": [{
            "catalog": one.catalog,
            "name": one.name,
            "agents": sorted(_agents_holding(one.catalog, one.name)),
        } for one in every]})
        return OK

    print(f"skills in {library.where()}")
    if not every:
        print("        no skills yet — install a catalog with: "
              "rundesk skills install <repository>")
        return OK
    as_table(("CATALOG", "SKILL", "AGENTS"),
             [(one.catalog, one.name, _whoever_holds(one)) for one in every])
    return OK


def _held_by(agent: str, as_json: bool = False) -> int:
    """What one agent holds, and what each of those needs."""
    if agent not in directory.known():
        return _failed(f"there is no agent called {agent}",
                       "rundesk agents list says who there is")
    try:
        held = grants.held(agent)
    except TROUBLE as why:
        return _failed(str(why))

    if as_json:
        print_json({"agent": agent, "skills": [_json_grant(one) for one in held]})
        return OK

    print(f"skills granted to {agent} in {grants.where(agent)}")
    if not held:
        print("        none yet — give it one with: "
              f"rundesk skills grant {agent} <{library.ADDRESS}>")
        return OK
    as_table(("SKILL", "FROM", "NEEDS", "STANDING"),
             [(one.name, _from(one), _counted(one), _how(one)) for one in held])
    return OK


def _json_grant(grant: grants.Grant) -> Dict[str, Any]:
    """One grant with the same standing the human listing reads from doctor."""
    finding = doctor.of(grant)
    try:
        required_values: Optional[int] = len(needs.declared(grant.at))
    except needs.Refused:
        required_values = None
    return {
        "name": grant.name,
        "catalog": grant.catalog or None,
        "skill": grant.skill or None,
        "aliased": grant.copied,
        "required_values": required_values,
        "standing": {"verdict": finding.verdict, "description": finding.said},
    }


def _catalogs() -> int:
    """Every catalog, what version it is on and where it came from."""
    try:
        every = library.catalogs()
    except TROUBLE as why:
        return _failed(str(why))

    print(f"catalogs in {library.where()}")
    if not every:
        print("        none yet — install one with: rundesk skills install <repository>")
        return OK
    as_table(("CATALOG", "VERSION", "SKILLS", "SOURCE"),
             [(one.name, one.manifest.version, str(len(library.found(library.inside(one.name)))),
               _came_from(one)) for one in every])
    return OK


def _installed(source: str, confirm: bool, fetching: Optional[catalogs.Fetching]) -> int:
    """Install a catalog, or say what installing it would bring.

    The fetch happens either way and the preview is read off the same validated tree the install
    would use — so what somebody is shown is what would land, rather than a description of it.
    """
    try:
        with catalogs.brought(source, "", fetching) as coming:
            if coming.manifest is None or coming.at is None:
                return _failed(f"nothing was fetched from {source}")
            taken = catalogs.reserved(coming.manifest.name)
            if taken:
                # Before the confirmation is even looked at, for the reason `remove` refuses early:
                # asking somebody to confirm something that will then be refused is a worse answer
                # than refusing now.
                return _failed(taken)
            if not confirm:
                return _would_install(coming)
            did = catalogs.installed(coming, _out_loud)
    except TROUBLE as why:
        return _failed(str(why), "nothing was installed")

    print(f"{did.name} {did.after} installed")
    print(f"        skills   {', '.join(did.skills)}")
    print("        granted  none — give one to an agent with: "
          f"rundesk skills grant <agent> {did.name}/<skill>")
    return OK


def _would_install(coming: catalogs.Coming) -> int:
    """What installing this catalog would bring, on stderr, having changed nothing."""
    manifest = coming.manifest
    print(f"install: this would install {manifest.name} {manifest.version} from {coming.source}",
          file=sys.stderr)
    print(f"        about    {manifest.description}", file=sys.stderr)
    for name in coming.skills:
        wanted = _wanted_by(coming.at / library.INSIDE / name)
        print(f"        skill    {name}{wanted}", file=sys.stderr)
    print("        none of its skills would be granted to anybody.", file=sys.stderr)
    print("        nothing was installed. To go ahead:", file=sys.stderr)
    print(f"        rundesk skills install {coming.source} --confirm", file=sys.stderr)
    return FAILED


def _updated(name: str, confirm: bool, fetching: Optional[catalogs.Fetching]) -> int:
    """Check a catalog against where it came from, or say what checking it would change."""
    if library.is_team(name):
        return _failed(f"{name} declares a team — update it with: rundesk teams update {name}")
    if not confirm:
        return _would_update(name, fetching)
    try:
        # **Deliberately not handed `_out_loud`.** This function renders every fact out of what comes
        # back, and `catalogs.update` says those same facts through `saying` for the sweep in
        # `refreshed`, which has no other voice. Handed both, one `rundesk skills update` said the
        # outcome twice — once indented and once not.
        did = catalogs.update(name, fetching, validating=_dependency_catalog)
    except TROUBLE as why:
        return _failed(str(why))

    # **Its own boundary, because by here the catalog has already been replaced on disk.** Sharing the
    # guard above reported `skills: FAILED` for an update that had entirely succeeded: `refreshed`
    # sweeps every agent and takes a lock per agent, so ordinary contention anywhere in it — the thing
    # `locking.Stuck` exists for — came out as the verb's own failure. The same reasoning, and the
    # same wording, as the sweep `install` and `rundesk update` run through `refreshed` above.
    went: Dict[str, List[str]] = {}
    sweeping = ""
    try:
        went = grants.retired(name, did.retired)
        grants.refreshed(_out_loud)
    except TROUBLE as why:
        sweeping = str(why)

    # **Decided by `did.changed`, never by the versions matching** — see `catalogs.Installed`.
    if not did.changed:
        # "nothing changed" rather than "nothing was fetched", because both answers arrive here:
        # a `304` fetched nothing at all, and a local directory hands back a whole tree that turns out
        # to be the one already standing. The second had this line claiming no fetch had happened.
        print(f"{name} {did.after} — up to date, nothing changed")
        return OK
    if did.before != did.after:
        print(f"{name} {did.before} -> {did.after} — its tree was replaced")
    else:
        print(f"{name} {did.after} — its tree was replaced, at the same version")
    for one in did.retired:
        print(f"        {one} is no longer in this catalog")
    for agent in sorted(went):
        print(f"        {agent} no longer holds {', '.join(went[agent])}")
    _swept(sweeping)
    return OK


def _swept(why: str) -> None:
    """Say that the grants could not all be brought into line, if they could not.

    On stderr and without changing the exit code, for the reason `refreshed` gives at length: what the
    verb reports is whether *it* worked, and it did — the tree was replaced. A sweep that could not
    finish is a true thing to say and a false reason to tell a script the update failed.
    """
    if not why:
        return
    print(f"        the grants could not all be brought up to date: {why}", file=sys.stderr)
    print("        rundesk skills doctor says which agent is affected", file=sys.stderr)


def _would_update(name: str, fetching: Optional[catalogs.Fetching]) -> int:
    """What checking this catalog would change, having changed nothing.

    Exits non-zero even when the answer is "nothing", because the answer to `--confirm` being absent
    is always "this did not happen" — and a script that read zero here would take it for done.
    """
    try:
        settled = library.read(name)
        if settled.provenance is None or not catalogs.may_be_fetched(name):
            return _failed(f"{name} is not fetched from anywhere, so there is nothing to check")
        holding = library.found(library.inside(name))
        with catalogs.brought(settled.provenance.source, settled.provenance.etag,
                              fetching) as coming:
            # **Asked of `catalogs.brings_a_change` rather than worked out here**, so a preview
            # cannot promise something `--confirm` then declines to do. This used to read
            # `not coming.fresh`, which is only one of the ways there is nothing to do: a local
            # directory has no `ETag`, so it always hands back a whole tree and always looked fresh —
            # and the preview said it would replace a tree that was already identical.
            if not catalogs.brings_a_change(settled.at, coming):
                print(f"update: {name} {settled.manifest.version} is up to date — nothing would "
                      "change", file=sys.stderr)
            elif coming.manifest is not None:
                _dependency_catalog(coming.at, coming.manifest)
                # **Says the tree would be replaced, and names a version movement only when there
                # is one.** What is on the far end is authoritative whether its version moved or
                # not, so a catalog whose author edited a skill without bumping a number is one this
                # would still replace — and a preview reading "would move acme from 1.0.0 to 1.0.0"
                # is a preview describing something that is not happening.
                moved = (f", moving it from {settled.manifest.version} to "
                         f"{coming.manifest.version}"
                         if coming.manifest.version != settled.manifest.version else "")
                print(f"update: this would replace {name}'s tree from "
                      f"{settled.provenance.source}{moved}", file=sys.stderr)
                print("        discard any local edit inside it — the repository is the source of "
                      "truth and an edit here is drift", file=sys.stderr)
                for one in holding:
                    if one not in coming.skills:
                        print(f"        take    {one} — it is no longer in this catalog, and every "
                              "grant of it would be revoked", file=sys.stderr)
                for one in coming.skills:
                    if one not in holding:
                        print(f"        add     {one}", file=sys.stderr)
    except TROUBLE as why:
        return _failed(str(why))

    print("        nothing was changed. To go ahead:", file=sys.stderr)
    print(f"        rundesk skills update {name} --confirm", file=sys.stderr)
    return FAILED


def _removed(name: str, confirm: bool) -> int:
    """Take a catalog away, or say what taking it away would cost."""
    try:
        settled = library.read(name)
    except TROUBLE as why:
        return _failed(str(why))

    if library.is_team(name):
        return _failed(f"{name} declares a team and cannot be removed through skills")

    stays = catalogs.what_stays(name)
    if stays:
        # Refused before `--confirm` is even looked at. A catalog that cannot be removed cannot be
        # removed with a flag either, and asking somebody to confirm something that will then be
        # refused is a worse answer than refusing now.
        return _failed(stays)

    try:
        dependents = team_catalogs.dependents(name)
    except (team_catalogs.Refused, library.Refused, OSError) as why:
        return _failed(f"installed team dependencies could not be checked ({why})")
    if dependents:
        return _failed(f"{name} is required by installed teams: "
                       f"{', '.join(sorted(dependents))} — update those team declarations before "
                       "removing it")

    holding = library.found(library.inside(name))
    if not confirm:
        return _would_remove(name, settled, holding)
    try:
        went = catalogs.remove(name)
        lost = grants.retired(name, went)
    except TROUBLE as why:
        return _failed(str(why), f"{name} is unchanged")

    print(f"{name} removed")
    print(f"        skills   {', '.join(went) if went else 'none'}")
    for agent in sorted(lost):
        print(f"        {agent} no longer holds {', '.join(lost[agent])}")
    return OK


def _dependency_catalog(at: Path, manifest: library.Manifest) -> None:
    """Refuse a replacement that would strand a skill required by an installed team."""
    try:
        dependents = team_catalogs.dependents(manifest.name)
    except (team_catalogs.Refused, library.Refused, OSError) as why:
        raise catalogs.Refused(f"installed team dependencies could not be checked ({why})") from why
    available = set(library.found(at / library.INSIDE))
    missing = {team: [skill for skill in skills if skill not in available]
               for team, skills in dependents.items()}
    missing = {team: skills for team, skills in missing.items() if skills}
    if missing:
        details = "; ".join(f"{team}: {', '.join(skills)}"
                            for team, skills in sorted(missing.items()))
        raise catalogs.Refused(
            f"{manifest.name} cannot retire skills required by installed teams ({details})")


def _would_remove(name: str, settled: library.Catalog, holding: List[str]) -> int:
    """What removing this catalog would take, on stderr, having taken none of it."""
    print(f"remove: this would take the catalog {name} from {library.where()}", file=sys.stderr)
    print(f"        take     {settled.at} — the whole catalog, at {settled.manifest.version}",
          file=sys.stderr)
    for one in holding:
        who = sorted(_agents_holding(name, one))
        also = f" — held by {', '.join(who)}, and revoked from each" if who else ""
        print(f"        take     {one}{also}", file=sys.stderr)
    print("        keep     any value you set for it — rundesk env forgets nothing here",
          file=sys.stderr)
    print("        nothing was removed. To go ahead:", file=sys.stderr)
    print(f"        rundesk skills remove {name} --confirm", file=sys.stderr)
    return FAILED


def _granted(agent: str, address: str, alias: str) -> int:
    """Give an agent a skill."""
    try:
        skill = library.look_up(address)
        held = grants.granted(agent, skill, alias)
    except grants.NotPresented as why:
        return _not_presented(why, f"{agent} does hold it",
                              "rundesk skills doctor reports it as UNSEEN, and rundesk update "
                              "repairs it")
    except grants.Occupied as why:
        # The one refusal with a way out. Told apart by its own kind rather than worked out from the
        # address afterwards — see `grants.Occupied` for the two refusals that trick that.
        return _failed(str(why),
                       f"revoke it:     rundesk skills revoke {agent} {alias or skill.name}",
                       f"or hold both:  rundesk skills grant {agent} {address} --as <name>")
    except TROUBLE as why:
        return _failed(str(why))

    print(f"{agent} holds {held.name}")
    print(f"        from     {held.catalog}/{held.skill}"
          f"{' — a copy, standing under another name' if held.copied else ''}")
    print(f"        stands   {held.at}")

    # **Read after the grant landed, so it may not fail the grant.** A skill whose declaration will
    # not parse is a real thing to meet — a catalog author ships one — and reading it here used to
    # crash the verb *after* the link was already on disk, which reported nothing about the work that
    # had succeeded. The grant is done either way; this is the part that says what is still needed.
    try:
        wanted = needs.declared(skill.at)
    except needs.Refused as why:
        print(f"        needs    what it needs cannot be read — {why}")
        return OK
    if wanted:
        print(f"        needs    {', '.join(one.env for one in wanted)}")
        if not needs.usable(wanted):
            print("        none of it is set yet, so nothing can use this skill:")
            print(f"        rundesk skills configure {skill.address}")
    return OK


def _not_presented(why: Exception, landed: str, then: str) -> int:
    """Say that the change landed and the linking did not, which is not the same as having failed.

    One function because two verbs reach it and the wording has to hold for both. The difference
    decides what somebody does next: told a grant had failed they retry and meet "already holds it",
    and told a revoke had failed they look for a skill that is already gone — in each case having been
    given no reason to think the first command worked.

    **The last line is the caller's, and that is not a style choice.** After a grant the skill is
    still held, so `doctor` walks it and reports `UNSEEN`. After a revoke it is not: `grants.revoked`
    takes the grant away *before* it presents, so there is nothing left for `doctor` to walk — it says
    "nothing is granted" and exits zero while the vendor links sit there. One shared line sent
    somebody to `doctor` for a fault `doctor` cannot see, which is the defect this whole change exists
    to remove, pointing the other way.
    """
    return failed(f"skills: FAILED — {why}", landed,
                  "this was the linking into each provider's own root", then)


def _revoked(agent: str, name: str) -> int:
    """Take a skill away from an agent."""
    try:
        went = grants.revoked(agent, name)
    except grants.NotPresented as why:
        # **Every verb that can reach the raiser needs its own answer.** `NotPresented` is
        # deliberately outside `TROUBLE` — that is the whole point of giving it its own kind — so a
        # verb that does not name it does not catch it at all, and `revoke` did not: an ordinary
        # revoke under lock contention came out of `cli.main` as a traceback. Splitting a type out of
        # a blanket catch is not finished until every caller of what raises it has been checked.
        # No mention of `doctor`: there is no grant left for it to look at. `rundesk update` prunes
        # the links, which is a true thing to say and the only one there is.
        return _not_presented(why, f"{agent} no longer holds it",
                              "rundesk update clears any link left standing in a provider's root")
    except TROUBLE as why:
        return _failed(str(why))

    print(f"{agent} no longer holds {name}")
    if went.address:
        # **Asked of the grant rather than assumed.** A revoke is exactly what somebody is told to
        # do about a `DANGLING` grant — the skill is already gone from the library, which is why the
        # grant pointed at nothing — and saying it is "still in the library" there sends them to look
        # for something that is not there, in the one case the command was reached for on purpose.
        print(f"        it came from {went.address}, and is still in the library" if went.resolves
              else f"        it came from {went.address}, which is no longer in the library")
    return OK


def _profiles(address: str) -> int:
    """Every account one skill is configured for, and whether each of them is whole."""
    try:
        skill = library.look_up(address)
        wanted = needs.declared(skill.at)
    except TROUBLE as why:
        return _failed(str(why))

    if not wanted:
        print(f"{skill.address} needs no credentials, so it has no profiles")
        return OK

    # Walked once, for the reason `doctor._verdict` gives: each of `every`, `started` and `usable`
    # asks the credential store about every declared name, and asking all three walked it three times.
    every = needs.every(wanted)
    started = [one for one in every if one.exists]

    print(f"profiles for {skill.address}")
    as_table(("PROFILE", "STANDING", "MISSING"),
             [(one.shown, _whole(one), ", ".join(one.missing) or NOTHING) for one in every])
    unfinished = next((one for one in started if not one.whole), None)
    if unfinished is not None:
        print(f"        finish it: rundesk skills configure {skill.address} "
              f"--profile {unfinished.shown}")
    elif not any(one.whole for one in started):
        print(f"        set it up: rundesk skills configure {skill.address}")
    return OK


def _configured(address: str, profile: str) -> int:
    """Set the values one skill needs, one at a time, reading each rather than taking it as an
    argument.

    A value already set may be kept by typing nothing, so finishing a half-configured account does
    not mean re-typing the parts that were right. Everything still missing at the end is named, so
    a run that was interrupted says exactly what is left.
    """
    try:
        skill = library.look_up(address)
        wanted = needs.declared(skill.at)
        if profile:
            trouble = needs.profile_trouble(profile)
            if trouble:
                return _failed(trouble)
    except TROUBLE as why:
        return _failed(str(why))

    if not wanted:
        return _failed(f"{skill.address} needs no credentials, so there is nothing to configure")

    where = f" for {needs.as_named(profile).lower()}" if profile else ""
    print(f"{skill.name} needs {len(wanted)} value{'s' if len(wanted) > 1 else ''}{where}")
    kept = 0
    for one in wanted:
        full = needs.named(one.env, profile)
        already = secrets.placed(full)
        print(f"        {full}   {one.about}"
              f"{' — set; type nothing to keep it' if already else ''}")
        said = env.typed("        > ")
        if said is None:
            if not already:
                print(f"        {full} was left unset")
            continue
        try:
            secrets.stated(full, said)
        except (secrets.Refused, secrets.Stuck, OSError) as why:
            return _failed(str(why), f"{kept} value(s) were kept before this")
        kept += 1

    return _how_it_stands(skill, wanted, profile, kept)


def _how_it_stands(skill: library.Skill, wanted: List[needs.Need], profile: str, kept: int) -> int:
    """What a `configure` ended up with — and non-zero when it is still not usable.

    Non-zero on an account that is still incomplete, because a half-configured profile is the exact
    state this whole mechanism exists to make visible: a command that exited zero on one would be
    reporting a success nobody earned.
    """
    held = needs.standing(wanted, profile)
    print(f"        kept {kept} value{'s' if kept != 1 else ''}")
    if held.whole:
        print(f"profile {held.shown} is complete")
        return OK
    print(f"skills: FAILED — profile {held.shown} is not complete", file=sys.stderr)
    print(f"        not set  {', '.join(held.missing)}", file=sys.stderr)
    print(f"        rundesk skills configure {skill.address}"
          f"{f' --profile {held.shown}' if held.name else ''}", file=sys.stderr)
    return FAILED


def _forgotten(address: str, profile: str, confirm: bool) -> int:
    """Empty every value of one account."""
    try:
        skill = library.look_up(address)
        wanted = needs.declared(skill.at)
    except TROUBLE as why:
        return _failed(str(why))

    if not wanted:
        return _failed(f"{skill.address} needs no credentials, so there is nothing to forget")
    held = needs.standing(wanted, profile)
    there = [needs.named(one.env, profile) for one in wanted
             if needs.named(one.env, profile) not in held.missing]
    if not there:
        return _failed(f"nothing is set for {skill.address} under {held.shown}")

    if not confirm:
        print(f"forget: this would empty {len(there)} value(s) for {skill.address}",
              file=sys.stderr)
        for full in there:
            print(f"        empty    {full}", file=sys.stderr)
        print("        the names stay, holding nothing, so it is visible as switched off rather "
              "than never configured.", file=sys.stderr)
        print("        nothing was emptied. To go ahead:", file=sys.stderr)
        print(f"        rundesk skills forget {address}"
              f"{f' --profile {profile}' if profile else ''} --confirm", file=sys.stderr)
        return FAILED

    try:
        for full in there:
            secrets.cleared(full)
    except (secrets.Refused, secrets.Stuck, OSError) as why:
        return _failed(str(why))
    print(f"{skill.address} {held.shown} is emptied — {len(there)} value(s)")
    return OK


def _doctored(agent: Optional[str]) -> int:
    """Say what cannot be used and why, and exit non-zero when anything is wrong."""
    if agent is not None and agent not in directory.known():
        return _failed(f"there is no agent called {agent}",
                       "rundesk agents list says who there is")
    try:
        found = doctor.looked_over(agent)
    except TROUBLE as why:
        return _failed(str(why))

    if not found:
        who = agent or "any agent"
        print(f"nothing is granted to {who}, so there is nothing to check")
        return OK

    for one in _by_agent(found):
        print(one)
    trouble = doctor.counted(found)
    if not trouble:
        print(f"all {len(found)} of them are ready")
        return OK

    # Flushed before anything goes to stderr. The findings are on stdout so a script can read them
    # and the summary is on stderr so a script can ignore it — but stdout is block-buffered into a
    # pipe and stderr is not, so `rundesk skills doctor | less` showed the summary *above* the
    # findings it summarises.
    sys.stdout.flush()
    # **The colon is only earned when something follows it.** Not every verdict has a command behind
    # it — a provider root holding something of the operator's own is a fault rundesk states and
    # refuses to act on — and a heading reading "3 of 4 cannot be used:" with nothing under it reads
    # like output that went missing.
    typing = doctor.fixes(trouble)
    ending = ":" if typing else " — each of them says what is in the way"
    print(f"skills: {len(trouble)} of {len(found)} cannot be used{ending}", file=sys.stderr)
    for line in typing:
        print(f"        {line}", file=sys.stderr)
    return FAILED


def _by_agent(found: List[doctor.Finding]) -> List[str]:
    """The findings as lines, grouped under each agent's own name.

    Grouped here rather than in `doctor`, because which agent a finding belongs to is a fact and
    putting a heading above it is a decision about words.
    """
    # Measured rather than guessed. Fixed widths were wrong the first time a real catalog was
    # installed — `rundesk-skills-apple` is twenty characters and ran straight into the next column,
    # which is the kind of defect a test asserting `assertIn` never sees.
    skill = max((len(one.skill) for one in found), default=0) + 2
    where = max((len(doctor.where(one)) for one in found), default=0) + 2
    verdict = max((len(one.verdict) for one in found), default=0) + 2

    lines: List[str] = []
    standing = ""
    for one in found:
        if one.agent != standing:
            standing = one.agent
            lines.append(standing)
        lines.append(f"  {one.skill:<{skill}}{doctor.where(one):<{where}}"
                     f"{one.verdict:<{verdict}}{one.said}")
        lines.extend(f"      {said}" for said in doctor.readable(one))
    return lines


def _whoever_holds(skill: library.Skill) -> str:
    """Which agents hold this skill, read off their own directories."""
    who = sorted(_agents_holding(skill.catalog, skill.name))
    return ", ".join(who) if who else NOTHING


def _agents_holding(catalog: str, skill: str) -> List[str]:
    """Every agent holding one skill of one catalog, however it is named in their directory."""
    return [name for name in directory.known()
            if any(one.catalog == catalog and one.skill == skill for one in grants.held(name))]


def _from(grant: grants.Grant) -> str:
    """Which catalog a grant came from, as a listing shows it. The same answer `doctor` gives."""
    return grants.source_shown(grant.catalog, grant.copied)


def _counted(grant: grants.Grant) -> str:
    """How many values a granted skill needs, or nothing when it needs none."""
    try:
        wanted = needs.declared(grant.at)
    except needs.Refused:
        return "?"
    return str(len(wanted)) if wanted else NOTHING


def _how(grant: grants.Grant) -> str:
    """One line saying how a granted skill stands.

    The same verdict `doctor` gives, said shorter. Asked of `doctor` rather than worked out here,
    because a table and a diagnosis disagreeing about whether a skill is usable is the kind of thing
    nobody notices until they are relying on the wrong one.
    """
    found = doctor.of(grant)
    return found.said if found.verdict == doctor.READY else f"{found.verdict} — {found.said}"


def _whole(profile: needs.Profile) -> str:
    """Whether one account is whole, said in the three answers there are."""
    if profile.whole:
        return "complete"
    return "INCOMPLETE" if profile.exists else "not set"


def _came_from(catalog: library.Catalog) -> str:
    """Where a catalog came from, or the reason there is nowhere."""
    if catalog.provenance is None:
        return "yours" if catalog.name == library.MINE else NOTHING
    return catalog.provenance.source


def _wanted_by(at: Path) -> str:
    """What a skill about to be installed will want, said in one clause. `""` when nothing."""
    try:
        wanted = needs.declared(at)
    except needs.Refused as why:
        return f" — its declaration cannot be read: {why}"
    if not wanted:
        return ""
    return " — needs " + ", ".join(one.env for one in wanted)


def _out_loud(said: str) -> None:
    print(f"        {said}")


def _failed(why: str, *and_so: str) -> int:
    """Say what went wrong, and what that leaves — never one without the other."""
    return failed(f"skills: FAILED — {why}", *and_so)
