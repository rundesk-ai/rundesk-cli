"""What a brain itself printed, and what it said went wrong — the two files beside a run.

Everything a run *recorded* is in what the agent keeps, and is asked for through
[`store.py`](store.py). What is here is the two things that cannot be a row:

    logs/runs/<run>.jsonl   what the brain printed, as it printed it. Its path is handed
                            to the adapter through `RUNDESK_RAW`, and an adapter may be a
                            shell script — you cannot hand one a database handle.
    logs/runs/<run>.err     what it said went wrong. An operating-system pipe.

**Both may be destroyed to reclaim space**, so nothing a run recorded is recoverable only
from them (R-STO-5): every line an adapter produced is a row as well, understood or not.
That is the whole reason they are kept apart from the account rather than inside it, and it
is what makes deleting `logs/` cost an owner nothing they need.

They stand under `logs/` rather than beside the records because that is what they are —
diagnostics, of a piece with the gateway's own log, and swept by the same broom.

**`.jsonl` is the one file nothing here writes.** An adapter is a program: what its *brain*
said before the adapter made records of it never passes through rundesk at all, so without
somewhere to put it, a vendor changing its stream shape would show up as records quietly
going missing rather than as drift anybody could look at. The adapter is told where the file
is and may append to it; one that does not is a perfectly good adapter, and it is not there.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

#: What each is called. The brain's own stream keeps the suffix its contents deserve: it is
#: a stream of JSON records, whatever any particular adapter chooses to put in it.
PRINTED = ".jsonl"
ERRORS = ".err"

#: The directory the two stand in, under the agent's logs.
RUNS = "runs"

#: How much of one run's stream is worth keeping. The same bound the gateway's own log
#: has had all along (`gateway_log.LOG_BYTES`), for the same reason and against a worse case:
#: a brain replays the whole prior thread when it attaches, so on a long conversation the
#: dominant content of every run is the *previous* runs, written again — measured at 26 MB
#: per run across six consecutive runs of one conversation, growing with each turn. The end
#: is what is kept, because that is this run and the beginning is the replay (R-RUN-22).
CEILING_BYTES = 4 * 1024 * 1024

#: How long what a brain printed is kept. These files are diagnostics and may be destroyed
#: to reclaim space without costing the account anything (R-STO-5), and a week is long
#: enough to look into a turn somebody is still asking about. Nothing swept them at all
#: before, which read as 807 MB across 384 files against 7.7 MB of actual records
#: (R-RUN-23).
KEEP_DAYS = 7


def home(logs) -> Path:
    """Where what a brain printed is kept, given where this agent's logs are."""
    return Path(logs) / RUNS


def printed(logs, run: str) -> Path:
    """What the brain printed during this run — the path an adapter is handed."""
    return home(logs) / (run + PRINTED)


def beside(logs, run: str) -> Path:
    """What it said went wrong during this run."""
    return home(logs) / (run + ERRORS)


def kept(logs, run: str) -> list:
    """Both files for one run, whether or not either is there.

    Named in one place, so that removing a run and sweeping what a brain printed take the
    same list that writing it made. A second list is one that falls behind.
    """
    return [printed(logs, run), beside(logs, run)]


def read(logs, run: str, which: str = PRINTED) -> bytes:
    """One of them, exactly as it was written. Missing is empty, which is what it means."""
    try:
        return (home(logs) / (run + which)).read_bytes()
    except OSError:
        return b""


def trim(logs, run: str, ceiling: int = CEILING_BYTES) -> int:
    """Cut what a brain printed down to the ceiling, keeping the end. Says how much went.

    **The end, never the beginning (R-RUN-22).** What an adapter appends first is the
    handshake and, on a resumed conversation, the entire prior thread replayed back at it;
    what it appends last is this turn. Keeping the head would keep the one part already on
    disk under the runs it actually belongs to, and throw away the only copy of the part
    that is new.

    Rundesk never writes this file — an adapter does, and may be a shell script — so the
    ceiling is applied once the adapter has finished with it rather than as it is written.
    A whole line is what is kept: cutting at a byte offset lands mid-record, and a `.jsonl`
    whose first line is half a record is one nothing can read.

    Doing nothing is the ordinary outcome. A file under the ceiling, absent, or unreadable
    is left exactly as it is: this reclaims space and is never allowed to be the reason a
    turn fails.
    """
    at = printed(logs, run)
    try:
        held = at.stat().st_size
    except OSError:
        return 0
    if held <= ceiling:
        return 0
    aside = at.with_name(at.name + ".trimming")
    try:
        with open(at, "rb") as whole, open(aside, "wb") as keeping:
            whole.seek(held - ceiling)
            whole.readline()                    # the partial record at the cut, dropped
            elided = whole.tell()
            keeping.write(json.dumps({
                "type": "elided",
                "by": "rundesk",
                "bytes": elided,
                "why": f"what this brain printed was over {ceiling} bytes; the beginning "
                       f"was dropped and the end of the run kept",
            }).encode("utf-8") + b"\n")
            while True:
                block = whole.read(1024 * 1024)
                if not block:
                    break
                keeping.write(block)
        os.replace(aside, at)
        return elided
    except OSError:
        # The transcript as it stands is better than no transcript, and better than a
        # turn that failed while tidying up after itself.
        try:
            os.remove(aside)
        except OSError:
            pass
        return 0


def sweep(logs, keep_days: int = KEEP_DAYS, now=None) -> list:
    """Take away what brains printed longer ago than this, and say whose runs they were.

    **The broom this module has always claimed to be swept by (R-RUN-23).** These stand
    under `logs/` because they are diagnostics, of a piece with the gateway's own log —
    which is bounded and rotated. Nothing bounded these, and an agent holding a hundred
    times more abandoned transcript than records is the ordinary result rather than the
    unlucky one.

    Both files of a run go together or neither does, so a run is never left with half of
    what it printed. A directory that cannot be read is nothing to sweep, not an error:
    reclaiming space is never worth failing a gateway over.
    """
    at = home(logs)
    if keep_days <= 0 or not at.is_dir():
        return []
    oldest = (time.time() if now is None else now) - keep_days * 86400
    swept = []
    for run in known(logs):
        try:
            if printed(logs, run).stat().st_mtime >= oldest:
                continue
        except OSError:
            continue
        for one in kept(logs, run):
            try:
                one.unlink()
            except OSError:
                pass
        swept.append(run)
    return swept


def known(logs) -> list:
    """Every run this agent has what a brain printed for.

    What is *on disk*, asked of the disk — never a list of runs, which is what the records
    are for. The two are compared rather than assumed to agree: a run whose file has been
    swept is ordinary, and a file whose run is unknown is not.
    """
    at = home(logs)
    if not at.is_dir():
        return []
    return sorted(one.name[: -len(PRINTED)] for one in at.glob("*" + PRINTED))
