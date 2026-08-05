"""Moving this install to the newest published release.

The highest-consequence path in the product, so everything variable in it — what is published, how an
archive is fetched — arrives as an argument and the whole of it runs offline in a test.

The order is chosen so that the failure which cannot damage anything happens first:

1. Ask what is published. Cannot ask → **stop, non-zero**, and change nothing.
2. Not newer → settle the install anyway, and stop. Being on the newest release is not the same as
   being settled on it, and an update interrupted between the two would otherwise never finish.
3. Fetch the archive and check it is a rundesk tree, in a temporary directory. Nothing installed has
   been touched yet, so everything up to here is free to fail.
4. Replace `app/`, staged and renamed, putting back what was there if any part fails.
5. **Hand off to the release that just landed** to settle the install.

## Why step five is a handoff and not two more lines here

Once the files are replaced, this process is still running **the old release** — its modules were
imported before the swap and they do not change underneath it. So the code sitting in memory to fill
in configuration and run migration steps is the code being replaced, and it would carry the install
forward using the *previous* release's steps and the previous release's idea of what a configuration
holds. Every step the new release ships would be skipped, and the install would be stamped as
carried.

So the settling is done by loading the new release from disk in a separate interpreter and calling
its `settle()`. Deliberately not a command-line flag: settling is a step of installing and updating
rather than an operation anybody performs, and the command surface stays exactly what it says it is.
"""

import argparse
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from rundesk import __version__
from rundesk.commands import failed, the_reason
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import backups, home, migration, release, tree
from rundesk.utils import programs

#: How a release archive is brought down: given where it is and where to put it, it puts it there.
#: The second of the two things in this product that leave the machine, and like the first it is a
#: value a caller hands in rather than an import a test cannot reach past.
Fetching = Callable[[str, Path], None]

FETCH_SECONDS = 60

#: How long the newly installed release is given to settle the install. Generous: a migration step
#: may legitimately move a lot of files.
SETTLE_SECONDS = 300


def cmd_update(_args: argparse.Namespace, asking: Optional[release.Asking] = None,
               fetching: Optional[Fetching] = None) -> int:
    """Move to the newest published release, or say it is already up to date.

    Takes no flags. `asking` looks up what is published and `fetching` downloads it; both are
    resolved here rather than bound in the signature, so the whole command is driven with no network
    anywhere near it.
    """
    line, published, could_ask = release.standing(__version__, asking)
    if not could_ask:
        print(line, file=sys.stderr)
        return FAILED
    print(line)

    if not release.newer(published, __version__):
        # **Being on the newest release is not the same as being settled on it.** An update that
        # was interrupted between replacing the files and settling — a machine that slept, a
        # terminal that closed — leaves an install whose code is current and whose configuration and
        # migrations belong to the release before it. Asking GitHub then answers UP TO DATE for
        # ever, and the settling never happens: a value the new release added is never written, and
        # a migration step it shipped is never run.
        #
        # So this settles rather than checking whether settling is needed. Every part of it is
        # already idempotent — the directories are made if absent, configuration values are filled
        # in only where missing, and a migration step that has run is recorded and skipped — so
        # doing it unconditionally costs one process and makes the half-updated state impossible to
        # be left in, rather than merely unlikely.
        if not paths.app().exists():
            return OK
        gone_wrong = settled_by_the_new_release(paths.app())
        if gone_wrong:
            return _failed(f"this install is on {__version__} and is not settled — {gone_wrong}")
        return OK

    try:
        root = paths.home()
    except paths.Refused as why:
        return _failed(str(why))

    holding = tempfile.mkdtemp(prefix="rundesk-update-")
    try:
        try:
            landed = _brought_down(published, Path(holding), fetching)
        except (OSError, urllib.error.URLError, tarfile.TarError, ValueError) as why:
            return _failed(f"{published} could not be fetched: {why}")

        print(f"        installing {published}")
        try:
            tree.place(landed, root)
        except tree.HalfReplaced as why:
            return _failed(str(why))
        except (tree.Refused, OSError) as why:
            return _failed(f"{why} — this install is unchanged")
    finally:
        shutil.rmtree(holding, ignore_errors=True)

    gone_wrong = settled_by_the_new_release(paths.app())
    if gone_wrong:
        # The files landed and the settling did not. Said plainly rather than rolled back: the new
        # release is on disk, and what needs deciding is the data, which is untouched and still there.
        print(f"update: {published} is installed and was not settled — {gone_wrong}",
              file=sys.stderr)
        print("        running it again will carry on from where this stopped", file=sys.stderr)
        return FAILED

    # Recorded here, and only here, because this is the path where a version really arrived. The
    # settling above runs on every update including one that found nothing newer, so stamping in
    # there would move the answer forward every time anybody merely checked.
    try:
        config.moved(data=paths.data())
    except (config.Unreadable, config.Refused, config.Stuck) as why:
        print(f"update: {published} is installed and when it arrived was not recorded — {why}",
              file=sys.stderr)

    where = release.release_url(published.lstrip("v"))
    print(f"rundesk updated to {published}")
    if where:
        print(f"        what changed: {where}")
    return OK


def settle() -> int:
    """Make this install match the release now sitting in `app/`.

    Self-determining rather than told which case it is: an install with no configuration file has
    never been settled and has nothing to carry, and one with a configuration file is being moved
    forward. Deciding it here means the caller never has to be right about it, and running this by
    hand on an install that was interrupted is always safe.
    """
    fresh = not config.where(paths.data()).exists()
    try:
        # Inside the guard, not before it. Laying the directories down is filesystem work like
        # everything below it — a stray *file* where a directory belongs raises, and outside the
        # `try` that came out of the subprocess an install settles in as a raw traceback, which
        # `install: FAILED —` then printed verbatim to whoever ran the installer.
        home.prepare(saying=_out_loud)
        if fresh:
            config.write_fresh(paths.data())
            # Nothing to carry: the directories were made correctly a moment ago, and the steps
            # describe changes from releases this install never had.
            migration.stamp_without_running(paths.data())
        else:
            config.fill_in(paths.data())
            kept = _kept_before_carrying()
            gone_wrong = migration.carry(paths.data(), saying=_out_loud)
            if gone_wrong:
                return _failed(f"{gone_wrong}{kept}")
    except (config.Unreadable, config.Stuck, migration.Broken, OSError) as why:
        # Every write below `settle` goes through the configuration, including the stamp each
        # migration step lands with, so all of these are caught in one place rather than at each
        # of the calls that can give them.
        #
        # `OSError` is here because everything this function does is filesystem work, and the one
        # thing a settle must never do is end in a traceback: it runs in a subprocess whose stderr
        # is forwarded whole into the failure a person reads.
        #
        # `Broken` is here because steps that cannot be ordered are found by `stamp_without_running`
        # too, and that is the *fresh install* path — the one place a broken checkout is most likely
        # to be discovered. `carry` already answers it as a sentence; without this, the same fault a
        # second later came out of the other branch as a raw traceback, through a subprocess, into a
        # message somebody was meant to read.
        return _failed(str(why))
    return OK


def _kept_before_carrying() -> str:
    """Copy the data before any step touches it, and say which copy that is. `""` when none.

    **This is the rollback, and it is deliberately not a down-step.** A step that failed halfway
    has left the data in a shape only that step knew about, and an inverse written months earlier
    by somebody who never ran it is not a way back — it is a second untested change applied to an
    install that is already broken. A copy taken a moment before is the whole of the answer, it
    needs nothing written per step, and the way back is a command that already exists and is
    already proven: `rundesk backups restore <name> --confirm`.

    Taken only when there is something to carry, so an ordinary update that changes no data does
    not leave a copy behind every time. And only when the owner keeps copies at all: `backup_enabled`
    has been a setting that governed nothing until now, and an owner who turned it off should not
    be surprised by one appearing.

    A copy that could not be made is not a reason to refuse to carry — it is said, and the carrying
    goes ahead, because an install left un-migrated is its own kind of broken.
    """
    data = paths.data()
    try:
        settled = config.read(data)
        if not migration.outstanding(settled.get("migration")):
            return ""
        if not settled.get("backup_enabled"):
            return ""
        name = backups.save(data)
    except (config.Unreadable, migration.Broken, backups.Refused, OSError) as why:
        _out_loud(f"no copy was taken before carrying: {why}")
        return ""
    _out_loud(f"kept {name} — the data as it was before carrying")
    return f" — {paths.data()} as it was before this is the copy {name}"


#: Loading the release that has just landed and asking it to settle the install. Run in a separate
#: interpreter on purpose, and **not** through a command-line flag: settling is a step of installing
#: and updating rather than an operation anybody performs, so it is not on the command surface.
_SETTLE = (
    "import sys;"
    "sys.path.insert(0, sys.argv[1]);"
    "from rundesk.commands.update import settle;"
    "raise SystemExit(settle())"
)


def settled_by_the_new_release(app: Path) -> str:
    """Run the release now in `app/` to settle the install. `""` when it worked.

    A subprocess rather than an `exec`, so the process that performed the update is still here to
    report what happened. The environment is inherited, which is what carries `RUNDESK_HOME` through
    — the new release must settle the same install this one just replaced.

    `sys.executable` rather than the launcher's `#!/usr/bin/env python3`: which interpreter that
    resolves to depends on the PATH of whoever started the command, so the two can differ on one
    machine. The update runs on the interpreter that is already running it.
    """
    ended = programs.run([sys.executable, "-c", _SETTLE, str(app / "src")], SETTLE_SECONDS)
    if ended.out:
        sys.stdout.write(ended.out)
    if ended.trouble:
        return f"the installed release {ended.trouble}"
    if ended.code != 0:
        return the_reason(ended.err) or f"it ended {ended.code}"
    return ""


def _brought_down(tag: str, into: Path, fetching: Optional[Fetching] = None) -> Path:
    """Fetch and unpack a release, and hand back the tree inside it.

    Members that would escape the directory are refused. The standard library only started refusing
    them in a version far newer than the floor here, so this is checked rather than relied upon: an
    archive is somebody else's bytes, and an unpacker that trusts them writes wherever they say.
    """
    fetch = fetching or _downloaded
    archive = into / "release.tar.gz"
    fetch(release.archive_url(tag), archive)

    with tarfile.open(archive, "r:gz") as held:
        for member in held.getmembers():
            settled = (into / member.name).resolve()
            if into.resolve() not in settled.parents and settled != into.resolve():
                raise ValueError(f"{member.name} would be written outside the download")
            if member.issym() or member.islnk():
                # **The two kinds of link do not resolve their target the same way, and checking
                # them as though they did is a check that passes while the escape happens.** A
                # symlink's target is resolved by the filesystem against the link's own directory.
                # A hard link's is resolved by `tarfile` itself against the extraction root —
                # `os.path.join(path, tarinfo.linkname)`, unchanged in every version from the floor
                # here upwards. So a hard link one directory deep naming `../something` was measured
                # against the wrong place, came out looking contained, and was then created pointing
                # at a real file outside the download. That file's contents are then indistinguishable
                # from an ordinary member and get copied into `app/` with the rest of the release.
                against = into if member.islnk() else settled.parent
                pointed = (against / member.linkname).resolve()
                if into.resolve() not in pointed.parents:
                    raise ValueError(f"{member.name} points outside the download")
        held.extractall(into)

    inside = [at for at in into.iterdir() if at.is_dir()]
    for at in inside:
        if tree.is_rundesk(at):
            return at
    raise ValueError("the archive does not contain a rundesk tree")


def _downloaded(url: str, into: Path) -> None:
    """Fetch a URL to a file. The only thing here that leaves the machine."""
    asked = urllib.request.Request(url, headers={"User-Agent": release.USER_AGENT})
    with urllib.request.urlopen(asked, timeout=FETCH_SECONDS) as answered, open(into, "wb") as writing:
        shutil.copyfileobj(answered, writing)


def _out_loud(said: str) -> None:
    print(f"        {said}")


def _failed(why: str) -> int:
    """`NOT APPLIED` rather than `FAILED`, and the difference is the point: an update that declined
    to move — nothing newer published, nothing reachable to ask — is not a command that broke."""
    return failed(f"update: NOT APPLIED — {why}")
