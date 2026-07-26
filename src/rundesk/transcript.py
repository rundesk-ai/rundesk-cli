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

from pathlib import Path

#: What each is called. The brain's own stream keeps the suffix its contents deserve: it is
#: a stream of JSON records, whatever any particular adapter chooses to put in it.
PRINTED = ".jsonl"
ERRORS = ".err"

#: The directory the two stand in, under the agent's logs.
RUNS = "runs"


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
