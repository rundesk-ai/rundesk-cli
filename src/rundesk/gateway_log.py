"""What a gateway is called, and the account it writes under that name.

One concern, and the code says so: a gateway's name becomes the name of its lock, its record
**and** its log, so what a name may be and where the writing lands are the same decision. A
name containing a separator would put all three somewhere else entirely.

The log is kept apart from run state on purpose — state is cleared when a gateway goes, and
history is only worth anything if it outlives the gateway that wrote it (R-GW-18).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from rundesk import data_home


#: The gateway that exists before there are agents to name one after.
DEFAULT_NAME = "gateway"

#: How a line in a gateway's log reads. One place, because anything else writing to that
#: log has to match it, and working the format out by hand somewhere else is how the two
#: come to differ with nothing to catch it.
WRITTEN_AS = "%(asctime)s %(levelname)-7s %(message)s"

#: How much a gateway may write before it starts again, and how many it keeps. A gateway
#: that has been up for a month should not be able to fill a disk, and the thing you want
#: when something happened at three in the morning is the part just before it.
LOG_BYTES = 2 * 1024 * 1024

LOG_KEEP = 3

#: Who wrote a line, for a reader asking one gateway what it has been saying. The gateway
#: writes its own, bounded and rotated; the machine that keeps the gateway up captures
#: whatever escaped the logger, which is the only place a start that died before there was
#: a logger says anything at all. Named for what wrote it rather than for what supervises
#: this machine — there is no launchd on the one CI runs half the suite on.
GATEWAY_LOG = "gateway"

MACHINE_LOG = "machine"

EVERY_LOG = "all"

LOG_SOURCES = (GATEWAY_LOG, MACHINE_LOG, EVERY_LOG)

class NotAName(ValueError):
    """A gateway name that would not stay inside the directory it belongs in."""


def checked(name: str) -> str:
    """A gateway's name becomes the name of its lock, its record and its log, so one
    containing a separator would put all three somewhere else entirely."""
    if not name or not all(ch.isalnum() or ch in "-_." for ch in name) or name.strip(".") == "":
        raise NotAName(
            f"'{name}' is not a usable name — letters, digits, dash, dot and underscore"
        )
    return name


def logs_home() -> Path:
    """Where gateways write what happened. Kept apart from what they are *doing* now, in
    `home()`: that is state, cleared when a gateway goes, and this is history, which is
    only worth anything if it outlives the gateway that wrote it (R-GW-18)."""
    return Path(os.environ.get("RUNDESK_LOG_DIR") or data_home() / "logs")


def log_path(name: str, logs: Path | None = None) -> Path:
    """The file a gateway of this name writes to — what `rundesk logs` reads."""
    return (logs or logs_home()) / f"{checked(name)}.log"


def log_sources(name: str, logs: Path | None = None,
                source: str = EVERY_LOG) -> list[tuple[str, Path]]:
    """Every file a gateway of this name has said anything into, oldest first (R-GW-36).

    Two things write about one gateway and only one of them was ever readable. The
    gateway's own log rotates, so the lines explaining the tail live in `.log.1`; and
    what never reaches the logger at all — an interpreter traceback, a task nobody
    awaited, a refusal to start printed before there was a logger — lands only in what
    the machine captured. `rundesk logs` is what a failed start tells the owner to run,
    so it has to reach both or it answers the one question it exists for with silence.
    """
    where = logs or logs_home()
    plain = checked(name)
    found: list[tuple[str, Path]] = []
    if source in (GATEWAY_LOG, EVERY_LOG):
        # Oldest first: the rotation numbers count backwards, so reading them in reverse
        # puts one gateway's account back into the order it was written.
        for older in range(LOG_KEEP, 0, -1):
            found.append((GATEWAY_LOG, where / f"{plain}.log.{older}"))
        found.append((GATEWAY_LOG, where / f"{plain}.log"))
    if source in (MACHINE_LOG, EVERY_LOG):
        for ours in (".out", ".err"):
            found.append((MACHINE_LOG, where / f"{plain}{ours}"))
    return [(said, path) for said, path in found if path.exists()]


def note(name: str, said: str, logs: Path | None = None) -> str | None:
    """Add a line to a gateway's log from outside the gateway, and say if it could not be.

    Formatted by the same formatter the gateway itself writes through, rather than
    worked out by hand: a change to how a line reads would otherwise leave these lines
    looking like something else, in the one account that outlives the gateway.

    The reason comes back rather than being swallowed (R-GW-37). A schedule added in a
    home nothing had written yet printed ADDED, kept the change, and left no audit line
    anywhere — a mutation and its history disagreeing, silently, on the first use.

    The directory is made here because this is the first thing to write into a clean
    home as often as not, and a caller that has to make somewhere for a log before it
    can be told about a failure has been given the failure twice.
    """
    record = logging.LogRecord(f"rundesk.gateway.{name}", logging.INFO, "", 0, said, None, None)
    target = log_path(name, logs)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Appended by path, from a process that is not the gateway, while the gateway's
        # own handler rotates by rename. A line written across a rotation lands in
        # `.log.1` — which is read back, in order, by `log_sources` above, so it is
        # somewhere else rather than lost.
        with open(target, "a", encoding="utf-8") as log:
            log.write(logging.Formatter(WRITTEN_AS).format(record) + "\n")
    except OSError as why:
        return str(why)
    return None


def recorder(name: str, logs: Path) -> logging.Logger:
    """A log for one gateway, and no other.

    Built rather than fetched from the logging registry: two gateways in one process
    would otherwise share a name and write each other's lines, and nothing in this module
    is shared between two gateways.
    """
    logs.mkdir(parents=True, exist_ok=True)
    keeping = logging.Logger(f"rundesk.gateway.{name}", logging.INFO)
    to_file = logging.handlers.RotatingFileHandler(
        log_path(name, logs), maxBytes=LOG_BYTES, backupCount=LOG_KEEP, encoding="utf-8"
    )
    to_file.setFormatter(logging.Formatter(WRITTEN_AS))
    keeping.addHandler(to_file)
    # Also said out loud, but only to a person watching (R-GW-35). A gateway run in a
    # terminal shows its working; one run by the machine had every line copied into a
    # file nothing rotated, nothing read and no requirement mentioned — an unbounded
    # shadow of a log that exists to be bounded. What the machine captures is worth
    # keeping for what the logger never sees, and worthless as a second copy of what it
    # does. `isatty` can refuse to answer on a stream somebody has replaced; a stream
    # that cannot say it is a terminal is not one.
    try:
        watched = sys.stderr is not None and sys.stderr.isatty()
    except (AttributeError, ValueError):
        watched = False
    if watched:
        aloud = logging.StreamHandler(sys.stderr)
        aloud.setFormatter(logging.Formatter(f"rundesk {name}: %(message)s"))
        keeping.addHandler(aloud)
    return keeping


def channel_note(log, name: str, said: str) -> None:
    """Keep adapter diagnostics at the severity the adapter stated (R-GW-44).

    Unclassified stderr remains a warning for adapters written before the level marker
    existed. Silently demoting an unknown third-party adapter's failure would be worse
    than retaining its existing severity.
    """
    line = said.rstrip()
    level, marker, message = line.partition("\t")
    if marker and level == "INFO":
        log.info("channel '%s': %s", name, message)
        return
    if marker and level == "WARNING":
        line = message
    log.warning("channel '%s': %s", name, line)
