"""Finding the programs that stand outside rundesk, and reading what one printed.

An adapter is a **program, never a plugin**, and rundesk has two kinds of them: a channel adapter
holds a connection to somebody else's service open, and a provider adapter runs an agent's brain.
They answer entirely different questions, and everything they have in common is here.

Three things follow from adapter-as-program, and they are the same three for both kinds. Rundesk does
not load somebody else's code into the gateway hosting every other agent. An adapter author is not
obliged to write Python. And **a vendor library lives on the far side of this seam and never enters
the gateway** — reaching a chat service needs that service's package, and the only reason that is
compatible with a product whose own code imports nothing is that the import happens in a different
process.

## Where one is found

**A bare name resolves among the ones that ship, then among the ones this install has been given;
anything with a separator in it is used as a path.** So a shipped name is the release's own, a bare
name an install has been given is the owner's, and `/Users/me/work/thing` is a program being written
right now.

Which two directories those are is the caller's, because the two kinds do not share a namespace: a
channel called `discord` and a provider called `discord` are different programs, and one directory
holding both would make them one file.

Found by looking rather than listed. A registry of names beside a directory of programs is two
things to keep in step, and the failure when they drift is the worst kind: one says the adapter is
known and the other cannot produce it.

## Which interpreter runs it

**Decided here and handed over on `PATH`, never discovered by the adapter.** The build this replaces
had each adapter find its own virtualenv by counting parent directories, the count was wrong for a
whole release, and nothing failed until somebody added a channel.

It goes on `PATH` rather than in front of the argv, and that is the part worth getting right: an
adapter is an executable with a shebang of its own and may be a shell script, so running one through
`python3` is nonsense. Putting the install's own `bin` first means `#!/usr/bin/env python3` resolves
to the install's own interpreter, a shell adapter is unaffected, and neither had to be told anything.

## Reading what one printed

Everything an adapter prints is **an unvetted program's output**, so nothing here raises for
anything it finds there. A value of the wrong shape, a stream with a warning in front of the answer,
a program that printed nothing at all — each comes back as the least it could mean, because the
caller's job is to report a refusal and not to catch a traceback.

May depend on `utils`.
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rundesk.core import paths
from rundesk.utils import programs

#: What an adapter is started with, from this process's own environment. Everything else is dropped:
#: an adapter is handed what it needs by name, so a variable it did not ask for is one it cannot come
#: to depend on by accident — and the thing most likely to be in there is a credential belonging to
#: somebody else entirely.
CARRIED = ("PATH", "HOME", "TMPDIR", "TZ", "LANG", "LC_ALL")

#: How much of what a program printed is put into a sentence somebody reads.
REASON_AT_MOST = 200


class NotRunnable(Exception):
    """There is no program where this adapter said there would be one, said with where it was looked.

    The only way finding one fails. **Not recognising a name is not a failure** — an adapter rundesk
    has never heard of is the case this whole seam exists for, and the single question is whether
    something runnable stands where the name resolved to.
    """


def where_the_packages_are() -> Optional[Path]:
    """The install's own virtualenv, or `None` when it has not got one.

    **This goes on the front of `PATH` and is never prepended to the argv.** An adapter is an
    executable with a shebang of its own — it may be a shell script, and running one through
    `python3` is nonsense — so the interpreter is chosen by what `#!/usr/bin/env python3` resolves
    to, which is a thing rundesk decides and the adapter never has to.

    It can be absent: a machine with no network has a working install and no packages. An adapter
    needing one then works only where somebody has put it on the path themselves, and whatever asks
    the adapter a question reports the `ImportError` as the refusal it is rather than pretending
    otherwise.
    """
    theirs = paths.app() / ".venv" / "bin"
    return theirs if theirs.is_dir() else None


def runnable(at: Path) -> bool:
    """Whether this is a file somebody could actually run.

    Both halves asked, because they fail differently and a caller told "not there" about a program
    that is there and not executable goes looking in the wrong place entirely.
    """
    try:
        return at.is_file() and os.access(str(at), os.X_OK)
    except OSError:
        return False


def where(name: str, shipped_in: str, given_in: str) -> Path:
    """The program behind `name`. `NotRunnable` when there is not one, saying where it was looked for.

    `shipped_in` is a directory under `paths.code()` and `given_in` one under `paths.data()`, and the
    caller names both because the two kinds of adapter do not share a namespace.

    A bare name is looked for among the ones that ship and then among the ones this install has been
    given, in that order — a release's own adapter is the one somebody gets by typing its name, and
    an install cannot quietly shadow it.
    """
    if os.sep in name or (os.altsep and os.altsep in name):
        # **Resolved, and that is not tidiness.** `Path("./quiet")` normalises to `quiet` — the
        # separator that got us into this branch is gone — and a bare name handed to `Popen` is
        # looked for on `PATH`, so the refusal reads `No such file or directory: 'quiet'` about a
        # program standing right there. `./name` is the first spelling anybody tries.
        at = Path(name).expanduser().resolve()
        if runnable(at):
            return at
        raise NotRunnable(f"{at} is not a program that can be run")

    looked = [paths.code() / shipped_in / name, paths.data() / given_in / name]
    for at in looked:
        if runnable(at):
            return at
    raise NotRunnable(
        f"there is no {name} adapter on this install — looked in "
        + " and ".join(str(one.parent) for one in looked))


def known(shipped_in: str, given_in: str) -> List[str]:
    """Every adapter of one kind this install can run, in name order, found by looking."""
    found = set()
    for at in (paths.code() / shipped_in, paths.data() / given_in):
        try:
            found.update(one.name for one in at.iterdir() if runnable(one))
        except OSError:
            continue                      # a directory that is not there yet is not a failure
    return sorted(found)


def environment(also: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """What an adapter is started with: a named handful, plus whatever it was given.

    Built rather than inherited. An adapter that could read this process's whole environment is one
    that comes to depend on something nobody meant to hand it — and a blocklist over an inherited
    environment is a list somebody has to keep true, where a built one has nothing to keep.
    """
    built = {name: os.environ[name] for name in CARRIED if name in os.environ}
    built["TERM"] = "dumb"                # nothing here is a terminal, and nothing may draw on one
    packages = where_the_packages_are()
    if packages is not None:
        # In front, so `#!/usr/bin/env python3` resolves to the install's own interpreter and the
        # adapter never has to work out where its packages live. See `where_the_packages_are`.
        built["PATH"] = os.pathsep.join([str(packages), built.get("PATH", os.defpath)])
    built.update(also or {})
    return built


def asked_offline(at: Path, within: float, env: Dict[str, str],
                  running: Optional[Callable[..., programs.Ran]] = None) -> Dict[str, Any]:
    """Ask an adapter what it can do, and read the object it printed. `{}` for every other answer.

    Both kinds of adapter answer this question and both answer it the same way, so how a *refusal*
    is read lives here rather than twice: an adapter that does not recognise the flag and does
    something else can do nothing, which is a complete and honest answer and never an error. Every
    failure — a program that would not start, a non-zero exit, output that is not an object — is an
    empty mapping, so a caller reads a missing field as the least capable answer and never has to
    tell "it said no" from "it would not say".

    What each kind *asks with* stays with that kind: a provider is asked with the settings its turn
    will run under, and a channel is not. That is the difference between the two contracts, and it
    is the argument rather than the body.

    `running` is resolved inside the body rather than bound in the signature: a default bound at
    definition is decided once, when the module is imported, and nothing can reach past it.
    """
    ran = (running or programs.run)([str(at), "--capabilities"], within, env=env)
    if ran.trouble or ran.code != 0:
        return {}
    said = printed_object(ran.out)
    return said if isinstance(said, dict) else {}


def printed_object(said: str) -> Any:
    """The JSON object an adapter printed, or `None`.

    **The last non-blank line, not the whole of standard output.** A program that printed a warning
    before its answer has still answered, and reading the whole stream would throw away a perfectly
    good reply because something upstream was chatty.
    """
    whole = said.strip()
    if not whole:
        return None
    try:
        return json.loads(whole)
    except ValueError:
        pass
    for line in reversed(said.splitlines()):
        if line.strip():
            try:
                return json.loads(line)
            except ValueError:
                return None
    return None


def last_said(said: str) -> str:
    """The last thing a program said before it stopped, for putting in a sentence.

    Bounded, because this ends up in a message somebody reads: a program that wrote a megabyte of
    traceback would otherwise fill the screen with the least useful part of it.
    """
    each = [line.strip() for line in said.splitlines() if line.strip()]
    return each[-1][:REASON_AT_MOST] if each else ""


def as_list(said: Any) -> List[Any]:
    """Whatever an adapter said, as a list — one thing said alone is a list of one.

    An adapter that needs a single credential naming it as a string rather than as a list of one is
    not making a mistake, and refusing it would be this side being pedantic about a shape it can see
    through.
    """
    if said is None:
        return []
    return list(said) if isinstance(said, (list, tuple)) else [said]


def as_mapping(said: Any) -> Dict[str, Any]:
    """Whatever an adapter said, as a mapping — `{}` when it said something else entirely.

    `said.get("secret", {})` is not this: a default applies only when the key is *absent*, so an
    adapter answering `"secret": "A_TOKEN"` handed a string to `.get` and raised `AttributeError`
    out of the one function whose whole job is to turn an unvetted program's output into an answer.
    """
    return said if isinstance(said, dict) else {}


def as_text(said: Any) -> Optional[str]:
    """A value an adapter reported, as text, or `None` when it said nothing at all.

    Said-nothing and said-empty are different answers, and collapsing them here would make an adapter
    that reported no place look like one that reported an empty one.
    """
    return None if said is None else str(said)
