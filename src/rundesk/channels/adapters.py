"""The program behind a channel: finding it, and the two questions asked of it before it is trusted.

An adapter is a **program, never a plugin**, and three things follow that are worth naming together.
Rundesk does not load somebody else's code into the gateway hosting every other agent. An adapter
author is not obliged to write Python. And — the one that decides it on this platform — **a vendor
library lives on the far side of this seam and never enters the gateway**: reaching Discord needs
`discord.py`, and the only reason that is compatible with a product whose own code imports nothing
is that the import happens in a different process.

## Where one is found

The same rule the provider layer already publishes: **a bare name resolves among the ones that ship,
then among the ones this install has been given; anything with a separator in it is used as a path.**
So `discord` is the shipped adapter, `my-thing` is one somebody dropped into `data/adapters/`, and
`/Users/me/work/thing` is a program being written right now.

Found by looking rather than listed. A registry of names beside a directory of programs is two
things to keep in step, and the failure when they drift is the worst kind: one says the adapter is
known and the other cannot produce it, so a channel is offered and then cannot start.

## Which interpreter runs it

**Decided here and handed over on `PATH`, never discovered by the adapter.** The build this replaces
had each adapter find its own virtualenv by counting parent directories, the count was wrong for a
whole release, and nothing failed until somebody added a channel.

It goes on `PATH` rather than in front of the argv, and that is the part worth getting right: an
adapter is an executable with a shebang of its own and may be a shell script, so running one through
`python3` is nonsense. Putting `app/.venv/bin` first means `#!/usr/bin/env python3` resolves to the
install's own interpreter, a shell adapter is unaffected, and neither had to be told anything.

**`lifecycle.packages` builds that virtualenv**, on every `install` and every `update`, from the
`requirements.txt` of the tree that just landed. `lifecycle.tree` refuses to *copy* one, which is the
other half of the same rule: an environment holds absolute paths and is built at its destination
rather than carried there.

It can be absent — a machine with no network has a working install and no packages, which
`packages.built` reports without failing the install. An adapter needing one then works only where
somebody has put it on the path themselves, and `checked` reports the `ImportError` as the refusal it
is rather than pretending otherwise.

## Two questions, both bounded, both before anything is written down

**`--capabilities`** is asked offline: no account, no network, the same answer every time. It is what
lets a fidelity difference be a fact rather than a guess — an adapter that cannot edit a message is
told apart from one that can and did not.

**`--check`** connects, signs in, and reports what it reached. **Nothing about a channel is written
down until it says so.** An agent whose channel is misconfigured has to find out while somebody is
standing at a terminal, not at three in the morning when they ask it something.

**`ok: false` is an answer and exits `0`.** What is read is the object, not the exit code: a program
that dies without printing one *failed*, and one that printed `ok: false` *refused*, and those lead
somewhere different. Both are bounded, because this is the one place rundesk runs an unvetted
program while a person waits.

May depend on `agents`, `core` and `utils`.
"""

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

from rundesk.core import paths
from rundesk.utils import programs

#: Where the adapters that ship stand, under whatever `paths.code()` resolves to, and where the ones
#: an install has been given stand. Two places and no third: one is part of the release and is
#: replaced by an update, the other is the owner's and is never touched by one.
SHIPPED_IN = "channels"
GIVEN_IN = "adapters"

#: How long `--capabilities` may say nothing, and how long it may take in total. It is a question
#: whose answer the adapter already knows, asked with no network and no account — so a minute of
#: silence is already generous, and the ceiling exists because this is the one place an unvetted
#: program runs before anything has been written down.
CAPABILITIES_WITHIN = 60.0

#: How long `--check` may take. Longer, because it signs in to somebody else's service over somebody
#: else's network — and still finite, because a person is standing at a terminal waiting for it.
CHECK_WITHIN = 300.0

#: What is carried into an adapter's environment from this one. Everything else is dropped: an
#: adapter is handed what it needs by name, so a variable it did not ask for is one it cannot come
#: to depend on by accident.
CARRIED = ("PATH", "HOME", "TMPDIR", "TZ", "LANG", "LC_ALL")


class NotRunnable(Exception):
    """No program stands behind this channel, said with where it was looked for.

    Named apart from `Refused` because the answer is different: a channel whose adapter is missing
    is a channel that cannot start until something is installed, not one somebody configured wrongly.
    """


class Checked(NamedTuple):
    """What an adapter said when it was asked whether it could reach what it was pointed at.

    `ok` is the field to read first, and while it is `False` nothing else here means anything except
    `why`. That is the shape rather than an exception because a refusal is an *answer* — the adapter
    connected, was told no, and said so — and turning it into a traceback would lose the sentence
    the person at the terminal needs.
    """

    ok: bool
    describes: str
    notify_place: Optional[str]
    settings: str
    secret_names: List[str]
    invite: str
    why: str


def where_the_packages_are() -> Optional[Path]:
    """The install's own virtualenv, or `None` when it has not got one.

    **This goes on the front of `PATH` and is never prepended to the argv.** An adapter is an
    executable with a shebang of its own — it may be a shell script, and running one through
    `python3` is nonsense — so the interpreter is chosen by what `#!/usr/bin/env python3` resolves
    to, which is a thing rundesk decides and the adapter never has to.

    Decided here rather than by the adapter, for the reason the module docstring gives: the previous
    build let each adapter count parent directories to find its virtualenv, the count was wrong for
    a whole release, and nothing failed until somebody added a channel.
    """
    theirs = paths.app() / ".venv" / "bin"
    return theirs if theirs.is_dir() else None


def where(kind: str) -> Path:
    """The program behind `kind`. `NotRunnable` when there is not one, saying where it was looked for.

    Anything with a separator is a path and is used as one, so an adapter being written right now
    needs nothing installed anywhere. A bare name is looked for among the ones that ship and then
    among the ones this install has been given, in that order — a release's own adapter is the one
    somebody gets by typing its name, and an install cannot quietly shadow it.
    """
    if os.sep in kind or (os.altsep and os.altsep in kind):
        at = Path(kind).expanduser()
        if _runnable(at):
            return at
        raise NotRunnable(f"{at} is not a program that can be run")

    looked = [paths.code() / SHIPPED_IN / kind, paths.data() / GIVEN_IN / kind]
    for at in looked:
        if _runnable(at):
            return at
    raise NotRunnable(
        f"there is no {kind} adapter on this install — looked in "
        + " and ".join(str(one.parent) for one in looked))


def known() -> List[str]:
    """Every adapter this install can run, in name order, found by looking rather than listed."""
    found = set()
    for at in (paths.code() / SHIPPED_IN, paths.data() / GIVEN_IN):
        try:
            found.update(one.name for one in at.iterdir() if _runnable(one))
        except OSError:
            continue                      # a directory that is not there yet is not a failure
    return sorted(found)


def capabilities(kind: str, running: Optional[Callable[..., programs.Ran]] = None) -> Dict[str, Any]:
    """What this adapter says it can do. `{}` when it would not say, which is a whole answer.

    **Asked rather than assumed, and never guessed from a name.** An adapter that does not recognise
    the flag and does something else can do nothing, which is a complete answer and not an error —
    so every failure here is an empty mapping rather than an exception, and the caller reads a
    missing field as the least capable answer.

    Resolved inside the body rather than bound in the signature: a default bound at definition is
    decided once, when the module is imported, and nothing can reach past it.
    """
    ran = (running or programs.run)([str(where(kind)), "--capabilities"],
                                    CAPABILITIES_WITHIN, env=_environment())
    if ran.trouble or ran.code != 0:
        return {}
    said = _one_object(ran.out)
    return said if isinstance(said, dict) else {}


def checked(kind: str, options: Sequence[str], env: Dict[str, str],
            running: Optional[Callable[..., programs.Ran]] = None) -> Checked:
    """Ask an adapter whether it can reach what it was pointed at, and what it found there.

    `options` is everything the owner typed after `--`, carried through exactly as typed. **Rundesk
    does not parse it and has no list of what any platform needs** — what comes back in `settings`
    is the adapter's own normalised account, which is what an owner will still be running on in a
    year.

    `env` carries the credential, by name, and nothing from this process's own environment reaches
    the adapter except the handful in `CARRIED`.

    **A program that died without printing an object failed; one that printed `ok: false` refused.**
    Both come back as `ok=False`, and `why` says which, because the sentence is the whole of what a
    person at a terminal can act on.
    """
    ran = (running or programs.run)(
        [str(where(kind)), "--check", *options],
        CHECK_WITHIN, env=_environment(env))
    if ran.trouble:
        return _refused(f"the {kind} adapter {ran.trouble}")
    said = _one_object(ran.out)
    if not isinstance(said, dict):
        return _refused(
            f"the {kind} adapter did not say whether it could connect"
            + (f" — it said: {_the_reason(ran.err)}" if ran.err.strip() else ""))
    if not said.get("ok"):
        return _refused(str(said.get("why") or f"the {kind} adapter would not connect"))
    return Checked(
        ok=True,
        describes=str(said.get("describes") or kind),
        notify_place=_a_text(said.get("notify_place")),
        settings=json.dumps(said.get("settings") if isinstance(said.get("settings"), dict) else {}),
        secret_names=[str(one) for one in _a_list(_a_mapping(said.get("secret")).get("env"))],
        invite=str(said.get("invite") or ""),
        why="")


def talking_to(kind: str, env: Dict[str, str], errors: Path,
               holding: int) -> programs.Talking:
    """Start this adapter's long-lived half and keep both ends of the conversation open.

    The third invocation, and the only one that is not bounded: `--capabilities` and `--check` are
    questions with answers, and this is a program that will still be here in six months.

    `holding` is the channel's claim, passed down so it lives exactly as long as the child — see
    `channels.hosting`, which takes it. **Whatever calls this must drain `stdout` continuously**;
    `utils.programs.talking` says what happens to anything that does not.
    """
    return programs.talking([str(where(kind)), "serve"], errors, env=_environment(env),
                            holding=(holding,))


def _refused(why: str) -> Checked:
    """One shape for every way this can come back no, so no caller has to build it."""
    return Checked(ok=False, describes="", notify_place=None, settings="{}", secret_names=[],
                   invite="", why=why)


def _runnable(at: Path) -> bool:
    """Whether this is a file somebody could actually run.

    Both halves asked, because they fail differently and a caller told "not there" about a program
    that is there and not executable goes looking in the wrong place entirely.
    """
    try:
        return at.is_file() and os.access(str(at), os.X_OK)
    except OSError:
        return False


def _environment(also: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """What an adapter is started with: a named handful, plus whatever it was given.

    Built rather than inherited. An adapter that could read this process's whole environment is one
    that comes to depend on something nobody meant to hand it — and the thing most likely to be in
    there is a credential belonging to a different agent.
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


def _one_object(said: str) -> Any:
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


def _the_reason(said: str) -> str:
    """The last thing a program said before it stopped, for putting in a sentence.

    Bounded, because this ends up in a message somebody reads: a program that wrote a megabyte of
    traceback would otherwise fill the screen with the least useful part of it.
    """
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    return lines[-1][:200] if lines else ""


def _a_list(said: Any) -> List[Any]:
    """Whatever an adapter said, as a list — one thing said alone is a list of one.

    An adapter that needs a single credential naming it as a string rather than as a list of one is
    not making a mistake, and refusing it would be this side being pedantic about a shape it can see
    through. Slack needs two, so the list is the real shape and this is the courtesy.
    """
    if said is None:
        return []
    return list(said) if isinstance(said, (list, tuple)) else [said]


def _a_mapping(said: Any) -> Dict[str, Any]:
    """Whatever an adapter said, as a mapping — `{}` when it said something else entirely.

    `said.get("secret", {})` is not this: a default applies only when the key is *absent*, so an
    adapter answering `"secret": "A_TOKEN"` handed a string to `.get` and raised `AttributeError`
    out of the one function whose whole job is to turn an unvetted program's output into an answer.
    """
    return said if isinstance(said, dict) else {}


def _a_text(said: Any) -> Optional[str]:
    """A value an adapter reported, as text, or `None` when it said nothing at all.

    Said-nothing and said-empty are different answers, and collapsing them here would make a channel
    that reported no place look like one that reported an empty one.
    """
    return None if said is None else str(said)
