"""What a run did, written down while it did it — the thing all of this is for.

An agent that worked all night is only worth having if what it did can be read back. So
every run writes an account of itself, one record to a line, added to and never rewritten
(R-RUN-5), and it outlives the gateway that wrote it (R-RUN-10).

**Three files, because they are thrown away at different times.**

    <run>.jsonl   the account   — what happened, in rundesk's words. Small, and kept.
    <run>.raw     stdout        — every line the brain said, byte for byte.
    <run>.err     stderr        — every line it said went wrong, byte for byte.

The account is what a channel renders and what a cost is read from, and it is written in
a vocabulary no brain owns, so nothing downstream ever learns a vendor's words. The two
raw files are the whole of what the brain gave us, kept so that a format that drifts can
be probed and adapted to rather than guessed at — and kept *separately* so a retention
policy can one day drop them and leave the account standing. Deleting a whole file is not
rewriting one, which is how both rules hold at once.

**Order does not depend on a clock (R-RUN-7).** `seq` counts from nothing, per run, so
concatenating two runs of one conversation reads in the order the work happened whatever
the machine's clock did in between (R-RUN-8). `at` is wall time, for a person reading it,
and is never what anything is sorted by.

**This module knows nothing about brains.** It is told an event and given a raw line, and
it writes them down. What the six kinds of record are, and which line is one of them, is
`provider`'s — so a vocabulary that grows never reaches this file.
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

from rundesk_cli import gateway

#: Where the count of runs is kept, so a new one is never numbered behind an old one.
#: Inside the run directory, because it is about those runs and nothing else — and it is
#: only ever a hint: the directory itself is the truth, and a lost count is caught by the
#: file that already stands under the name it would hand out.
ALLOCATING = "allocating.json"

#: What is added to a run's number to keep two of them apart. Numbers alone would be
#: enough within one machine; this makes a transcript copied off one and read beside
#: another's still obviously a different run.
MARK_FROM = "abcdefghijklmnopqrstuvwxyz0123456789"
MARK_LENGTH = 4

#: What each of a run's files is called. The account is what survives a pruning; the
#: other two are what a pruning takes.
ACCOUNT = ".jsonl"
RAW = ".raw"
ERRORS = ".err"
KEPT = (RAW, ERRORS)


def _marked(pick=None) -> str:
    picking = pick or random.choice
    return "".join(picking(MARK_FROM) for _ in range(MARK_LENGTH))


def allocate(runs: Path, pick=None) -> str:
    """A run of this agent's own, numbered after every run before it (R-RUN-1).

    Numbered rather than stamped, so the order runs were admitted in survives a clock
    that went backwards, a machine in another timezone, and two transcripts read side by
    side (R-RUN-7). The count is kept beside them and the name is claimed under the same
    hold, so two turns admitted at once cannot be given one id — and if the count is ever
    lost, the file already standing under a name is what catches it.
    """
    runs.mkdir(parents=True, exist_ok=True)
    with gateway.changing(runs / ALLOCATING, {}, "the count of runs") as counted:
        after = int(counted.get("last") or 0)
        while True:
            after += 1
            named = f"{after}-{_marked(pick)}"
            try:
                os.close(os.open(runs / (named + ACCOUNT),
                                 os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            except FileExistsError:
                continue  # the count was behind the directory; the directory wins
            counted["last"] = after
            return named


class Writer:
    """One run's three files, open for as long as the run lasts.

    Held open rather than reopened per record: a turn writes a record at a time for
    however long the work takes, and opening a file for each would be the same decision
    made thousands of times. Flushed on every record, because the point of an account is
    that it is readable while the thing it accounts for is still happening.
    """

    def __init__(self, runs: Path, run: str, agent: str, now=None):
        self.run = run
        self.agent = agent
        self._now = now or time.time
        self._seq = 0
        runs.mkdir(parents=True, exist_ok=True)
        self._account = open(runs / (run + ACCOUNT), "a", encoding="utf-8")
        self._raw = open(runs / (run + RAW), "ab")
        self._errors = open(runs / (run + ERRORS), "ab")

    def add(self, event: dict | None = None, raw: bytes | None = None) -> int:
        """Write one record down, and say where in the run it stood.

        `event` is what rundesk made of it and `raw` is what the brain actually said, and
        either may be absent. A record of a kind nobody here knows arrives with a raw
        line and no event: the account keeps its place in the order and says nothing
        about it, the raw file keeps it verbatim, and the turn carries on (R-PRV-5).
        """
        self._seq += 1
        if raw is not None:
            self._raw.write(raw if raw.endswith(b"\n") else raw + b"\n")
            self._raw.flush()
        line = {"run": self.run, "agent": self.agent, "seq": self._seq,
                "at": _stamped(self._now())}
        if event is not None:
            line["event"] = event
        self._account.write(json.dumps(line, sort_keys=True) + "\n")
        self._account.flush()
        return self._seq

    def went_wrong(self, said: bytes | str) -> None:
        """One line of what the brain said went wrong, kept and kept apart (R-PRV-6).

        Never given a place in the account: this is what went wrong rather than what
        happened, and a reader that could not tell them apart would be reading a brain's
        warnings as its work.
        """
        data = said if isinstance(said, bytes) else said.encode("utf-8", "replace")
        self._errors.write(data if data.endswith(b"\n") else data + b"\n")
        self._errors.flush()

    def close(self) -> None:
        for one in (self._account, self._raw, self._errors):
            try:
                one.close()
            except OSError:
                pass  # a run's account is written as it goes; nothing is owed at the end

    def __enter__(self) -> "Writer":
        return self

    def __exit__(self, *gone) -> None:
        self.close()


def _stamped(when: float) -> str:
    """Wall time, for a person reading it. Never what anything is ordered by (R-RUN-7)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when))


def read(runs: Path, run: str) -> list[dict]:
    """One run's account, in the order it happened (R-RUN-4).

    Read straight off the file with no gateway anywhere near it, which is what makes an
    account outlive the thing that wrote it (R-RUN-10). A line that cannot be read is
    skipped rather than fatal: an account with a torn last line — a machine that lost
    power mid-record — is still the account of everything before it.
    """
    at = runs / (run + ACCOUNT)
    if not at.is_file():
        return []
    said = []
    for line in at.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            said.append(one)
    return said


def raw(runs: Path, run: str, which: str = RAW) -> bytes:
    """Everything the brain said, exactly as it said it — or nothing, once it is pruned."""
    at = runs / (run + which)
    return at.read_bytes() if at.is_file() else b""


def known(runs: Path) -> list[str]:
    """Every run this agent has, oldest first.

    Sorted on the number rather than the name, because run ten sorts before run nine as
    text and an account read in the wrong order is worse than none.
    """
    if not runs.is_dir():
        return []
    return [named for _, named in sorted(
        (_numbered(at.name[:-len(ACCOUNT)]), at.name[:-len(ACCOUNT)])
        for at in runs.iterdir()
        if at.is_file() and at.name.endswith(ACCOUNT) and at.name != ALLOCATING
    )]


def _numbered(run: str) -> int:
    before, _, _ = run.partition("-")
    return int(before) if before.isdigit() else 0


def events(runs: Path, run: str, kind: str | None = None) -> list[dict]:
    """What rundesk understood of this run, without the lines it did not."""
    return [one["event"] for one in read(runs, run)
            if isinstance(one.get("event"), dict)
            and (kind is None or one["event"].get("type") == kind)]
