"""Looking through the platforms an agent is connected to, and bringing one result's files in.

**The agent is the only caller this is shaped for.** A person asks Slack from Slack; what nothing
else could do is let an agent in the middle of a turn ask *its own channels* a question, read the
answer, narrow it, and ask again — which is why this is a verb it runs rather than a block carried
in with a message it happened to be sent.

`rundesk messages` is the same question asked of a different thing, and the two are deliberately
next to each other: that one reads what this agent was told and said back, and this one reads what
was said on the platform it is connected to, by anybody, whether the agent was there or not.

## One verb, however many platforms

There is one search here and there will never be two. Every channel answers the same request and
returns the same row — who, where, when, the words, a link, and what files are attached — and an
adapter that cannot search says so in `--capabilities` and is skipped without a call or a credential.
So an agent learns this once, an agent with no channels has no search at all, and adding a platform
adds no vocabulary. The platform knowledge stays in the adapter, which is the only place that may
hold it.

## What it can see is what the bot can see

Nothing here widens an agent's reach. A channel is searched with exactly what `--check` is handed —
the bot's own credential, out of the agent's own name — so an agent finds what the bot it is hosted
as was invited to and nothing else. There is no scope on this command, and none available to it.

## Four answers, and none of them may be read as another

Found, found nothing, **looked as far as it could**, and could not look. The third is the one this
file exists to keep separate: a search that ran out of budget and a search that found nothing look
identical in a list of zero rows, and an agent that reads the first as the second concludes a thing
was never discussed. So a spent budget is printed as its own line, marked, above or below the rows
either way — and never as an empty listing.

A channel that could not be searched never costs the others: the ones that answered are printed,
the one that refused is named on stderr, and the exit code says whether anything was looked through
at all.
"""

import argparse
import json
import sqlite3
from datetime import datetime
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Sequence

from rundesk.agents import directory, migration, records
from rundesk.channels import adapters, credentials, files, hosting, kept
from rundesk.commands import Subcommands, failed
from rundesk.core import secrets
from rundesk.exits import FAILED, OK, USAGE
from rundesk.utils import locking, programs
from rundesk.utils.terminal import NOTHING, as_table

#: What runs an adapter. Handed in with no default of its own, for the reason `commands.channels`
#: gives at length: a case that forgets it gets the real thing, and the real thing reaching Slack
#: fails against the closed proxy a suite runs behind rather than passing quietly on a laptop.
Reaching = Callable[..., programs.Ran]

#: Everything a verb here can be stopped by, the same set `commands.channels` catches and for the
#: same reasons — no program behind a channel, records that are not there or cannot be understood,
#: an agent name that reaches outside where agents are kept, a migration that has not run, a
#: credential store that will not answer, and the ordinary failures of a disk.
TROUBLE = (kept.Refused, adapters.NotRunnable, directory.Refused, records.NotThere,
           records.Unreadable, records.Refused, migration.Ahead, migration.Broken,
           files.Refused, secrets.Refused, secrets.Stuck, locking.Stuck, OSError, sqlite3.Error)

#: How much of a found message is shown on one line when the whole of it was not asked for. The same
#: number `commands.messages` uses, for the same reason: enough to recognise an exchange and go and
#: read it, not the exchange itself.
ON_ONE_LINE = 70

#: The line that says a search did not finish. **Marked, and never folded into the count**, because
#: this is the one distinction an agent must not miss: a search that stopped early and a search that
#: found nothing are the same empty table, and only this sentence tells them apart.
NOT_WHOLE = "NOT THE WHOLE ANSWER"

#: What a channel that does not offer search is called, once, per search. Not a failure and not a
#: refusal: an adapter written before this existed does nothing wrong by not answering a question
#: that did not exist when it was written.
NO_SEARCH_HERE = "offers no search"


class Looked(NamedTuple):
    """What one channel came back with, and whether it looked at all.

    `asked` is `False` for a channel that does not offer search — nothing was run, nothing was
    handed a credential, and there is no `found` to read. It is the difference between a channel
    that searched and found nothing and one that never searched, which the exit code turns on.
    """

    kind: str
    asked: bool
    found: Optional[adapters.Searched]
    why: str


def register(sub: Subcommands) -> None:
    """One verb, and one flag on it that makes it a different act.

    **Bringing a file in is not a field on a search result, and it is not a second verb either.**
    Not a field, because a search reads an index and answers in a second while this downloads —
    folding it in would mean fetching every attachment of every result to answer a question about
    words, and on one platform the link in a result is already expiring, so a file has to be asked
    for against the message again rather than against the answer. Not a second verb, because the
    whole point of this capability is that an agent learns *one* thing: `rundesk search --help` is
    the entire surface, on every platform, for both halves of it.

    **`--fetch` rather than a sub-verb, and that is argparse's constraint rather than a preference.**
    A sub-verb after a positional list is ambiguous — `search ava files` cannot be told from `search
    files ava` — so the word would have had to move in front of the agent, which no other verb here
    does. The flag reads as the act it is and cannot be mistaken for a word to look for.
    """
    look = sub.add_parser("search", help="look through the platforms an agent is connected to")
    look.add_argument("agent", metavar="<agent>", help="whose channels to look through")
    look.add_argument("words", metavar="<words>", nargs="*",
                      help="what to look for; left out only with --fetch")
    look.add_argument("--channel", metavar="<channel>",
                      help="only this channel (default: every one this agent has)")
    look.add_argument("--place", metavar="<id>",
                      help="only this room or private conversation, as a result reports it")
    look.add_argument("--from", metavar="<id>", dest="sender",
                      help="only messages this person said, as the platform knows them")
    look.add_argument("--since", metavar="<YYYY-MM-DD>", help="nothing said before this day")
    look.add_argument("--until", metavar="<YYYY-MM-DD>", help="nothing said after this day")
    look.add_argument("--limit", metavar="<n>", type=int, default=adapters.RESULTS_AT_MOST,
                      help=f"how many from each channel (default: {adapters.RESULTS_AT_MOST}, "
                           f"most: {adapters.RESULTS_CEILING})")
    look.add_argument("--full", action="store_true",
                      help="print whole messages rather than one line each")
    look.add_argument("--fetch", metavar="<ref>", default=None,
                      help="bring one result's attachments in, instead of searching — needs "
                           "--channel, and takes the ref the search printed")


def cmd_search(args: argparse.Namespace, reaching: Optional[Reaching] = None) -> int:
    """A `Namespace` in, an exit code out."""
    if args.fetch is not None:
        return _brought_in(args, reaching)
    words = " ".join(args.words).strip()
    if not words:
        return _mistyped("say what to look for: rundesk search <agent> <words>")
    if args.limit < 1:
        return _mistyped("--limit is how many to answer with, so it is at least 1")
    if args.limit > adapters.RESULTS_CEILING:
        return _mistyped(f"--limit may be at most {adapters.RESULTS_CEILING} — a platform asked for "
                         f"more than that is one paginated until it refuses")
    for named, said in (("--since", args.since), ("--until", args.until)):
        if said and not _is_a_day(said):
            return _mistyped(f"{named} is a day, written {named} 2026-08-01")
    try:
        trouble = directory.not_an_agent(args.agent)
        if trouble:
            return _failed(trouble, "see what there is with: rundesk agents")
        rows = _the_channels(args.agent, args.channel)
        if not rows:
            return _nothing_to_search(args.agent, args.channel)
        asking = adapters.Asking(words=words, place=args.place or "", user=args.sender or "",
                                 since=args.since or "", until=args.until or "", most=args.limit)
        looked = [_one_channel(args.agent, row, asking, reaching) for row in rows]
    except TROUBLE as why:
        return _failed(str(why))
    return _shown(args, words, looked)


def _the_channels(agent: str, named: Optional[str]) -> List[Dict[str, Any]]:
    """Which channels this search covers: the one that was named, or every one the agent has.

    **Named or all, and never a guess in between.** A channel somebody named that the agent does not
    have comes back empty rather than quietly widening to everything, which is the failure worth
    avoiding: a typo that searched more than was asked for is a typo nobody notices.
    """
    if named:
        return [one for one in kept.all(agent) if str(one.get("kind")) == named]
    return list(kept.all(agent))


def _one_channel(agent: str, row: Dict[str, Any], asking: adapters.Asking,
                 reaching: Optional[Reaching]) -> Looked:
    """Ask one channel, having first asked whether it can be asked at all.

    **`--capabilities` first, and it is not a formality.** It is offline, takes no credential and
    reaches nothing, and it is the whole of how a channel that does not offer search is told from
    one that offers it and broke. Running `search` to find out would read a crash and an adapter
    written before this existed as the same thing, and would hand a credential to a program that was
    never going to use it.
    """
    kind = str(row.get("kind") or "")
    try:
        if not adapters.offers_search(kind, reaching):
            return Looked(kind, False, None, NO_SEARCH_HERE)
        return Looked(kind, True,
                      adapters.searched(kind, asking, _handed(agent, row), reaching), "")
    except TROUBLE as why:
        # **Every way one channel can fail is that channel's, not the search's.** A missing program,
        # a credential store that will not answer, records that cannot be read: raised, any one of
        # them would discard the answers the channels before it had already given. Named here
        # instead, so a search across four channels reports three answers and one reason.
        return Looked(kind, False, None, str(why) or type(why).__name__)


def _handed(agent: str, row: Dict[str, Any], staging: bool = False) -> Dict[str, str]:
    """What a channel is asked its question with: who it is, who it may answer, and its credentials.

    **The same values a hosted channel is handed, resolved the same way, for the same agent.** That
    is what makes the reach of a search a fact rather than a promise: a channel searches as the bot
    it is hosted as, because it is handed the value that agent's own name holds and nothing else.
    Read through `channels.kept` and `channels.credentials` rather than built here, so a search, a
    `--check` and a running adapter cannot come to disagree about who a channel is.

    `RUNDESK_ALLOW` is here for the reason it is on a `--check`: an adapter may need to know whose
    private conversations are its to look in before it looks in any of them.

    **`RUNDESK_CHANNEL_HOME` is handed to `fetch` and withheld from `search`**, and that is the same
    rule the carried environment already follows: a variable an invocation cannot use is one it must
    not come to depend on. Only `fetch` stages a file, and where a staged file may stand is checked
    by `channels.files.landed` against this directory — so a `search` handed it would be a search
    able to name a path that landing would then accept.
    """
    kind = str(row.get("kind") or "")
    admitting = kept.admitting(row)
    built = {"RUNDESK_AGENT": agent,
             "RUNDESK_CHANNEL": kind,
             "RUNDESK_SETTINGS": str(row.get("settings") or "{}"),
             "RUNDESK_ALLOW": ",".join(admitting.senders),
             "RUNDESK_ALLOW_PLACES": ",".join(admitting.places)}
    if staging:
        at = hosting.at(agent, kind)
        # Made here rather than left to the adapter. An adapter told to stage into a directory that
        # is not there has to make it, and one that makes it makes it wherever it read the name —
        # so the directory a landing will accept from is the one rundesk created, not one an adapter
        # invented beside it.
        at.mkdir(parents=True, exist_ok=True)
        built["RUNDESK_CHANNEL_HOME"] = str(at)
    built.update(credentials.handed(agent, _named_secrets(row)))
    return built


def _named_secrets(row: Dict[str, Any]) -> List[str]:
    """The environment names this channel's credentials are kept under, as the record holds them.

    Read exactly the way `commands.channels` and `channels.hosting` read it, so what a search is
    started with is what a `--check` and a hosted adapter are started with. A record that will not
    parse names nothing, which is the least this can claim.
    """
    try:
        held = json.loads(row.get("secret_names") or "[]")
    except (TypeError, ValueError):
        return []
    return [str(one) for one in held] if isinstance(held, list) else []


def _shown(args: argparse.Namespace, words: str, looked: Sequence[Looked]) -> int:
    """Print what each channel came back with, and answer whether anything was looked through.

    **The exit code turns on whether anything looked, not on whether anything was found.** A search
    that ran everywhere and matched nothing did what it was asked; one where no channel could be
    searched did not, and a script reading `0` for the second would carry on as though the words
    were not there to be found.
    """
    asked = [one for one in looked if one.asked and one.found is not None]
    answered = [one for one in asked if one.found.ok]
    for one in looked:
        if one.asked and one.found is not None and not one.found.ok:
            _refused(one.kind, one.found.why)
        elif not one.asked:
            _could_not(one.kind, one.why)
    for one in answered:
        _one_answer(args, words, one)
    if not answered:
        if not asked:
            return _failed(f"nothing {args.agent} has could be searched",
                           "see what it has with: rundesk channels " + args.agent)
        return FAILED
    return OK


def _one_answer(args: argparse.Namespace, words: str, one: Looked) -> None:
    """One channel's results, headed by what was asked and what was reached.

    **The heading is printed before the rows and says the narrowing back.** An empty table under no
    heading reads as a broken search; the same table under a sentence naming the words, the channel
    and the places looked through reads as an answer.
    """
    found = one.found
    print(f"\n{_counted(found)} on {one.kind}{_narrowed_by(args, words)}{_reached(found)}")
    if found.partial:
        # Above the rows as well as in the count, because this is the line that must not be missed:
        # rows that are present make an incomplete answer look complete, and rows that are absent
        # make it look like an absence of conversation.
        print(f"  {NOT_WHOLE} — {found.partial}")
    if args.full:
        for each in found.results:
            _in_full(each)
        return
    as_table(("WHEN", "WHO", "WHERE", "FILES", "REF", "SAID"),
             [(each.when or NOTHING, each.display or each.who or NOTHING,
               each.where or NOTHING, str(len(each.attachments)) if each.attachments else "",
               each.ref or NOTHING, _briefly(each)) for each in found.results])


def _in_full(one: adapters.Result) -> None:
    """One result whole: who and where it was said, when, what to open, and what to fetch."""
    print(f"\n[{one.when}] {one.display or one.who}"
          f"{f' in {one.where}' if one.where else ''}")
    if one.link:
        print(one.link)
    print(f"ref {one.ref}" + (f" — {len(one.attachments)} attached: "
                              + ", ".join(str(each.get('name') or NOTHING)
                                          for each in one.attachments)
                              if one.attachments else ""))
    print(one.text)


def _counted(found: adapters.Searched) -> str:
    """How many were found, said so that a search that stopped early never reads as an empty one."""
    if found.results:
        return f"{len(found.results)} found" + (" so far" if found.partial else "")
    return "nothing found yet" if found.partial else "nothing found"


def _narrowed_by(args: argparse.Namespace, words: str) -> str:
    """The question that was asked, said back, so an empty answer is readable rather than alarming."""
    each = [f"holding {words!r}"]
    if args.place:
        each.append(f"in {args.place}")
    if args.sender:
        each.append(f"from {args.sender}")
    if args.since:
        each.append(f"since {args.since}")
    if args.until:
        each.append(f"until {args.until}")
    return ", " + ", ".join(each)


def _reached(found: adapters.Searched) -> str:
    """What the channel says it looked through, where it said anything at all.

    Said-nothing is not said-zero: a channel that reported nothing about its own reach prints no
    clause here, rather than one claiming it looked in no places.
    """
    each = []
    if found.places is not None:
        each.append(f"{found.places} place{'' if found.places == 1 else 's'}")
    if found.messages is not None:
        each.append(f"{found.messages} message{'' if found.messages == 1 else 's'}")
    return f"  ({', '.join(each)} looked through)" if each else ""


def _briefly(one: adapters.Result) -> str:
    """Enough of a found message to recognise it, on one line."""
    said = " ".join(str(one.text).split())
    if not said:
        return NOTHING
    return said if len(said) <= ON_ONE_LINE else said[:ON_ONE_LINE - 1] + "…"


def _brought_in(args: argparse.Namespace, reaching: Optional[Reaching]) -> int:
    """Bring one result's attachments onto this machine, and say where each landed.

    **Staged by the adapter and landed by rundesk**, exactly as a file that arrives on its own is:
    the adapter holds the credential and writes into the channel's own directory, and
    `channels.files.landed` proves the path is contained, the file is ordinary and it holds the
    bytes the platform said it would — against the file rather than against what the adapter claimed
    about it. So a search's attachment stands in the same dated directory, under the same message,
    swept on the same day, as one somebody sent the agent.

    A file that will not land is named and the others still go: one refusal is not a reason to
    throw away the rest of what somebody attached.
    """
    if not args.channel:
        return _mistyped("--fetch needs the channel that found it: "
                         "rundesk search <agent> --fetch <ref> --channel <channel>")
    if args.words:
        return _mistyped("--fetch brings one result in and looks for nothing, so it takes no words")
    narrowing = [named for named, said in (("--place", args.place), ("--from", args.sender),
                                           ("--since", args.since), ("--until", args.until))
                 if said]
    if narrowing:
        # **Refused rather than ignored.** Every one of these narrows a *search*, and a fetch is not
        # one — silently accepting them would answer a different question from the one that was
        # typed, which is the failure this command refuses loudly everywhere else.
        return _mistyped(f"--fetch names one result and narrows nothing, so it does not take "
                         f"{', '.join(narrowing)}")
    try:
        trouble = directory.not_an_agent(args.agent)
        if trouble:
            return _failed(trouble, "see what there is with: rundesk agents")
        row = kept.one(args.agent, args.channel)
        # **Asked the same question `search` is asked first, and for the same reason.** A channel
        # that offers no search has no result to have printed a ref, so a `--fetch` against one is
        # a mistake rather than a request — and answering it by handing an adapter written before
        # this release both a credential and somewhere to write would be the one thing the gate on
        # the search exists to prevent.
        if not adapters.offers_search(args.channel, reaching):
            return _failed(f"{args.channel} {NO_SEARCH_HERE}, so nothing it found can be fetched")
        got = adapters.fetched(args.channel, args.fetch,
                               _handed(args.agent, row, staging=True), reaching)
        if not got.ok:
            return _failed(f"{args.channel} would not fetch {args.fetch}: {got.why}")
        return _landed(args, got)
    except TROUBLE as why:
        return _failed(str(why))


def _landed(args: argparse.Namespace, got: adapters.Fetched) -> int:
    """Take each staged file into the agent's own account of what arrived, and print where it went."""
    if not got.message:
        return _failed(f"{args.channel} fetched files without saying which message they came from, "
                       f"so there is nowhere to file them")
    where, refused = [], []
    for one in got.brought[:files.PER_MESSAGE]:
        try:
            where.append(files.landed(args.agent, args.channel, got.message, one))
        except (files.Refused, ValueError, OSError) as why:
            # **The same three the arriving path catches, and `ValueError` is not padding.** An
            # adapter is an unvetted program: one that names `/tmp/a\0b` makes the landing raise
            # `ValueError` rather than refuse, and uncaught that is a traceback out of a command
            # whose whole premise is that it cannot trust what the adapter said.
            refused.append(str(why) or type(why).__name__)
    for why in refused:
        failed(f"search: {why}")
    if len(got.brought) > files.PER_MESSAGE:
        # Bounded here as well as in the adapter, for the reason `channels.files` gives about the
        # arriving path: an agent's directory is not somewhere a stranger gets to fill.
        failed(f"search: {len(got.brought)} files were offered and only the first "
               f"{files.PER_MESSAGE} were brought in")
    if got.partial:
        print(f"{NOT_WHOLE} — {got.partial}")
    if not where:
        return _failed(f"nothing came in from {args.fetch}"
                       + (f" — {len(refused)} would not land" if refused else ""))
    print(f"{len(where)} from {args.fetch}, in {args.agent}'s {args.channel} record")
    for at in where:
        print(at)
    return OK


def _nothing_to_search(agent: str, named: Optional[str]) -> int:
    """Why there was nothing to look through, in the words of whichever of the two it was."""
    if named:
        return _failed(f"{agent} has no {named} channel",
                       f"see what it has with: rundesk channels {agent}")
    return _failed(f"{agent} has no channels, so there is nothing to search",
                   f"connect one with: rundesk channels add {agent} <adapter> --allow <id>")


def _is_a_day(said: str) -> bool:
    """Whether this is a day, and a day that exists.

    **Parsed rather than shape-checked**, because the shapes agree and the days do not: `2026-99-99`
    has four digits, two and two, and is not a date. Refused here, where somebody is told what to
    type, rather than sent to a platform to be refused there in that platform's own words.
    """
    try:
        datetime.strptime(said, "%Y-%m-%d")
    except (ValueError, TypeError):
        return False
    return True


def _refused(kind: str, why: str) -> None:
    failed(f"search: {kind} would not search — {why}")


def _could_not(kind: str, why: str) -> None:
    failed(f"search: {kind} was not searched — {why}")


def _failed(why: str, *and_so: str) -> int:
    return failed(f"search: FAILED — {why}", *and_so)


def _mistyped(why: str) -> int:
    """The command line itself was wrong, which argparse's own code is for.

    Through `failed` like every other refusal in this product, and only the *code* differs: a
    message on stdout is a message a shell pipeline swallows into the data it was collecting.
    """
    failed(f"search: FAILED — {why}")
    return USAGE
