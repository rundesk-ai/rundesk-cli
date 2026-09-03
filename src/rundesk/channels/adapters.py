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

## Four bounded questions, and one program that does not stop

Two are asked while somebody is at a terminal, before anything about a channel is written down. Two
are asked in the middle of a turn, by the agent itself, of a channel that is already connected. All
four are bounded, and all four are read the same way: **the object the program printed is the answer
and the exit code is not.**

**`--capabilities`** is asked offline: no account, no network, the same answer every time. It is what
lets a fidelity difference be a fact rather than a guess — an adapter that cannot edit a message is
told apart from one that can and did not, and an adapter that cannot search from one that can. It is
the only one of the four asked with no credential at all.

**`search`** and **`fetch`** are the agent's, not the owner's. An agent asks its channel to look
through the platform it is connected to, reads what came back, narrows the question and asks again;
and when a result carries a file worth having, it asks for that file by itself. Both run as their own
bounded programs rather than as words down the hosted channel's pipe — so both work in a turn a
schedule started and in one somebody typed at a terminal, neither takes the channel's claim, and
neither displaces a `serve` that is already running.

**Neither of them widens what an agent can see.** They are handed exactly what `--check` is handed,
out of the same names, for the same agent: a bot's own credential, and therefore a bot's own reach.
There is no scope here that a connected channel did not already have.

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

#: How long `search` may take. Shorter than `--check` on purpose: an agent runs this in the middle of
#: a turn and will run it again after reading the answer, so a minute of a platform not answering is
#: already a minute the turn spent on nothing. An adapter that cannot finish inside it is expected to
#: stop looking and say so in `partial` rather than to be cut off here.
SEARCH_WITHIN = 60.0

#: How long `fetch` may take. Longer, because it is downloading files rather than reading an index,
#: and the sizes it may bring are `channels.files`' to bound rather than the clock's.
FETCH_WITHIN = 300.0

#: The word a `--capabilities` answer offers search under, and the exact key `commands.search` reads.
OFFERS_SEARCH = "search"

#: How many results a search asks for unless somebody says otherwise, and the most it will ever ask
#: for. **Deliberately not `providers.kept.FOUND_AT_MOST`**, which `channels` may not import and
#: which answers a different question — how much of an agent's own record to read back, rather than
#: how much of somebody else's platform to ask for. The number agrees because the reason does: the
#: agent is the first caller and every line it reads costs it tokens.
RESULTS_AT_MOST = 20

#: The ceiling on that. An adapter asked for five thousand results is one paginating somebody else's
#: platform until it is rate-limited, and the refusal belongs here rather than in each adapter.
RESULTS_CEILING = 100

#: What every part of a search is bounded to before it reaches a prompt or a platform. **Applied on
#: rundesk's side, whatever an adapter promised**: a result is a stranger's words, the display name
#: beside them is a stranger's words, and so is the sentence an adapter wrote about why it stopped.
#: The bound that protects a prompt is the one that runs where the prompt is composed.
#:
#: `WORDS_AT_MOST` is the other direction and is the one with a platform behind it: a query past a
#: published ceiling is refused by the platform rather than truncated by it, so it is clipped here
#: where the refusal can be avoided rather than reported.
WORDS_AT_MOST = 400
TEXT_AT_MOST = 1000
NAME_AT_MOST = 80
WHERE_AT_MOST = 60
WHEN_AT_MOST = 40
LINK_AT_MOST = 400
PARTIAL_AT_MOST = 240

#: The ids on a result, bounded here too. **An id looks like the one field a stranger did not
#: write, and it is not**: `who` is what gets printed whenever an adapter omits `display`, and `ref`
#: is printed on every row and typed back into `--fetch`. Both are an adapter's text, so both are
#: flattened and clipped exactly as a display name is. `REF_AT_MOST` is the number
#: `docs/extending/adapters.md` asks an adapter for, applied here so the page is true of the code
#: rather than a request the code does not enforce.
ID_AT_MOST = 120
REF_AT_MOST = 64

#: How many files one result may describe. The same number and the same reason as
#: `channels.files.PER_MESSAGE`, which bounds what one arriving message may bring: a result is a
#: stranger's message too, and a listing is not somewhere a stranger gets to fill either.
ATTACHMENTS_AT_MOST = 10


class Asking(NamedTuple):
    """What a channel is asked to look for. Every field is on the wire, and `""` means unscoped.

    **Said-nothing and said-empty are one answer here, and that is the exception rather than the
    rule.** Everywhere else in this product the two are kept apart; a scope has no third meaning —
    an absent place and an empty place both mean *everywhere this channel can reach* — so every key
    is always sent, and an adapter never has to decide what a missing one would have meant.
    """

    words: str
    place: str = ""
    user: str = ""
    since: str = ""
    until: str = ""
    most: int = RESULTS_AT_MOST


class Result(NamedTuple):
    """One message a channel found, in the shape every adapter answers in.

    **Who, where and when are as much of the answer as the words are.** A line of text with nothing
    around it is something an agent cannot act on: it cannot say who to go back to, cannot tell a
    room from a private conversation, and cannot tell last week from last year.

    `link` and `display` are `""` where the platform gave neither, and that is a whole answer rather
    than a failure — the id in `who` and the place in `external_place` are what the platform is
    asked with again, and they are always there.
    """

    who: str
    display: str
    where: str
    external_place: str
    when: str
    text: str
    link: str
    ref: str
    attachments: List[Dict[str, Any]]


class Searched(NamedTuple):
    """What a channel made of one search, in four states that must never be read as each other.

    | | |
    |---|---|
    | **found** | `ok`, `results` has some, `partial` is `""` |
    | **found nothing** | `ok`, `results` is empty, `partial` is `""` — it looked everywhere asked |
    | **looked as far as it could** | `ok`, `partial` is the sentence saying where it stopped |
    | **could not look** | not `ok`, and `why` is the sentence |

    **`partial` is load-bearing and is not a flavour of finding nothing.** An agent that reads a
    spent budget as an absence of conversation concludes the thing was never discussed, which is the
    one wrong answer this whole capability can give. So the third state is its own: `results` may be
    empty or not, and `partial` says the search did not finish either way.

    `places` and `messages` are what the adapter says it looked at, and are `None` where it did not
    say — a channel that reports nothing about its own reach is not one reporting zero.
    """

    ok: bool
    results: List[Result]
    places: Optional[int]
    messages: Optional[int]
    partial: str
    why: str


class Fetched(NamedTuple):
    """What a channel staged when it was asked for one result's attachments.

    `brought` is each file exactly as `channels.files.landed` takes it — `at`, `name` and `bytes` —
    and this module neither opens nor moves one. Where a fetched file may stand and how big it may
    be are that module's, and are checked there against the file rather than against what an adapter
    said about it.

    `message` is the platform's own id for the message these came from, and is what the landed copies
    are filed under — so an attachment brought in by a search stands in the same dated directory,
    under the same message, as one that arrived on its own.
    """

    ok: bool
    message: str
    brought: List[Dict[str, Any]]
    partial: str
    why: str


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


def searched(kind: str, asking: Asking, env: Dict[str, str],
             running: Optional[Callable[..., programs.Ran]] = None) -> Searched:
    """Ask a channel to look through its own platform, and read what it found.

    **The fourth invocation, and the first one an agent causes.** `--capabilities` and `--check` are
    asked while somebody is at a terminal connecting a channel; this is asked in the middle of a
    turn, by the agent itself, and asked again once it has read the answer. That is what sets the
    ceiling — see `SEARCH_WITHIN` — and it is why nothing here waits, retries or holds anything.

    **A process of its own, not a word down the hosted channel's pipe.** The two are not the same
    seam: `serve` is one long-lived connection a gateway drains, and a request sent down it would
    only ever work while a gateway was up and would have to be correlated back through it. Asked as
    its own bounded program, a search works in a turn a schedule started, in one somebody typed at a
    terminal, and in one agent's delegation to another — which is the whole of what "on demand"
    means. It takes no claim and holds no lock, so it runs beside a live `serve` rather than
    displacing it.

    **What it may look through is the credential's own reach and nothing wider.** This hands over
    exactly what `--check` is handed, out of the same names, for the same agent — so a search sees
    the places that bot was invited to and no more. There is no widening here and none available:
    an adapter is handed a bot's credential, and a bot's credential is what a bot can see.

    `ok=False` covers both a refusal and a failure, exactly as `Checked` does, and `why` is what
    tells them apart — a program that died without printing an object *failed*, and one that printed
    `ok: false` *refused*. **Whether this channel offers search at all is not asked here**: that is
    `--capabilities`' answer, read offline and with no credential, and `commands.search` asks it
    first so that a channel with nothing to offer costs no token and no call.
    """
    ran = (running or programs.run)(
        [str(where(kind)), "search"], SEARCH_WITHIN, env=adapters.environment(env),
        telling=json.dumps(_as_asked(asking)))
    said, trouble = _answered(kind, ran, "search")
    if trouble:
        return Searched(False, [], None, None, "", trouble)
    if not said.get("ok"):
        return Searched(False, [], None, None, "",
                        str(said.get("why") or f"the {kind} adapter would not search"))
    looked = adapters.as_mapping(said.get("looked"))
    return Searched(
        ok=True,
        results=_results(adapters.as_list(said.get("results")), asking.most),
        places=_a_count(looked.get("places")),
        messages=_a_count(looked.get("messages")),
        partial=_one_line(said.get("partial")),
        why="")


def fetched(kind: str, ref: str, env: Dict[str, str],
            running: Optional[Callable[..., programs.Ran]] = None) -> Fetched:
    """Ask a channel to bring in the attachments of one result it found. The fifth invocation.

    **A second act rather than a field on a search result, and the reason is the platform.** Discord
    signs its attachment links with an expiry and publishes no endpoint that refreshes one, so a
    link handed back in a search result is a link already going stale; the adapter has to reach the
    message again and only then download. Folding that into the search would also mean downloading
    every attachment of every result to answer a question about words.

    **This stages, and `channels.files` lands.** The adapter holds the credential and rundesk holds
    the filesystem, which is the same division the arriving path already makes: the adapter writes
    into the channel's own directory under a name of no consequence and says where, and `landed`
    proves the path is contained, the file is ordinary, and it holds the bytes the platform said it
    would — against the file, never against what the adapter claimed about it.
    """
    ran = (running or programs.run)(
        [str(where(kind)), "fetch"], FETCH_WITHIN, env=adapters.environment(env),
        telling=json.dumps({"ref": str(ref)}))
    said, trouble = _answered(kind, ran, "fetch")
    if trouble:
        return Fetched(False, "", [], "", trouble)
    if not said.get("ok"):
        return Fetched(False, "", [], "",
                       str(said.get("why") or f"the {kind} adapter would not fetch"))
    brought = [one for one in adapters.as_list(said.get("attachments")) if isinstance(one, dict)]
    return Fetched(ok=True, message=str(said.get("message") or ""), brought=brought,
                   partial=_one_line(said.get("partial")), why="")


def offers_search(kind: str, running: Optional[Callable[..., programs.Ran]] = None) -> bool:
    """Whether this channel says it can search. Asked offline, with no account and no credential.

    **Asked rather than attempted, and that distinction is the point.** An adapter written before
    search existed does not recognise the argument, and running it to find out would be reading a
    crash and a refusal as the same thing. `--capabilities` is the question that already exists for
    exactly this — a fidelity difference as a fact rather than a guess — and a missing key is read
    the least capable way round, so silence means *no* and nothing is retried for it.
    """
    return bool(capabilities(kind, running).get(OFFERS_SEARCH))


def _as_asked(asking: Asking) -> Dict[str, Any]:
    """One search request as it crosses the seam. Every key present, bounded before it is sent.

    **Bounded here rather than trusted to be small.** The words are a person's or an agent's, they
    end up in somebody else's query string, and one platform publishes a refusal for a query past
    its own ceiling — so the ceiling this side applies is the one an adapter can rely on.
    """
    return {"words": str(asking.words)[:WORDS_AT_MOST],
            "place": str(asking.place),
            "user": str(asking.user),
            "since": str(asking.since),
            "until": str(asking.until),
            "limit": max(1, min(int(asking.most), RESULTS_CEILING))}


def _answered(kind: str, ran: programs.Ran, invocation: str):
    """The object an adapter printed, and the sentence to report when there is not one.

    One reading for both bounded invocations, because both are judged the same way: **the object is
    read and the exit code is not.** A program that printed `ok: false` refused and exits `0` saying
    so; one that died without printing an object failed; and the sentence has to say which, because
    that is the whole of what somebody can act on.
    """
    if ran.trouble:
        return {}, f"the {kind} adapter {ran.trouble}"
    said = adapters.printed_object(ran.out)
    if not isinstance(said, dict):
        return {}, (f"the {kind} adapter did not answer the {invocation} it was asked"
                    + (f" — it said: {adapters.last_said(ran.err)}" if ran.err.strip() else ""))
    return said, ""


def _results(said: Sequence[Any], most: int) -> List[Result]:
    """Every result an adapter printed, as rows, bounded to what was asked for.

    **Everything here is a stranger's text arriving from an unvetted program**, so nothing raises
    and nothing is trusted: a row that is not an object is dropped, every field is read as text, and
    the bound this side applies is the one that holds when an adapter ignores the one it was given.
    A result with neither words nor a file in it is dropped, because a line saying only that
    somebody spoke is a line that costs an agent tokens and tells it nothing.
    """
    found: List[Result] = []
    for one in said:
        if len(found) >= max(1, min(int(most), RESULTS_CEILING)):
            break
        if not isinstance(one, dict):
            continue
        attachments = [_an_attachment(each) for each in adapters.as_list(one.get("attachments"))
                       if isinstance(each, dict)][:ATTACHMENTS_AT_MOST]
        text = str(one.get("text") or "")[:TEXT_AT_MOST]
        if not text and not attachments:
            continue
        found.append(Result(
            who=_one_line(one.get("who"), ID_AT_MOST),
            display=_one_line(one.get("display"), NAME_AT_MOST),
            where=_one_line(one.get("where"), WHERE_AT_MOST),
            external_place=_one_line(one.get("external_place"), ID_AT_MOST),
            when=_one_line(one.get("when"), WHEN_AT_MOST),
            text=text,
            link=_one_line(one.get("link"), LINK_AT_MOST),
            ref=_one_line(one.get("ref"), REF_AT_MOST),
            attachments=attachments))
    return found


def _an_attachment(said: Dict[str, Any]) -> Dict[str, Any]:
    """One file a result carries, described and not fetched.

    `bytes` is kept only when the platform really said a number, because said-nothing and said-zero
    are different answers and `channels.files.landed` reads an absent one as the first.
    """
    described: Dict[str, Any] = {"name": _one_line(said.get("name"), NAME_AT_MOST)}
    size = said.get("bytes")
    if isinstance(size, int) and not isinstance(size, bool):
        described["bytes"] = size
    return described


def _a_count(said: Any) -> Optional[int]:
    """A number an adapter reported about its own reach, or `None` where it reported nothing.

    A channel that said nothing about how far it looked is not one that looked nowhere, and reading
    the two as one would let a search that reported nothing read as a search that found nothing.
    """
    if isinstance(said, bool) or not isinstance(said, int) or said < 0:
        return None
    return said


def _one_line(said: Any, most: int = PARTIAL_AT_MOST) -> str:
    """A stranger's text, flattened to one line and clipped, before it can reach a prompt.

    **Flattened here, on rundesk's side.** Every one of these was written by whoever wrote it, and a
    newline in any of them is how somebody ends our sentence and begins one of their own — a place
    name, a display name, and a sentence an adapter wrote about why it stopped looking are all the
    same kind of thing. The bound that protects a prompt is the one that runs where the prompt is
    composed, not the one an adapter promised to apply.
    """
    if said is None:
        return ""
    flat = " ".join(str(said).split())
    return flat if len(flat) <= most else flat[:most - 1] + "…"


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





