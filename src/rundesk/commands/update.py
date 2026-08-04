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
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from rundesk import __version__
from rundesk.core import config, paths
from rundesk.exits import FAILED, OK
from rundesk.lifecycle import home, migration, release, tree

FETCH_SECONDS = 60

#: How long the newly installed release is given to settle the install. Generous: a migration step
#: may legitimately move a lot of files.
SETTLE_SECONDS = 300


def cmd_update(_args: argparse.Namespace, asking=None, fetching=None) -> int:
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
    home.prepare(saying=_out_loud)

    fresh = not config.where(paths.data()).exists()
    try:
        if fresh:
            config.write_fresh(paths.data())
        else:
            config.fill_in(paths.data())
    except config.Unreadable as why:
        return _failed(str(why))

    if fresh:
        # Nothing to carry: the directories were made correctly a moment ago, and the steps describe
        # changes from releases this install never had.
        migration.stamp_without_running(paths.data())
        return OK

    gone_wrong = migration.carry(paths.data(), saying=_out_loud)
    if gone_wrong:
        return _failed(gone_wrong)
    return OK


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
    try:
        ended = subprocess.run([sys.executable, "-c", _SETTLE, str(app / "src")], text=True,
                               stdin=subprocess.DEVNULL, capture_output=True,
                               timeout=SETTLE_SECONDS)
    except OSError as why:
        return f"the installed release could not be run: {why}"
    except subprocess.TimeoutExpired:
        return f"the installed release did not finish within {SETTLE_SECONDS} seconds"
    if ended.stdout:
        sys.stdout.write(ended.stdout)
    if ended.returncode != 0:
        return (ended.stderr or f"it ended {ended.returncode}").strip()
    return ""


def _brought_down(tag: str, into: Path, fetching=None) -> Path:
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
                pointed = (settled.parent / member.linkname).resolve()
                if into.resolve() not in pointed.parents:
                    raise ValueError(f"{member.name} points outside the download")
        held.extractall(into)

    inside = [at for at in into.iterdir() if at.is_dir()]
    for at in inside:
        if (at / "rundesk").is_file() and (at / "src" / "rundesk").is_dir():
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
    print(f"update: NOT APPLIED — {why}", file=sys.stderr)
    return FAILED
