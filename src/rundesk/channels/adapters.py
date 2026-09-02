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

**`--check`** reaches the platform as that adapter defines and reports what it found. Discord opens
its gateway connection; Slack authenticates and obtains a Socket Mode URL without opening it.
**Nothing about a channel is written down until it says so.** An agent whose channel is
misconfigured has to find out while somebody is standing at a terminal, not at three in the morning
when they ask it something.

**`ok: false` is an answer and exits `0`.** What is read is the object, not the exit code: a program
that dies without printing one *failed*, and one that printed `ok: false` *refused*, and those lead
somewhere different. Both are bounded, because this is the one place rundesk runs an unvetted
program while a person waits.

May depend on `agents`, `core` and `utils`.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

from rundesk.core import adapters
from rundesk.utils import programs

#: Finding a program, what it is started with, and reading what it printed are the same questions
#: for a provider adapter, so they live in `core.adapters` and this names only what is a channel's.
#: Re-exported rather than aliased at each call site: `NotRunnable` is in `commands.channels`'s
#: `TROUBLE` tuple as `adapters.NotRunnable`, and a caught kind is part of this module's surface.
NotRunnable = adapters.NotRunnable
CARRIED = adapters.CARRIED
where_the_packages_are = adapters.where_the_packages_are


def where(kind: str):
    """The program behind this channel kind. See `core.adapters.where`."""
    return adapters.where(kind, SHIPPED_IN, GIVEN_IN)


def known():
    """Every channel adapter this install can run. See `core.adapters.known`."""
    return adapters.known(SHIPPED_IN, GIVEN_IN)


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


def capabilities(kind: str, running: Optional[Callable[..., programs.Ran]] = None) -> Dict[str, Any]:
    """What this adapter says it can do. `{}` when it would not say, which is a whole answer.

    **Asked rather than assumed, and never guessed from a name.** An adapter that does not recognise
    the flag and does something else can do nothing, which is a complete answer and not an error —
    so every failure here is an empty mapping rather than an exception, and the caller reads a
    missing field as the least capable answer.

    How the answer is read is `core.adapters`', because a provider is asked the same question and
    reads a refusal the same way. What is a *channel's* is that it is asked with nothing of a
    particular run set — there is no run.
    """
    return adapters.asked_offline(where(kind), CAPABILITIES_WITHIN, adapters.environment(),
                                  running)


def checked(kind: str, options: Sequence[str], env: Dict[str, str],
            running: Optional[Callable[..., programs.Ran]] = None) -> Checked:
    """Ask an adapter whether it can reach what it was pointed at, and what it found there.

    `options` is everything the owner typed after `--`, carried through exactly as typed. **Rundesk
    does not parse it and has no list of what any platform needs** — what comes back in `settings`
    is the adapter's own normalised account, which is what an owner will still be running on in a
    year.

    `env` carries the credential, by name, and nothing from this process's own environment reaches
    the adapter except the handful in `CARRIED`.

    **`RUNDESK_ALLOW` belongs in `env` too, and the caller puts it there.** Who may reach an agent is
    not only a hosting-time fact: an adapter may need to open private conversations for the people
    on that list, including while it checks the first destination it can reach. One asked to connect
    without the list can therefore refuse before it has signed in — and a caller that carried only
    the credential would meet that refusal on every `add`. `channels.hosting` builds the same
    variable, from the same list, for the long-lived half.

    **A program that died without printing an object failed; one that printed `ok: false` refused.**
    Both come back as `ok=False`, and `why` says which, because the sentence is the whole of what a
    person at a terminal can act on.
    """
    ran = (running or programs.run)(
        [str(where(kind)), "--check", *options],
        CHECK_WITHIN, env=adapters.environment(env))
    if ran.trouble:
        return _refused(f"the {kind} adapter {ran.trouble}")
    said = adapters.printed_object(ran.out)
    if not isinstance(said, dict):
        return _refused(
            f"the {kind} adapter did not say whether it could connect"
            + (f" — it said: {adapters.last_said(ran.err)}" if ran.err.strip() else ""))
    named = [str(one) for one in adapters.as_list(adapters.as_mapping(said.get("secret")).get("env"))]
    if not said.get("ok"):
        # **The credential's name comes back on a refusal too, and this is what carries it.** An
        # adapter that cannot connect for want of a token names the variable it looked in — the
        # Discord one says so in its own docstring — and that name is the whole of how a caller
        # knows what to ask a person for without holding a list of what any platform wants. Dropped
        # here, the only refusal `rundesk channels add` could ever answer with was to repeat itself.
        return _refused(str(said.get("why") or f"the {kind} adapter would not connect"), named)
    return Checked(
        ok=True,
        describes=str(said.get("describes") or kind),
        notify_place=adapters.as_text(said.get("notify_place")),
        settings=json.dumps(said.get("settings") if isinstance(said.get("settings"), dict) else {}),
        secret_names=named,
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
    return programs.talking([str(where(kind)), "serve"], errors, env=adapters.environment(env),
                            holding=(holding,))


def _refused(why: str, named: Optional[List[str]] = None) -> Checked:
    """One shape for every way this can come back no, so no caller has to build it.

    `named` is whatever credential the adapter said it looked for. Empty for a program that died
    without answering — there is nothing to have read — and filled in for one that answered no
    because nothing was set, which is the refusal a caller can actually do something about.
    """
    return Checked(ok=False, describes="", notify_place=None, settings="{}",
                   secret_names=list(named or []), invite="", why=why)





