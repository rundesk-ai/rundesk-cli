"""Ask an agent something, here, in this terminal, and watch it work.

The attended way in. A gateway answers a channel and the clock starts a schedule; this is a person
typing, and it is the only caller that can **steer** — put a word into a turn that is already
running, which no unattended caller has anybody to get one from.

**One conversation per agent, not one per command.** Asking again carries the same exchange on, which
is what a person means by asking again. `--fresh` starts a new one on the brain.

**It shows the turn as it happens.** A brain that says several complete things while it works has
each shown as it is said, its tools are named by what they *did* rather than by whatever that vendor
calls them, and what it is thinking is shown only when asked for — reasoning is long, and a terminal
that printed all of it would bury the answer.

**It refuses rather than queues.** A conversation already being answered in is busy, and a second
turn must not begin: the claim is the kernel's, so this competes correctly with a gateway answering
the same agent on a channel, with no coordination between the two.
"""

import argparse
import sys
from typing import Any, Dict, Iterator, Optional

from rundesk.agents import directory, records
from rundesk.channels import arriving
from rundesk.commands import Subcommands, failed
from rundesk.exits import OK
from rundesk.providers import instructions, kept, protocol, turns
from rundesk.utils import terminal

#: What a tool that did something is shown as. Its own name is the *brain's* word for it, and putting
#: that in front of somebody means putting one vendor's vocabulary in front of a person who has never
#: heard of that vendor.
DID = {"read": "read", "search": "searched", "run": "ran", "edit": "edited", "list": "listed",
       "make": "made", "delegate": "delegated", "memory": "updated memory",
       "rules": "updated its rules", "identity": "updated who it is"}

#: How much of what a tool reported is shown. The whole of it is in the turn's own records; this is
#: what belongs on a line somebody is watching go past.
A_SUMMARY_AT_MOST = 100


def register(sub: Subcommands) -> None:
    """One verb, and the only one that can be steered."""
    asking = sub.add_parser("ask", help="ask an agent something, here, and watch it work")
    asking.add_argument("agent", metavar="<agent>")
    asking.add_argument("prompt", metavar="<prompt>", nargs="+", help="what to ask")
    asking.add_argument("--fresh", action="store_true",
                        help="start a new conversation on the brain rather than carrying one on")
    asking.add_argument("--read-only", action="store_true",
                        help="ask the brain to look without changing anything")
    asking.add_argument("--model", metavar="<model>",
                        help="a model name this brain understands")
    asking.add_argument("--thinking", action="store_true",
                        help="show what it is reasoning about as well as what it says")
    asking.add_argument("--quiet", action="store_true",
                        help="show only the answer")


def cmd_ask(args: argparse.Namespace) -> int:
    """A `Namespace` in, an exit code out."""
    agent = args.agent
    trouble = directory.not_an_agent(agent)
    if trouble:
        return _failed(trouble, "see what there is with: rundesk agents")
    said = " ".join(args.prompt).strip()
    if not said:
        return _failed("there was nothing to ask")

    try:
        landed = arriving.asked_at_a_terminal(agent, said)
        request = turns.Request(
            agent=agent, prompt=said, conversation=landed.conversation,
            trigger=instructions.A_PERSON_ASKED,
            access_mode=protocol.ACCESS_READ if args.read_only else protocol.ACCESS_WORK,
            model_name=args.model, fresh=args.fresh,
            source=arriving.FROM_TERMINAL, place=agent)
        shown = _Shown(args.thinking, args.quiet)
        got = turns.run(request, watching=shown.heard, saying=_typed())
    except turns.Busy as why:
        return _failed(str(why),
                       f"see what it is doing with: rundesk turns {agent}")
    except (turns.NotRunnable, directory.Refused, records.NotThere, records.Unreadable,
            kept.Refused, OSError) as why:
        return _failed(str(why))
    return _said(agent, got, args.quiet)


def _said(agent: str, got: turns.Outcome, quiet: bool) -> int:
    """The answer, and what the turn came to when it did not work."""
    if got.reply.strip():
        print(("\n" if not quiet else "") + got.reply)
    for one in got.files:
        print(terminal.dim(f"  made {one.get('name') or one.get('at')}"))
    if got.worked:
        if not quiet:
            print(terminal.dim(f"\n{_cost(got)}  ·  turn {got.turn}"))
        return OK
    return _failed(
        f"{agent} did not answer — {got.failure_message or got.turn_status}",
        *_what_to_do_about(got),
        f"what it did:  rundesk turns {agent} {got.turn}")


def _what_to_do_about(got: turns.Outcome) -> tuple:
    """The one line that says whether this is worth trying again, and who has to do something.

    The whole point of a closed vocabulary: a person reading a failure should not have to know a
    vendor's error strings to know whether to wait or to act.
    """
    if got.failure_code is None:
        return ()
    if protocol.needs_human_action(got.failure_code):
        return (f"this will not clear on its own ({got.failure_code})",)
    if protocol.is_retryable(got.failure_code):
        return (f"the same question later may work ({got.failure_code})",)
    return (f"the brain said: {got.failure_code}",)


def _cost(got: turns.Outcome) -> str:
    """What the turn cost, or that nobody said. **Zero and unknown are different answers.**"""
    used = got.usage
    if not used.usage_reported:
        return "it did not say what it cost"
    each = [f"{one} {what}" for what, one in
            (("in", used.input_tokens), ("out", used.output_tokens),
             ("cached", used.cache_read_tokens), ("written", used.cache_write_tokens))
            if one is not None]
    at = f" · {used.context_tokens} in the conversation" if used.context_tokens else ""
    return (", ".join(each) or "nothing measured") + at


class _Shown:
    """What a person watching a turn sees while it runs.

    Prose is shown when it is **finished** and never while it is being written: a reply that rewrites
    itself in place is unreadable, and a brain that says several complete things as it works is
    writing the way a person does.
    """

    def __init__(self, thinking: bool, quiet: bool):
        self.thinking = thinking
        self.quiet = quiet

    def heard(self, one: Dict[str, Any]) -> None:
        if self.quiet:
            return
        said = one.get("type")
        if said == "tool":
            print(terminal.dim(f"  {DID.get(one.get('did'), 'used a tool')}"), flush=True)
        elif said == "result" and one.get("summary"):
            print(terminal.dim(f"    {str(one['summary'])[:A_SUMMARY_AT_MOST]}"), flush=True)
        elif said == "think" and self.thinking and one.get(protocol.WHOLE):
            print(terminal.dim(f"  {one.get('text', '')}"), flush=True)
        elif said == "limit":
            print(terminal.yellow(f"  {_a_limit(one)}"), flush=True)


def _a_limit(one: Dict[str, Any]) -> str:
    """Account state a brain reported. **News about the account, never about the work** — a turn
    carrying one of these may have succeeded."""
    left = one.get("percent_left")
    resets = one.get("resets_at")
    return "allowance" + (f": {left}% left" if left is not None else "") + (
        f", back at {resets}" if resets else "")


def _typed() -> Optional[Iterator[str]]:
    """Words a person types while a turn is running, or nothing when nobody is at a terminal.

    **Only when this really is a terminal.** A turn started from a pipe or a script has an input that
    is somebody else's data, and reading it would send a script's next line into somebody's brain.
    """
    if not sys.stdin or not sys.stdin.isatty():
        return None
    return iter(_lines_typed())


def _lines_typed() -> Iterator[str]:
    """Each line somebody types, until they stop. Ends when the input does, which ends the steering.

    Blocking on its own thread inside the turn, so a person typing and a brain talking happen at the
    same time — see `turns._speaking`, which is what runs this.
    """
    for line in sys.stdin:
        said = line.strip()
        if said:
            yield said


def _failed(why: str, *and_so: str) -> int:
    return failed(f"ask: FAILED — {why}", *and_so)
