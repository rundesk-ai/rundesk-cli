"""What version is installed, what has been published, and moving between them.

Standard library only, and every network call is behind a seam a test can replace —
`latest` is a function passed in, so the whole of this module is exercised offline.

An update replaces the checkout in place and never touches the symlink that put
`rundesk` on your PATH, so the command keeps working across a version change.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import sys
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

REPO_SLUG = "rundesk-ai/rundesk-cli"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{REPO_SLUG}/releases/latest"
ARCHIVE_URL = f"https://github.com/{REPO_SLUG}/archive/refs/tags/{{tag}}.tar.gz"
RELEASE_URL = f"https://github.com/{REPO_SLUG}/releases/tag/{{tag}}"
HTTP_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 60
USER_AGENT = "rundesk-cli-updater"

_VERSION_RE = re.compile(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(value: str) -> tuple[int, int, int] | None:
    """`v1.2.3` and `1.2` alike; anything that is not a version at all is None."""
    match = _VERSION_RE.match(value.strip())
    if not match:
        return None
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


#: A release tag names all three parts, always. `parse_version` is deliberately forgiving —
#: it reads `1.2` so a comparison never fails on a shortened tag — and forgiveness is the
#: wrong instinct for a link: `v1.2` is a page that does not exist, and a release note nobody
#: can open is worse than none offered at all.
_RELEASE_VERSION_RE = re.compile(r"^v?(\d+\.\d+\.\d+)$")


def release_url(version: str | None) -> str | None:
    """Where what changed in a version is published, or None when it is not a version.

    Built from this repository's identity and the version itself, never read back out of a
    sentence written for a person: an outcome summary is prose, and a link derived from
    prose changes meaning the day somebody rewords it (R-UPD-46).

    A version arrives here either bare (`0.15.0`) or as the whole of what `rundesk version`
    printed (`rundesk 0.15.0`), so the last word is taken and then held to the shape a
    release tag actually has. Anything else is no link rather than a wrong one.
    """
    if not version:
        return None
    words = str(version).split()
    if not words:
        return None
    match = _RELEASE_VERSION_RE.match(words[-1])
    if not match:
        return None
    return RELEASE_URL.format(tag=f"v{match.group(1)}")


def is_newer(latest: str, local: str) -> bool:
    there, here = parse_version(latest), parse_version(local)
    # A version we cannot read is not a reason to claim an update: saying "behind"
    # on a garbled tag would send someone chasing a release that does not exist.
    if there is None or here is None:
        return False
    return there > here


#: Told apart because they need different things of the reader: one is "wait and try again",
#: the other is "nothing has been published, or you cannot see it".
UNREACHABLE = "unreachable"
NOTHING_PUBLISHED = "nothing-published"


def latest_version_online() -> tuple[str | None, str | None]:
    """The newest published release, and which kind of nothing it was when there is none.

    Both are returned rather than one being left somewhere for the caller to pick up. Which
    kind of nothing it was is part of this answer — "we could not ask" and "there is nothing
    there" send a reader somewhere completely different — and a look-up whose second half
    was a module global held whatever the last real call left in it, which is precisely
    wrong when the whole point of the seam is that a test replaces the call.

    The request carries no credentials. rundesk is published in the open, so a token would
    buy nothing but rate-limit headroom for a question asked once in a while — and an
    earlier version read GITHUB_TOKEN from the environment, which meant a machine that
    happened to have one exported sent it on a check nobody asked to authenticate.
    """
    request = urllib.request.Request(RELEASES_LATEST_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        # 404 answers plainly: either nothing is published, or this repository is not visible
        # without credentials. Reporting that as "could not reach" sends someone to check
        # their network when the answer is that there is nothing to find.
        #
        # 403 is the opposite and was lumped in with it. It means the question was refused,
        # almost always the anonymous rate limit — sixty an hour per address, which a shared
        # or NAT'd one reaches on somebody else's traffic. Answering "nothing is published"
        # there is a confident falsehood about a release that exists, and it is the same
        # mistake as reading "could not ask" as "you are current" (R-UPD-19), pointed the
        # other way. Not knowing is its own answer.
        return None, (NOTHING_PUBLISHED if err.code == 404 else UNREACHABLE)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, UNREACHABLE
    # A shape we did not expect — an array, a rate-limit page parsed as JSON — reads as
    # "could not tell", never as a crash. This runs behind whatever the user typed.
    if not isinstance(payload, dict):
        return None, UNREACHABLE
    tag = payload.get("tag_name")
    if isinstance(tag, str) and tag:
        return tag, None
    return None, UNREACHABLE


def tag_matches(tag: str, version: str) -> bool:
    """Does a release tag name the same version the command reports?

    The one rule holding the whole update story together. A release tagged differently from
    what `rundesk version` says is a release nobody can reason about: the command names one
    thing, the update it offers another, and `is_newer` compares against a number that was
    never true. Checked when a release is published, and here, so the rule itself is testable.
    """
    return tag.strip().lstrip("v") == version.strip()


def describe(current: str, latest: str | None, why: str | None = None) -> str:
    """One line, state first. Whoever reads this needs to know which of four situations
    they are in before they need anything else about it."""
    if latest is None and why == NOTHING_PUBLISHED:
        return f"{current}: NO RELEASES — nothing is published, or this install cannot see them"
    if latest is None:
        return f"{current}: UNKNOWN — could not reach GitHub to check"
    if is_newer(latest, current):
        return f"{current}: OUT OF DATE — {latest} available, run: rundesk update"
    return f"{current}: UP TO DATE"


def run(
    repo_root: Path,
    current_version: str,
    check_only: bool = False,
    latest: Callable[[], tuple[str | None, str | None]] | None = None,
    apply: Callable[[Path, str], int] | None = None,
    busy: Callable[[], list] | None = None,
    pause: Callable[[], tuple] | None = None,
    resume: Callable[[list], list] | None = None,
    carry: Callable[[], str | None] | None = None,
    provision: Callable[[], str | None] | None = None,
    plugins: Callable[[], list] | None = None,
    unfit: Callable[[], str | None] | None = None,
    relaunch: Callable[[Path, list], str | None] | None = None,
    preview: Callable[[], list] | None = None,
) -> int:
    """Report where this install stands, and move it if asked.

    `latest`, `apply` and `busy` are arguments so the decision can be tested without a
    network, a download or a gateway — the part that is easy to get wrong is which of the
    outcomes is chosen, not the tarball handling.

    They resolve here rather than in the signature: a default argument is bound
    once, when the function is defined, so naming the function there would freeze
    it and quietly ignore anything that replaced it afterwards.

    `carry` brings what is on the machine into the shape the new files expect, and says
    what went wrong rather than raising it — the same shape `pause` already uses, and the
    reason this module knows nothing of migrations, databases or agents.
    """
    published, why = (latest or latest_version_online)()
    print(describe(current_version, published, why))
    if published is None:
        return 1
    if not is_newer(published, current_version):
        # **Current is not the same as working** (R-UPD-32). An update interrupted after the
        # files landed leaves this install reporting the new version with the old
        # dependencies beside it and records nothing has moved — and every later `rundesk
        # update` said UP TO DATE, which is the one answer that stops an owner looking. The
        # way out is to run the update again, so running it again has to be the thing that
        # mends it.
        return _mend(repo_root, current_version, check_only,
                     unfit, busy, pause, resume, carry, provision, plugins)
    if check_only:
        # **What it would do, before it does it** (R-UPD-34). Said here and nowhere else,
        # because this is the one path that promises to change nothing (R-UPD-8): the
        # preview reads what is on disk and asks nothing of a network, a package index or
        # a database that does not already exist.
        for line in (preview or (lambda: []))():
            print(f"        {line}")
        return 0
    # Held around everything that follows rather than around the download alone
    # (R-UPD-26). Standing gateways down, replacing the files and moving records forward
    # are one act from the machine's point of view, and a second update reaching any part
    # of it is two updates deciding the same install's shape at once.
    try:
        with _only_one(repo_root):
            return _replace_this_install(
                repo_root, published, apply, busy, pause, resume, carry, provision,
                relaunch, plugins, was=current_version,
            )
    except Busy as err:
        print(f"update: NOT APPLIED — {err}", file=sys.stderr)
        return 1


#: How the new code is told it is finishing a window somebody else opened, and which
#: gateways are waiting to come back. Carried in the arguments rather than in a file: it is
#: true for one handover and nothing should be able to find it afterwards and act on it.
CONTINUING = "--after-replacing"


#: How the release being left tells the one replacing it what it was called.
LEAVING = "RUNDESK_UPDATE_FROM"


def _relaunch(repo_root: Path, stopped: list, was: str | None = None) -> str | None:
    """Hand the rest of the window to the release that just landed.

    Never returns when it works — this process *becomes* the new one, so its exit code is
    the update's. Returns why when the handover could not happen at all, which leaves the
    caller holding an install it can still put back.

    The right to change this install is released here, because the descriptor holding it
    closes on exec, and taken again immediately by the process that replaces this one. A
    third update slipping into that gap would be refused by the second, which is the
    outcome anyway; the alternative is passing an open lock across exec and then teaching
    the far side not to ask for one, which is more moving parts than the gap is worth.
    """
    entry = repo_root / "rundesk"
    argv = [str(entry), "update", CONTINUING, ",".join(stopped)]
    if was:
        # **The version being left, carried across on purpose** (R-PLG-44). The far side is
        # the new code and knows only what it calls itself, so without this the one line an
        # owner reads about their own update can say where they arrived and never where
        # they came from. `RUNDESK_UPDATE_VERSION` is not this: that is the target the old
        # process was aiming at, which on this path is simply where it now is.
        os.environ[LEAVING] = was
    try:
        sys.stdout.flush()
        sys.stderr.flush()
        os.execv(str(entry), argv)
    except OSError as err:
        return str(err)
    return None   # unreachable: execv either replaces this process or raises


def carry_on(repo_root: Path, stopped: list, resume=None, carry=None,
             provision=None, landed: str | None = None, plugins=None) -> int:
    """Finish a window the release before this one opened (R-UPD-33).

    The public half of the handover: whoever runs this *is* the new code, so what it does
    to an owner's records is what the release that shipped it says it should be — and
    `landed` is what the release that shipped it calls itself, which is why the caller
    states it rather than this module inferring it from a version it was never given.
    """
    try:
        with _only_one(repo_root):
            return _bring_forward(repo_root, stopped, resume, carry, provision,
                                  landed=landed, plugins=plugins,
                                  was=os.environ.get(LEAVING))
    except Busy as err:
        print(f"update: NOT APPLIED — {err}", file=sys.stderr)
        return 1


def _mend(repo_root, current_version, check_only, unfit, busy, pause, resume,
          carry, provision, plugins=None) -> int:
    """Nothing newer to move to — so is what is already here actually usable?

    The same window, with nothing to lay down: what an install is made of and what its
    agents keep are brought forward exactly as they would be for a release, because the
    state this mends is one where the files arrived and neither of those followed. Reusing
    it rather than writing a second, shorter one is deliberate — two windows would be two
    orders, and the order is the part that protects the records.
    """
    why = (unfit or (lambda: None))()
    if not why:
        return 0
    print(f"{current_version}: DOES NOT FIT — {why}", file=sys.stderr)
    if check_only:
        # Asking where this install stands never changes it (R-UPD-8), and that a check now
        # has something to complain about does not make it a command that acts.
        print("        to mend it, run: rundesk update", file=sys.stderr)
        return 1
    try:
        with _only_one(repo_root):
            return _replace_this_install(
                repo_root, current_version,
                # Already here: there is no release to fetch, only what should have
                # followed one.
                apply=lambda _root, _tag: 0,
                # Nothing arrived, so there is nobody to hand over to: this process is
                # already running the release whose dependencies and steps are about to be
                # brought forward, which is the whole condition the handover exists for.
                relaunch=lambda _root, _names, _was=None: None,
                busy=busy, pause=pause, resume=resume, carry=carry, provision=provision,
                plugins=plugins,
            )
    except Busy as err:
        print(f"update: NOT APPLIED — {err}", file=sys.stderr)
        return 1


def _replace_this_install(
    repo_root: Path,
    published: str,
    apply=None,
    busy=None,
    pause=None,
    resume=None,
    carry=None,
    provision=None,
    relaunch=None,
    plugins=None,
    was: str | None = None,
) -> int:
    """The window itself: nothing an owner runs is up between the first line and the last.

    Split out from `run` so the right to change this install is held around the whole of
    it and released once, rather than taken and let go part-way through.
    """
    # Asked before anything is fetched or laid down, and only when something is actually
    # going to be moved (R-UPD-23). An update replaces the files a running gateway is
    # made of while it is part-way through a turn — the process keeps the code it already
    # imported, so what breaks is whatever it imports *next*, minutes later, deep inside
    # a provider session, in a way that reads like anything but an update. Refusing is
    # the whole of the safety here: stopping the work would be deciding on the owner's
    # behalf that the turn was worth less than the release.
    working = (busy or (lambda: []))()
    if working:
        print(
            f"update: NOT APPLIED — work is in flight: {', '.join(sorted(working))}",
            file=sys.stderr,
        )
        print("        wait for it to finish, or stop it: rundesk stop", file=sys.stderr)
        return 1
    # Stopped before anything is laid down, and only what can be started again
    # (R-UPD-21). A gateway left running reads the new files for anything it has not
    # imported yet, and goes on serving the old code for everything it has.
    stopped, refused = (pause or (lambda: ([], None)))()
    if refused:
        print(f"update: NOT APPLIED — {refused}", file=sys.stderr)
        # Standing everything down is not one act but one per gateway, so a refusal arrives
        # with some of them already stopped — `pause` hands those back beside the reason.
        # Saying "NOT APPLIED" and leaving them down reads as "nothing happened" while an
        # owner's agents are unreachable and unnamed, which is exactly what R-UPD-22 exists
        # to prevent, on the one path that did not answer for it (R-UPD-24).
        #
        # Asked only when something actually went down. A refusal on the first gateway it
        # looked at stopped nothing, and starting a conversation with the machine about an
        # empty list is how a refusal grows a second failure of its own.
        if stopped:
            left_down = (resume or (lambda _names: []))(stopped)
            back = sorted(set(stopped) - set(left_down))
            if back:
                print(f"        brought back: {', '.join(back)}", file=sys.stderr)
            if left_down:
                print(f"        did not come back: {', '.join(sorted(left_down))}",
                      file=sys.stderr)
                print("        why: rundesk logs <name>", file=sys.stderr)
        return 1
    try:
        moved = (apply or download_and_apply)(repo_root, published)
    except BaseException:
        # An update that fell over must not also leave the machine's gateways down behind
        # it (R-UPD-22): the files are as they were, so the old code they are made of is
        # still there to come back onto.
        (resume or (lambda _names: []))(stopped)
        raise
    if moved == 0:
        # **Everything below here belongs to the release that just landed** (R-UPD-33), so
        # this process hands over to it rather than going on. Nothing re-executed before,
        # and the cost was invisible: `migration.found()` reads `src/migrations/` off disk
        # at the moment it is asked, so the *new* step files were being run by the *old*
        # runner. Every future release quietly depended on that pairing working. The
        # interpreter is no better off — `rundesk` puts the virtualenv on `sys.path` when
        # the process starts, so anything installed a moment from now is invisible to this
        # one, and a module already imported stays the version it was.
        #
        # Does not return when it works. When it cannot — a release whose entry point will
        # not start is exactly the case worth surviving — this process is still the old
        # code, still holds everything it needs, and puts the release back itself.
        went = (relaunch or _relaunch)(repo_root, stopped, was)
        if went:
            print(f"update: NOT APPLIED — the new release would not start: {went}",
                  file=sys.stderr)
            # Branched on, not assumed. Putting the release back can itself fail part-way,
            # which is the one state `HalfReplaced` exists to name — and saying "back on the
            # version it was" there sends an owner to try again on an install that is a mix
            # of two releases. The path below this one always got that right; this one, the
            # newest, said it unconditionally.
            if _undo(repo_root):
                print("        this install is back on the version it was; try again",
                      file=sys.stderr)
            else:
                print("        the release could not be put back — reinstall this install",
                      file=sys.stderr)
            (resume or (lambda _names: []))(stopped)
            return 1
        return _bring_forward(repo_root, stopped, resume, carry, provision,
                              landed=published, plugins=plugins, was=was)
    # The release never landed, so there is nothing to bring forward and nothing to put
    # back — only whatever was stood down, which comes back onto the code it was already on.
    left_down = (resume or (lambda _names: []))(stopped)
    if left_down:
        print(
            f"update: FAILED, and did not come back: {', '.join(sorted(left_down))}",
            file=sys.stderr,
        )
        print("        why: rundesk logs <name>", file=sys.stderr)
        return 1
    return moved


def _bring_forward(repo_root: Path, stopped: list, resume=None, carry=None,
                   provision=None, landed: str | None = None, plugins=None,
                   was: str | None = None) -> int:
    """What an install is made of, then what its agents keep, then everything back up.

    The one window where nothing is up and the new files are already down. Reached twice —
    straight through when a release lands, and again by the process that release handed
    over to — so it is written once: two copies would be two orders, and the order is the
    part that protects the records.

    **What an install is made of comes forward first** (R-UPD-30). Two reasons, in order of
    weight. Records are the irreplaceable thing, so the failure that can happen without
    touching them should happen first: a build that fails here leaves every agent's records
    exactly as they were, and running the update again is the whole of the fix. And a step
    that one day needs a dependency can only have one if they are already there — nothing
    forces that today, and the order that allows it costs nothing.
    """
    went_wrong = (provision or (lambda: None))()
    where = "what rundesk is made of"
    if not went_wrong:
        went_wrong = (carry or (lambda: None))()
        where = "moving records forward"
    if went_wrong:
        # **The release is put back and the agents come back onto it** (R-UPD-31).
        # Migrations are one way, so reverting the program alone would strand an agent
        # already carried — its records newer than the code that must read them, refused
        # on open (R-MIG-10). What makes coming back safe is that `carry` puts every
        # agent's records back as well, so the machine is what it was before the update.
        print(f"update: NOT APPLIED — {where} could not be brought forward: {went_wrong}",
              file=sys.stderr)
        if _undo(repo_root):
            print("        this install is back on the version it was; try again",
                  file=sys.stderr)
        else:
            print("        the release could not be put back — reinstall this install",
                  file=sys.stderr)
        print("        why: rundesk logs <name>", file=sys.stderr)
        left_down = (resume or (lambda _names: []))(stopped)
        if left_down:
            print(f"        did not come back: {', '.join(sorted(left_down))}",
                  file=sys.stderr)
        return 1
    # Nothing is going back now: the release is on disk, what it needs is installed and
    # every agent's records are in the shape it expects. Only here does the copy of what
    # was there go, because until this line it is the only way back (R-UPD-31).
    _keep(repo_root)
    # **After the records and before anything comes back up, and it can never fail this**
    # (R-PLG-15). A plugin is a stranger's release: it is moved forward in the same window,
    # because a step of its own needs every gateway down exactly as rundesk's do — but what
    # it does is reported rather than acted on, and one that cannot be moved is held back
    # and named rather than taking an owner's agents down with it.
    #
    # **Done here, said at the end.** The work has to happen while nothing is up; the
    # account of it belongs after the release line, so an owner reads one ordered list —
    # rundesk, then each plugin — rather than plugin news arriving before the news that the
    # release landed at all (R-PLG-44).
    moved = (plugins or (lambda: []))()
    left_down = (resume or (lambda _names: []))(stopped)
    if left_down:
        print(
            f"update: applied, but did not come back: {', '.join(sorted(left_down))}",
            file=sys.stderr,
        )
        print("        why: rundesk logs <name>", file=sys.stderr)
        # Said even here: the release did land and the plugins were moved, and an owner
        # chasing a gateway that did not come back still needs to know what else changed
        # underneath it.
        _say_what_moved(landed, moved, was)
        return 1
    # **Said only here** (R-UPD-46, R-UPD-47), which is the one line in this module that is reached
    # exactly when a release is on disk, its dependencies are in place, every agent's
    # records are in the shape it expects and every gateway is back. Every failure and
    # rollback above returns before it, so nothing that did not land can say it did.
    _say_what_landed(landed)
    _say_what_moved(landed, moved, was)
    return 0


#: The narrowest the name column goes, so a single short name still reads as a column.
NAME_ROOM = 4


def _say_what_moved(landed: str | None, moved: list, was: str | None = None) -> None:
    """What this update moved: rundesk, then the plugins under it.

    **Two labels, rows, and one word each.** What a reader needs is which things moved and
    which did not, and the word carries it: `skipped` is a plugin that was not moved and
    works fine where it is, `failed` is one that is now unreachable. Why it failed is a
    question with an answer somewhere it has room — `rundesk plugins` — rather than a
    sentence trailing off the end of a row.

    Silent on a machine with no plugins: an owner who has never installed one sees exactly
    what they saw before this existed (R-PLG-44).
    """
    if not moved:
        return
    # Bare digits, because every plugin beside it is bare: a table where one row says
    # `v0.16.0` and the next says `1.5.0` makes a reader wonder what the `v` means.
    rows = [("rundesk", (was or "").lstrip("v"), (landed or "").lstrip("v"),
             "updated" if landed else "up to date")]
    rows += [(one.name, one.was or "", one.now or "", one.state) for one in moved]
    room = max(NAME_ROOM, max(len(name) for name, *_ in rows))
    span = max(len(_between(was, now)) for _n, was, now, *_ in rows)
    print()
    for at, (name, before, after, state) in enumerate(rows):
        if at == 1:
            print()
            print("plugins:")
        # rundesk stands at the margin and the plugins sit under their label, so the shape
        # says which is which before a word is read.
        print(f"{'  ' if at else ''}{name.ljust(room)}  "
              f"{_between(before, after).ljust(span)}  {state}")


def _between(was: str | None, now: str | None) -> str:
    """Where something came from and where it got to, or the one version anybody knows."""
    if was and now and was != now:
        return f"{was} -> {now}"
    return was or now or "-"


def _say_what_landed(landed: str | None) -> None:
    """Which release is now installed, and where to read what changed in it."""
    if not landed:
        return
    print(f"update: applied — now on {landed}")
    where = release_url(landed)
    if where:
        print(f"        what changed: {where}")


#: Which installs *this process* already holds the right to change. `flock` is held per
#: open file, not per process, so a second one taken here would refuse the first — and the
#: window takes it once around everything while the download inside it asks again.
_HELD: set = set()


@contextlib.contextmanager
def _only_one(repo_root: Path):
    """Hold the right to change this install, or say who already has it.

    Two updates running at once each replace what the other is mid-way through reading.
    The lock is advisory and only updates take it: a `rundesk version` racing an update is
    left to the swap being a rename, which is as close to instant as this gets.

    **Held around the whole window, not only the download** (R-UPD-26). It used to be taken
    inside the replacement alone, so standing every gateway down, moving records forward and
    bringing them back all ran unguarded — and a second update could stand gateways down
    while the first was part-way through moving an agent's records.
    """
    lock = repo_root / ".update.lock"
    key = str(lock)
    if key in _HELD:
        yield          # already this process's; asking the kernel again would refuse us
        return
    handle = open(lock, "w")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Busy(f"another update is already running (holding {lock})")
        _HELD.add(key)
        yield
    finally:
        _HELD.discard(key)
        handle.close()


class Busy(Exception):
    """Something else is already changing this install."""


def download_and_apply(repo_root: Path, tag: str) -> int:
    """Fetch that tag and lay it over the checkout, leaving the PATH symlink alone."""
    try:
        with _only_one(repo_root):
            return _download_and_apply(repo_root, tag)
    except Busy as err:
        print(f"FAILED — could not update: {err}", file=sys.stderr)
        return 1


def _download_and_apply(repo_root: Path, tag: str) -> int:
    # An update replaces the program that is running it, over a network, on somebody's
    # machine. Saying which step is under way costs nothing and is the difference between
    # waiting and wondering whether to reach for Ctrl-C — which is the one thing that used
    # to break an install.
    url = ARCHIVE_URL.format(tag=tag)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with tempfile.TemporaryDirectory() as work:
        archive = Path(work) / "rundesk.tar.gz"
        print(f"{tag}: downloading", flush=True)
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                archive.write_bytes(response.read())
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            print(f"{tag}: FAILED — could not download: {err}", file=sys.stderr)
            return 1

        unpacked = Path(work) / "unpacked"
        unpacked.mkdir()
        print(f"{tag}: unpacking {_size(archive)}", flush=True)
        try:
            with tarfile.open(archive) as tar:
                safe_extract(tar, unpacked)
        except (tarfile.TarError, ValueError, OSError) as err:
            print(f"{tag}: FAILED — the download is not shaped like a release: {err}", file=sys.stderr)
            return 1

        roots = [p for p in unpacked.iterdir() if p.is_dir()]
        if len(roots) != 1:
            print(f"{tag}: FAILED — the download is not shaped like a release", file=sys.stderr)
            return 1
        print(f"{tag}: installing into {repo_root}", flush=True)
        try:
            _copy_over(roots[0], repo_root)
        except HalfReplaced as err:
            # The only path here that a person has to act on, so it does not read like the
            # ordinary failure above it: running the update again cannot mend an install
            # that is partly one release and partly another (R-UPD-25).
            print(f"{tag}: FAILED — {err}", file=sys.stderr)
            print("        this install is not safe to run; reinstall it:", file=sys.stderr)
            print("        curl -fsSL https://github.com/" + REPO_SLUG
                  + "/releases/latest/download/install.sh | bash", file=sys.stderr)
            return 1
        except OSError as err:
            # What was already swapped has been put back, so this is the release it was on
            # before — the same install, and running the update again is the whole of the fix.
            print(f"{tag}: FAILED — could not install: {err}", file=sys.stderr)
            print("        the install is as it was; try again", file=sys.stderr)
            return 1

    print(f"{tag}: UPDATED — run 'rundesk version' to confirm")
    return 0


def readable(held_bytes: int) -> str:
    """A number of bytes as a person reads it — the one place that is decided.

    Here rather than beside either caller, because there are two and they are in different
    modules: how big a release is while it downloads, and how big a backup is in a listing.
    Written twice, they disagree the day one of them changes where megabytes begin — and a
    reader comparing "11 KB" against "0.0 MB" has no way to tell which of the two moved.
    """
    kb = held_bytes / 1024
    return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"


def _size(path: Path) -> str:
    """A downloaded size a person can read, so 'unpacking' names something real."""
    try:
        return readable(path.stat().st_size)
    except OSError:
        return "the release"


def safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Refuse a member that would land outside `dest` — an archive is untrusted input.

    **Public because a second caller needs exactly this**, not a second copy of it: a plugin
    arrives as a stranger's archive too, and a traversal guard written twice is one that
    stops being written the same way. `plugin.unpack` calls this one.

    Checking each member's own name is not enough. A link member's *target* is a second way
    out: an archive carrying a symlink to somewhere outside `dest`, followed by a file whose
    path runs through it, writes wherever the link points — the name check passes both,
    because at the time it runs the link does not exist yet for `resolve()` to follow.
    Verified against Python 3.9, the floor this project supports.

    The standard library only started refusing this by default in 3.14, so on every version
    this project targets the guard has to be ours.
    """
    root = dest.resolve()
    for member in tar.getmembers():
        if not _lands_inside(root, member.name):
            raise ValueError(f"refusing to extract outside the destination: {member.name}")
        if member.issym() or member.islnk():
            link = member.linkname
            if PurePosixPath(link).is_absolute():
                raise ValueError(f"refusing a link to an absolute path: {member.name} -> {link}")
            # A relative target is resolved from the directory the link sits in.
            if not _lands_inside(root, str(PurePosixPath(member.name).parent / link)):
                raise ValueError(f"refusing a link that points outside: {member.name} -> {link}")
    tar.extractall(dest)


def _lands_inside(root: Path, name: str) -> bool:
    """Whether `name`, taken relative to `root`, stays under it once '..' is worked out."""
    if PurePosixPath(name).is_absolute():
        return False
    target = os.path.normpath(str(root / name))
    return target == str(root) or target.startswith(str(root) + os.sep)


#: Laid down with the bit set, because a release archive does not carry one.
EXECUTABLE = {"rundesk", "install.sh"}


class HalfReplaced(Exception):
    """A replacement failed *and* putting back what was there failed too.

    The one outcome nothing else here can describe: the install is neither the version it
    was nor the version it was going to be. Named rather than folded into the ordinary
    failure, because the answer is not "run it again" — it is a person and a backup.
    """


def _copy_over(src: Path, dst: Path) -> None:
    """Lay the new tree over the old, leaving anything the release does not ship.

    Every replacement is built beside its target first and swapped in with a rename, so an
    interruption leaves either the old thing or the new one and never half of either.

    The shape this replaces removed each directory and then copied the new one into place.
    That left `src/rundesk` — the package implementing update, version and uninstall —
    absent for the whole duration of a copy. A Ctrl-C or a full disk inside that window
    bricked every command, including the one that could have repaired it.

    **Each swap is atomic; the loop over them was not** (R-UPD-25). A failure part-way
    through left some paths on the new release and the rest on the old — `rundesk` from one
    version and `src/` from another — and the caller then brought every gateway back onto
    it. Per-item atomicity is not consistency across items, so what was already swapped is
    put back before the failure is reported, and the install is the version it started as.
    """
    staged: list[tuple[Path, Path]] = []
    swapped: list[tuple[Path, Path | None]] = []
    try:
        for item in sorted(src.iterdir()):
            pending = dst / f".{item.name}.incoming"
            _discard(pending)
            if item.is_dir():
                shutil.copytree(item, pending)
            else:
                shutil.copy2(item, pending)
                if item.name in EXECUTABLE:
                    pending.chmod(0o755)
            staged.append((pending, dst / item.name))
        # Everything is written and complete. Only now does anything the running install
        # depends on move, and each move is a rename that either happened or did not.
        try:
            for pending, target in staged:
                # Written down *before* the move that could fail, so nothing this walk set
                # aside is ever outside what the revert below knows about. A swap that put
                # its own house in order and then raised kept that knowledge to itself, and
                # a failure inside its recovery stranded the only copy of what was there.
                outgoing = _set_aside(target)
                swapped.append((target, outgoing))
                os.rename(pending, target)
        except BaseException:
            stuck = _put_back(swapped)
            if stuck:
                raise HalfReplaced(
                    "the release was only partly laid down and what was there could not be "
                    f"put back: {', '.join(stuck)}"
                ) from None
            raise
        # **What was replaced is left where it was set aside**, for `_keep` to let go of or
        # `_undo` to put back (R-UPD-31). Discarding it here would make the replacement
        # atomic and the update as a whole one-way: what an install is made of and what its
        # agents keep both still have to come forward, and either can still fail.
    finally:
        for pending, _ in staged:
            _discard(pending)


def _set_aside(target: Path) -> Path | None:
    """Move whatever stands at `target` out of the way, and say where it went.

    None when the release ships something this install did not have — there was nothing to
    set aside, and putting it back means taking the new thing away again.

    What is set aside is the caller's to discard once the replacement is known to be good.
    Letting go of it here would make each swap atomic and the update as a whole one-way.
    """
    outgoing = target.with_name(OUTGOING.format(name=target.name))
    if outgoing.exists() or outgoing.is_symlink():
        # **An earlier attempt was interrupted after setting this aside**, so *that* copy is
        # the version this install was really on, and what stands at `target` now is however
        # far that attempt got. Discarding it and setting the target aside in its place —
        # which is what this used to do — replaced the true old content with the new, and a
        # later `_undo` then restored new over new and reported that the install was back on
        # the version it was. Keep the older one; the newer is the disposable half.
        _discard(target)
        return outgoing
    if not (target.exists() or target.is_symlink()):
        return None
    os.rename(target, outgoing)
    return outgoing


#: How a replaced item is named while the update that replaced it is still being proved.
OUTGOING = ".{name}.outgoing"


def _set_aside_here(repo_root: Path) -> list:
    """Everything this install has set aside, as (where it belongs, where it is).

    Found by looking rather than carried along, so it survives the update being asked
    about by a process other than the one that replaced the files.
    """
    found = []
    for outgoing in sorted(repo_root.glob(".*.outgoing")):
        name = outgoing.name[1: -len(".outgoing")]
        if name:
            found.append((repo_root / name, outgoing))
    return found


def _keep(repo_root: Path) -> None:
    """Let go of what was replaced, now that the whole update is proved (R-UPD-31)."""
    for _target, outgoing in _set_aside_here(repo_root):
        _discard(outgoing)


def _undo(repo_root: Path) -> bool:
    """Put this install back on the release it was, and say whether that worked.

    Asked when what an install is *made of* or what its agents *keep* could not be brought
    forward. Both are failures the release itself cannot be blamed for and both leave a
    machine on a version whose dependencies or records do not match it, so the release goes
    back rather than the owner being left to work out which half landed.
    """
    return not _put_back(_set_aside_here(repo_root))


def _put_back(swapped: list) -> list:
    """Undo the swaps already made, and say which could not be undone.

    Newest first, so a path that was set aside twice — which nothing here does today, and
    which a future release shipping a name twice would — ends on the oldest thing.

    Every failure is caught rather than the first one ending the walk: a revert that gave up
    half way is the state this exists to prevent, so the remaining paths are still tried and
    what is genuinely stuck is named.
    """
    stuck = []
    for target, outgoing in reversed(swapped):
        try:
            _discard(target)
            if outgoing is not None:
                os.rename(outgoing, target)
        except OSError:   # noqa: BLE001 — named and reported, never swallowed
            stuck.append(target.name)
    return sorted(stuck)


def _discard(path: Path) -> None:
    """Remove a leftover staging path, whatever it turned out to be."""
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists() or path.is_symlink():
        try:
            path.unlink()
        except OSError:
            pass
