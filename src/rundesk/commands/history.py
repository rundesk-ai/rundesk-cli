"""What an agent has already done: its runs, what they cost, what was said, and the log.

All reading and no writing. Everything here goes through the store or through the gateway's
own log, and none of it may change either — an owner asking what happened is usually asking
because something went wrong, and an answer that altered what it reported would be a
different answer the next time it was asked.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from rundesk import migration
from rundesk import store
from rundesk.commands import _as_table


#: How much of a provider's name a listing shows. Long enough for every shipped adapter and
#: for the end of a path; the whole of it is in the record.
_ANSWERED_BY_CHARS = 28

#: How much of one message is shown. Far more than a search result shows, because these are
#: read for their content rather than scanned for a hit — an agent working out what it was
#: told needs the sentence, not the fact that a sentence exists. The whole of it is in the
#: record; `--most 1` on one id is how a reader asks for that.
_MESSAGE_CHARS = 255

#: How much of one thing said is shown in a listing. The whole of it is in the record; this
#: is what fits on a line beside four other columns.
_SAID_CHARS = 80

#: How many of a gateway's last lines `logs` shows when not told otherwise. The parser reads
#: it from here, so what the surface offers and what the command means cannot disagree.
LOG_LINES = 40


def _reading(name: str, agents) -> "store.Store | None":
    """What this agent keeps, opened for a command that only asks.

    `None` where the answer is a refusal already printed, so the three read-only verbs
    below say the same thing when an agent is missing or its records will not be read —
    written once, because three of them saying it three ways is three ways to be wrong.
    """
    if not agents.exists(name):
        print(f"{name}: NO SUCH AGENT — nothing of that name has been made", file=sys.stderr)
        print("        what there is:  rundesk agents", file=sys.stderr)
        return None
    try:
        return agents.reading(name)
    except (store.Unreadable, store.TooNew, store.Behind, migration.Failed) as why:
        print(f"{name}: RECORDS UNREADABLE — {why}", file=sys.stderr)
        print(f"        what stands in the way:  rundesk doctor {name}", file=sys.stderr)
        return None


def _wants_a_name(verb: str) -> int:
    """Refuse a verb that is about one agent and was given none, in our own words.

    Never argparse's usage code: a script has to be able to tell a command that is not
    there from one it typed wrongly, and that is the whole distinction (R-CMD-8).
    """
    print(f"{verb}: NAME REQUIRED — say which agent", file=sys.stderr)
    print("        what there is:  rundesk agents", file=sys.stderr)
    return 1


def cmd_runs(args: argparse.Namespace, gateways, agents) -> int:
    """What this agent has run, newest first.

    Read from what it keeps, with nothing started: a night's work is asked about far more
    often than it is done, and a listing that had to run a brain to answer would be one
    nobody uses (R-USE-10).
    """
    if not args.name:
        return _wants_a_name("runs")
    kept = _reading(args.name, agents)
    if kept is None:
        return 1
    found = kept.runs(limit=max(1, args.most))
    if not found:
        print(f"{args.name}: NOTHING RUN YET")
        print(f'        ask it something:  rundesk ask {args.name} "…"')
        return 0
    # Which schedule, where there was one. `source` alone says the clock started it and
    # leaves an owner to work out which of their schedules that was — and the whole reason to
    # read this at all is that something happened while nobody was watching.
    named = {row["id"]: row["name"] for row in kept.schedules()}
    _as_table(("RUN", "WHEN", "SOURCE", "ANSWERED BY", "OUTCOME", "COST"), [
        (one["id"], str(one["started_at"]), _admitted_by(one, named),
         _answered_by(one["provider"]), _came_to(one), _spent(one))
        for one in found
    ])
    return 0


def _came_to(one: dict) -> str:
    """What became of this run, and the word for why where the brain gave one (R-RUN-19).

    `failed` on its own answers "did it work" and not "what do I do about it" — a turn
    stopped by an account limit reads exactly like a crashed adapter or a bad flag. The word
    is added rather than substituted, so the outcome column still says the one thing it has
    always said and can still be grepped for.

    Absent for every run whose adapter did not classify the failure, which is every run
    written before there was a column for it. Nothing is inferred from the prose in `why`.
    """
    became = str(one["outcome"] or "running")
    word = one.get("because")
    return f"{became} ({word})" if word else became


def _admitted_by(one: dict, named: dict) -> str:
    """What started this run, said the way an owner would ask about it (R-RUN-16).

    A schedule is named rather than merely reported as one: a listing of six runs that all
    say `schedule` is a listing that answers "was this me?" and not "which of mine was it?".
    A schedule that has since been removed leaves the run saying what kind it was, because
    the run outlives it.
    """
    said = str(one["source"])
    which = named.get(one.get("schedule_id"))
    return f"{said} '{which}'" if which else said


def _answered_by(named: str) -> str:
    """Which provider answered, as the owner named it — elided from the front if it is a path.

    Their own words rather than the settled form that names its private directory: that one
    carries a hash so two adapters of one name cannot share a directory, and nobody typed a
    hash. A long path keeps its end, because the part that tells one adapter from another is
    the last of it.
    """
    said = str(named or "-")
    return said if len(said) <= _ANSWERED_BY_CHARS else "…" + said[-(_ANSWERED_BY_CHARS - 1):]


def _spent(one: dict) -> str:
    """What one run cost, or that nobody said.

    A cost that never arrived reads as unknown rather than as nothing: a run that cost an
    unknown amount and one that cost zero are different facts, and a total that folded the
    first into the second would quietly claim to know more than it does (R-USE-7).
    """
    if not one["tokens_reported"]:
        return "not reported"
    # **Cached input is shown where the provider reported it** (R-USE-12). It is billed and
    # routinely dwarfs the fresh input beside it — one agent's fifty-six runs carried 101,510
    # fresh and 4,684,800 cached — so a row naming only the other two hid the whole of what
    # the run actually cost, and hid which conversations should have been started again.
    # Absent stays absent rather than becoming zero: a provider that reports no cache and one
    # that read nothing from it are different facts (R-USE-6).
    cached = one.get("tokens_cached")
    held = "" if cached is None else f" / {cached} cached"
    # **Cache writes are shown apart from fresh input** (R-USE-13), on the same rule as the
    # line above and for the opposite reason: a write is billed *above* fresh input, so a
    # run that folded them together priced its most expensive tokens as its cheapest. Absent
    # on every brain that does not report the split, and on every row written before there
    # was a column for it — where the two cannot be separated after the fact.
    written = one.get("tokens_written")
    made = "" if written is None else f" / {written} written"
    return f"{one['tokens_in'] or 0} in{held}{made} / {one['tokens_out'] or 0} out"


def cmd_usage(args: argparse.Namespace, gateways, agents) -> int:
    """What an agent has cost, in tokens. Every agent when none is named."""
    wanted = [args.name] if args.name else agents.known()
    if not wanted:
        print("NO AGENTS — nothing has cost anything yet")
        print("        make one:  rundesk add <agent> --provider <provider>")
        return 0
    rows = []
    for name in wanted:
        kept = _reading(name, agents)
        if kept is None:
            return 1
        spent = kept.usage()
        rows.append((
            name, str(spent["runs"]),
            # Absent rather than zero, all the way out to what is printed. `SUM` over no
            # rows is NULL and a run whose usage never arrived leaves it so, which is the
            # one distinction a spend limit reading this must not lose (R-USE-6).
            "-" if spent["input"] is None else str(spent["input"]),
            "-" if spent["output"] is None else str(spent["output"]),
            "-" if spent["cached"] is None else str(spent["cached"]),
            "-" if spent["written"] is None else str(spent["written"]),
            str(spent["unreported"]),
        ))
    _as_table(("AGENT", "RUNS", "IN", "OUT", "CACHED", "WRITTEN", "NOT REPORTED"), rows)
    return 0


def cmd_messages(args: argparse.Namespace, gateways, agents) -> int:
    """What has been said, newest first, across every surface this agent is reached on.

    The listing an agent reads about itself. `runs` says that work happened and `search`
    needs a word nobody always has — this is the one that answers "what was I just told,
    and what did I say", which is what a turn resuming a conversation it has no session for
    actually needs (R-STO-25).
    """
    if not args.name:
        return _wants_a_name("messages")
    kept = _reading(args.name, agents)
    if kept is None:
        return 1
    try:
        found = kept.latest(limit=max(1, args.most), since=args.since,
                            channel=args.channel, author=args.author, source=args.source,
                            conversation=args.conversation, who=args.who)
    except ValueError as why:
        # The closed sets say what they are rather than being quietly ignored, so a filter
        # nobody can spell is refused instead of answering a different question (R-STO-26).
        print(f"{args.name}: {why}", file=sys.stderr)
        return 1
    if not found:
        if args.conversation and not kept.has_conversation(args.conversation):
            # A conversation nobody has and a conversation with nothing in it are different
            # answers, and returning the empty listing for both is how an agent comes to
            # report that work it did never happened (R-STO-28).
            print(f"{args.name}: no conversation called {args.conversation}", file=sys.stderr)
            print("        the WHERE column names every one it has:  "
                  f"rundesk messages {args.name}", file=sys.stderr)
            return 1
        print(f"{args.name}: NOTHING SAID YET")
        print(f'        ask it something:  rundesk ask {args.name} "…"')
        return 0
    _as_table(("ID", "WHEN", "WHERE", "WHO", "MESSAGE"), [
        (str(one["id"]), str(one["at"]), f"{one['channel']}/{one['space']}",
         _said_by(one, args.name), " ".join(str(one["text"]).split())[:_MESSAGE_CHARS])
        for one in found
    ])
    return 0


def _said_by(one: dict, named: str) -> str:
    """Who said it: a person by their name, and the agent by its own.

    Two people in two direct messages are two conversations and would otherwise both read
    as `user`, which is the one thing this column exists to tell apart. A surface reports
    the name it shows a human — Discord hands over a display name rather than a number —
    and it is kept on the message, so it is shown wherever there is one.

    **The agent is named too**, because a listing that was asked for by name and answers
    `agent` spends a column saying the one thing its reader already knew. Said here rather
    than kept on the row: these are one agent's records, so the name is already the
    directory they stand in, and a copy on every message is a second place for it to be
    wrong. What stays generic is `rundesk` itself, which is not the agent and never a
    person.
    """
    if one.get("who"):
        return str(one["who"])
    return named if one["author"] == "agent" else str(one["author"])


def cmd_search(args: argparse.Namespace, gateways, agents) -> int:
    """What was said about something, wherever it was said and whoever said it.

    Unavailable is said out loud rather than answered as nothing found (R-STO-8): an empty
    answer and an impossible question look identical to whoever typed it, and one of them
    means "go and look somewhere else".
    """
    if not args.name or not args.words:
        print("SEARCH NEEDS AN AGENT AND SOMETHING TO LOOK FOR", file=sys.stderr)
        print(f'        like this:  rundesk search {args.name or "<agent>"} "the parser"',
              file=sys.stderr)
        return 1
    kept = _reading(args.name, agents)
    if kept is None:
        return 1
    try:
        found = kept.search(args.words, limit=max(1, args.most))
    except store.Unsearchable as why:
        print(f"{args.name}: SEARCHING UNAVAILABLE — {why}", file=sys.stderr)
        print("        every run is still listed and read:  rundesk runs "
              f"{args.name}", file=sys.stderr)
        return 1
    if not found:
        print(f"{args.name}: NOTHING SAID ABOUT THAT")
        return 0
    _as_table(("WHEN", "WHERE", "WHO", "SAID"), [
        (str(one["at"]), f"{one['channel']}/{one['space']}", str(one["author"]),
         " ".join(str(one["text"]).split())[:_SAID_CHARS])
        for one in found
    ])
    return 0


def cmd_logs(args: argparse.Namespace, gateways, agents) -> int:
    """What a gateway has been saying. Reads the files, so a gateway that has gone can
    still be asked what happened (R-GW-18, R-GW-36).

    Every source, not one file. A failed start tells the owner to run this, and the line
    explaining it is as likely to be in the rotation behind the current log, or in what
    the machine captured before there was a logger at all, as in the tail of `.log` —
    so reading only the last file answered the question this command exists for with
    NO LOG while the answer sat beside it.
    """
    logs = agents.resolved(args.name).logs
    found = gateways.log_sources(args.name, logs, args.source)
    if not found:
        print(f"{args.name}: NO LOG — nothing written yet ({gateways.log_path(args.name, logs)})",
              file=sys.stderr)
        return 1
    # One gateway's own account is one stream that rotation happens to have cut up, so
    # it is put back together before the tail is taken; what the machine captured is a
    # different account of the same gateway, and each of those is tailed on its own.
    streams: list[tuple[str, list[str]]] = []
    for whose, path in found:
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError as why:
            # Every other verb answers in our words when it cannot do the thing. A log
            # that cannot be read is a thing to be told about, not a traceback.
            print(f"{args.name}: FAILED — could not read the log: {why}", file=sys.stderr)
            return 1
        if streams and streams[-1][0] == whose == gateways.GATEWAY_LOG:
            streams[-1][1].extend(lines)
        else:
            streams.append((whose, lines))
    shown = [(whose, lines[-args.lines:] if args.lines > 0 else []) for whose, lines in streams]
    shown = [(whose, lines) for whose, lines in shown if lines]
    labelled = len({whose for whose, _ in shown}) > 1
    for whose, lines in shown:
        for line in lines:
            print(f"{whose:<8}{line}" if labelled else line)
    return 0
