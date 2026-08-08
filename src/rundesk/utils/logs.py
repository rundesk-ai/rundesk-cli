"""A day of lines in a file named after that day, and keeping only the last so many days.

**Retention is asked for in days, so it is kept in days.** A size-rotated log answers "three files of
two megabytes", which is however long that happens to be — a quiet week or a bad afternoon, and
nobody can tell you which. Nobody can answer *what happened on the second?* from `gateway.log.2`
either. A file per day answers both questions by its name, and sweeping is arithmetic on a date.

**There is no rollover, so there is no rollover to race.** Most of what writes here is short-lived
and several of them run at once — somebody typing a command, a scheduled job, an update — and a
size-rotated handler in two processes renames the file out from under the other one, interleaving or
losing the roll. Appending to a file named after today has no step to get wrong: two writers open the
same name and both are simply appending.

**A single write to a file opened `O_APPEND` lands whole.** The kernel takes the offset and the write
together, so concurrent writers interleave complete lines rather than tearing one in half. That is
the property the whole scheme rests on, so every line is one `write` of one string, and nothing here
keeps a file open between calls — a long-lived process holding a handler open on yesterday's file
would go on writing into it long after midnight, which is the shape this replaces.

**Days are the machine's own days, and so are the times on the lines.** The question a person asks a
log is *what happened at nine last night, when I noticed?*, and every other account of the same
machine — `ls`, Console, `log show`, the clock they read the time off — answers in local time. A log
in UTC makes the one reader who exists do arithmetic every time, to spare a reader in another
timezone who does not. The name of the file and the times inside it come from the same moment, so the
day somebody opens is the day whose lines are in it.

**Every line carries its offset**, which is what makes local time safe rather than merely convenient.
Across a daylight-saving fall-back the local clock reads `01:30` twice, and a bare local stamp is
ambiguous and out of order in exactly the hour somebody is most likely to be reading about something
odd. `01:30:00-07:00` and `01:30:00-08:00` are plainly an hour apart with nothing to work out. The
honest consequence, which somebody will meet: in that one file the lines sort oddly *as text* while
being in the right order in time. The offset is right there to say so, and the alternative is two
identical stamps an hour apart.

**Writing a line never fails a command.** A log is an account of the work, not the work — a backup
that could not write its own note is a backup that succeeded. That is exactly why reading must keep
"could not be read" as its own answer: with writing silent about failure, the reader is where a
person finds out.

**One file is not on that scheme, and it is not on it because it is not ours to name.** A supervisor
asked to capture a program's standard output opens the one path it was given, appends to it across
every restart of that program for ever, and neither truncates nor rotates it — so it is the one file
here that grows without anything deciding it should. A day-stamped name is not available to it: the
name was fixed in the supervisor's own configuration long before today, so a capture called after a
day would be named for the day that configuration was written and not for the day the lines landed.
`swept` cannot reach it either, because `swept` takes the age from the name and that name carries no
day. So `rotated` stands beside them and answers in the only terms a file somebody else writes can be
asked about: **by size**, because size is the one thing measurable about content nobody here chose,
and **by content**, because the descriptor is somebody else's too and moving the name out from under
an open one leaves it writing into a file nobody will look in. See `rotated` for the whole of that.

Beyond `files` — whose three words for how a read went are named again here rather than invented a
second time — this imports the standard library and nothing else. Knows nothing about rundesk: what
it is handed is a directory, and it has never been told whose.
"""

import contextlib
import datetime
import os
import re
from pathlib import Path
from typing import List, NamedTuple, Optional, Tuple

from rundesk.utils import files

#: What a day's file is called, and the shape a name must have to be one of ours.
#:
#: Sorting these names sorts the days, which is the whole reason for the order of the fields —
#: everything here reads the directory in date order without parsing a thing.
DAY = "%Y-%m-%d"
ENDS_WITH = ".log"
NAMED_FOR_A_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}\.log$")

#: How serious a line is: four words, and there is no fifth.
#:
#: **Four rather than PSR-3's eight.** A vocabulary that also holds `NOTICE`, `CRITICAL`, `ALERT`
#: and `EMERGENCY` is one nobody agrees the middle of, and what happens in practice is that
#: everything worth noticing becomes `ERROR` and the ladder stops carrying information. Named as
#: constants so a caller reaches for one instead of inventing another.
DEBUG = "DEBUG"
INFO = "INFO"
WARNING = "WARNING"
ERROR = "ERROR"
LEVELS = (DEBUG, INFO, WARNING, ERROR)

#: `[<when>] <LEVEL>: <what happened>`, one line each. The level is padded to the longest of the
#: four, so that a screen of lines reads as columns rather than as ragged prose.
SAID = "[{when}] {level} {said}\n"
WIDEST = max(len(one) for one in LEVELS) + len(":")

#: The same three answers `utils.files` gives, in the words this question is asked in. Named again
#: rather than spelled again: two modules with their own vocabulary for one distinction are two
#: modules that eventually disagree about it.
READ = files.READ
NOTHING_YET = files.MISSING
UNREADABLE = files.UNREADABLE

#: How much of the end of a file is read at a time while walking backwards. Big enough that twenty
#: ordinary lines are found in one read, small enough that answering never depends on the file size.
BLOCK_BYTES = 8192

#: What a file moved aside by `rotated` is called: `<name>.1` is the one that has just gone, and
#: `<name>.<keeping>` the oldest still kept. Numbered rather than named for a day, because nothing
#: here knows which day the lines inside were written on — see the module docstring.
ROTATED = "{name}.{which}"

#: The last line of every copy `rotated` makes, because every copy is a cut: a file is only moved
#: aside once it holds more than one kept generation does. Both numbers are in it — a file that was
#: cut and a file that stopped there look identical, and they are not the same fact.
DROPPED = ("rotated: this file was {size} bytes and the first {kept} of them are above. the rest is "
           "not here, so that moving it aside costs the same whatever it had grown to")


def stamp(when: Optional[datetime.datetime] = None) -> str:
    """One moment written the way a person reads it: the machine's own clock, carrying its offset.

    **Local rather than UTC, because the question anybody asks is "what happened at nine last
    night, when I noticed?"** Every other account of the same machine — the clock in the menu bar,
    `ls -la`, Console, `log show` — answers in the machine's own time, and a stamp in UTC makes the
    one reader who exists do arithmetic on every line to spare a reader in another timezone who
    does not.

    **The offset is what makes local safe rather than merely convenient.** Across a daylight-saving
    fall-back the same wall-clock time happens twice, and only the offset tells the two apart:
    `01:30:00-07:00` against `01:30:00-08:00` is plainly an hour with nothing to work out.
    `astimezone()` with no argument attaches whichever offset is in force at *that* moment, so this
    is right on both sides of a transition without anything here knowing when transitions fall.

    **One function rather than the same literal wherever a moment is shown**, because these are read
    side by side: `status` says how long a gateway has been up and the next thing anybody does is
    open that gateway's log. Two spellings of one shape agree until somebody edits one of them, and
    a test asserting that two literals still match is a test standing in for a function.

    `when` is resolved in the body rather than bound in the signature — a default decided when this
    module was defined is one nothing can reach past. Given one without a timezone it is read as the
    machine's own clock; given one with, it is shown in the machine's own clock.
    """
    moment = (when if when is not None else datetime.datetime.now()).astimezone()
    return moment.isoformat(sep=" ", timespec="seconds")


class Tail(NamedTuple):
    """The end of a log, and which of the three answers this was.

    `how` first. While it is `READ` the lines are the answer, and an empty list means the days are
    there with nothing in them; `NOTHING_YET` means nothing has ever been written; `UNREADABLE`
    means the question could not be answered at all, and `why` says what stopped it.

    The third is not the first two with an empty list. A caller handed `[]` for a permission problem
    reports a quiet program, and whoever reads that goes looking in the wrong place entirely.
    """

    how: str
    lines: List[str]
    why: str


def note(into: Path, said: str, level: str = INFO,
         when: Optional[datetime.datetime] = None) -> None:
    """Append one line — `[<when>] <LEVEL>: <what happened>` — to today's file. **Never raises.**

    A program must not fail because it could not write down what it was doing, so every `OSError`
    here — a directory that cannot be made, a full disk, a permission changed underneath — is
    swallowed. The reader is where somebody finds out, which is why `tail` keeps "could not be read"
    as an answer of its own.

    **Only the log directory itself may be made.** Its parent is the thing the log belongs to — an
    agent, a channel, or another durable owner — and recreating that parent because it disappeared
    would leave a half-made owner behind. This is also the race-safe half of callers checking that
    owner before they write: if it goes after their check, this `mkdir` fails rather than recursively
    putting it back.

    Opened `O_APPEND` and written once, then closed: see the module docstring for why nothing is
    held open between lines and why one write is the whole guarantee.

    `level` is one of `LEVELS` and is made into one — see `_how_serious`, because a column with a
    fifth word in it is a column nobody can filter on.

    `when` is the moment the line belongs to, resolved in the body rather than bound in the
    signature — a default decided when this module was defined is one nothing can reach past, and a
    case proving that a gateway running through midnight lands in two files should not have to wait
    until midnight to do it. The shape it is written in is `stamp`'s, which is also the shape a
    gateway's record carries: the reasoning for local time with an offset is there, in one place,
    because these two are read side by side.
    """
    moment = (when if when is not None else datetime.datetime.now()).astimezone()
    line = SAID.format(when=stamp(moment),
                       level=f"{_how_serious(level)}:".ljust(WIDEST),
                       said=said.rstrip("\n"))
    try:
        into.mkdir(exist_ok=True)
        # Created at the mode it should have rather than tightened afterwards — a log holds what a
        # program was doing and for whom, and the lines are already in it by the second step.
        holding = os.open(into / named_for(moment), os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                          files.ONLY_MINE)
        try:
            os.write(holding, line.encode("utf-8"))
        finally:
            os.close(holding)
    except OSError:
        return


def _how_serious(level: str) -> str:
    """One of `LEVELS`, whatever the caller said.

    **A word this vocabulary does not have becomes `ERROR`** rather than being written through or
    filed as ordinary. Written through, the column stops being four words and nothing can be
    filtered on it. Filed as `INFO`, a line nobody could classify is shown to a person as a routine
    event — and the four names somebody is most likely to reach for from outside this list are
    PSR-3's, three of which are graver than `ERROR` and not one of which is routine.

    Case and stray spacing are not somebody's mistake to pay for: `"info"` is `INFO`.
    """
    said = level.strip().upper()
    return said if said in LEVELS else ERROR


def named_for(moment: datetime.datetime) -> str:
    """What the file holding that day's lines is called.

    The **local** day, because the times on the lines inside are local: a name and its contents
    disagreeing about which day they are is how somebody opens last Tuesday and finds Wednesday.
    """
    return f"{moment.astimezone().strftime(DAY)}{ENDS_WITH}"


def kept(into: Path) -> List[Path]:
    """Every day file in `into`, newest first.

    Anything not named for a day is not ours and is not offered: a directory a program writes into is
    a directory somebody else puts a file in, and a listing that included those would have a caller
    reading them as logs — and `swept` removing them.
    """
    return _listed(into)[1]


def tail(into: Path, lines: int) -> Tail:
    """The last `lines` of everything written in `into`, oldest day first.

    The days are one stream, walked backwards from today and stopped as soon as there are enough
    lines, so asking for twenty lines of a year of logging reads a few kilobytes rather than the
    directory. Neither the number of days nor the size of any of them changes what this costs.

    A file that will not open stops the whole answer rather than being passed over: the lines that
    could be read, handed back as the end of the log, are a tail with a hole in it that nothing
    anywhere says is there.

    **The lines come back exactly as they are in the file.** Nothing here parses a line apart or
    renders one again, so what a command prints is the same text a person greps — and a log that is
    shown in one shape and searched in another is a log where the line somebody found is not the
    line they were shown.
    """
    how, there, why = _listed(into)
    if how == UNREADABLE:
        return Tail(UNREADABLE, [], why)
    if not there:
        return Tail(NOTHING_YET, [], f"nothing has been written in {into} yet")
    if lines <= 0:
        return Tail(READ, [], "")

    gathered: List[str] = []
    for one in there:
        try:
            gathered = _the_end_of(one, lines - len(gathered)) + gathered
        except OSError as trouble:
            return Tail(UNREADABLE, [], f"{one} could not be read ({trouble})")
        if len(gathered) >= lines:
            break
    return Tail(READ, gathered[-lines:], "")


def swept(into: Path, keeping: int) -> List[Path]:
    """Remove the days older than `keeping` of them, and hand back what went.

    **The age comes from the name, never from the file's own timestamp.** An mtime is changed by a
    copy, a restore, or a backup putting a file back — so a restore would silently age out logs it
    had just brought back, and the day they covered would be gone with nothing said. The name is
    what the day was, and nothing that moves a file can change it.

    **Nothing it cannot read as a day is touched.** A directory a program writes into is a directory
    somebody else leaves a file in, and a sweep that removed what it did not recognise is a sweep
    that deletes somebody's notes.

    `keeping` under one day removes nothing at all. A retention that arrives as `0` is a
    configuration that lost its value somewhere, and reading it as "keep none of it" would empty a
    log directory on the strength of a variable nobody set.

    What comes back is what actually went — a file that could not be removed is not reported as
    removed, because the whole point of a list here is that somebody can trust it.
    """
    if keeping < 1:
        return []
    # Counted in the machine's own days, because that is what the names are. Asking UTC instead
    # would put the cutoff a day out for part of every day, and the file it took would be the
    # oldest one somebody still wanted.
    oldest = datetime.date.today() - datetime.timedelta(days=keeping - 1)
    gone = []
    for one in kept(into):
        # The refusal to touch what is not ours lives in `kept`, which is the one place that decides
        # what a day file is — it is not repeated here, because two places deciding that is how they
        # come to decide it differently. `None` is asked about only because the answer may be one.
        day = the_day_of(one.name)
        if day is None or day >= oldest:
            continue
        try:
            one.unlink()
        except OSError:
            continue
        gone.append(one)
    return gone


def rotated(one: Path, when_over: int, keeping: int) -> Optional[Path]:
    """Move a file's content aside once it is bigger than `when_over`. **Never raises.**

    Hands back where the content went, or `None` when nothing was moved — which is the ordinary
    answer, because most calls find a file that is not big enough yet.

    **The content moves and the file stays.** A descriptor refers to an inode and not to a name, so
    renaming a file that somebody has open leaves them writing into the same inode under its new name
    — `<name>.1` — while the file everybody looks in stays empty for as long as that process lives.
    Unlinking it is worse: the same writes go somewhere with no name at all. This is written for
    exactly that case, a file a supervisor opened and handed to a program it started, so the original
    is truncated in place: same inode, same name, same descriptor, and whoever holds it goes on
    writing into the file whose path is in their configuration.

    **`O_APPEND` is what makes truncating safe rather than merely possible.** Under it every write
    takes the offset and the write together at the current end of the file, so the next line after a
    truncation lands at zero. A descriptor opened without it keeps an offset of its own across the
    truncation, and the next write leaves a hole of NUL bytes as long as everything that was there —
    a file that looks corrupt and is bigger than what it holds. Supervisors that capture output open
    these `O_APPEND`; nothing here can check that, so it is stated as the condition it is.

    **`when_over` is one decision wearing two hats**, and that is why there is one number rather than
    two: it is how big a kept generation is, and therefore the size at which a file has more in it
    than one generation holds. Everything this keeps is exactly that size, so what the whole scheme
    costs on disk is `when_over` times `keeping` and can be worked out without measuring anything.

    **The head is what is kept, and the tail is what goes.** A rotation that copied the whole file
    would make coming up cost whatever that file had grown to — for a program that has been spilling
    into its own output since March, gigabytes before the first useful thing happens. The first
    `when_over` bytes are the *start* of whatever went wrong, which is the part somebody is looking
    for; the end of it is still arriving in the live file. The last line of the copy says how big the
    file was and how much of it is above, because a file that was cut and a file that stopped there
    look identical and are not the same fact.

    **`keeping` under one moves nothing at all**, in the same spirit as `swept`: a retention that
    arrived as `0` is a value that lost itself somewhere, and reading it as "keep none of it" would
    have this truncate a file and throw the only copy away on the strength of it.

    A rotation is several steps and nothing makes them one. Interrupted between them it leaves either
    a copy that is about to be made again or a staged one nothing renamed — never a truncated
    original with no copy, because the truncation is last. Two processes rotating the same file at the
    same instant can roll one generation twice; both copies hold the same bytes, so what that costs is
    one older generation and never the content itself.
    """
    if keeping < 1:
        return None
    try:
        size = one.stat().st_size
    except OSError:
        return None
    if size <= when_over:
        return None

    aside = _numbered(one, 1)
    try:
        for which in range(keeping, 1, -1):
            # Rolled from the oldest down, so each generation lands on the one it replaces and the
            # one beyond `keeping` is written over rather than needing to be found and removed. These
            # are ours and nobody holds them open, so they move by name.
            with contextlib.suppress(OSError):
                os.replace(_numbered(one, which - 1), _numbered(one, which))
        staged = files.incoming_of(aside)
        _copied(one, staged, when_over, size)
        os.replace(staged, aside)
        # Last, and only once there is a copy under its finished name. See `files` on why a
        # half-written thing never wears one.
        os.truncate(one, 0)
    except OSError:
        return None
    return aside


def _numbered(one: Path, which: int) -> Path:
    """What the `which`th generation of a rotated file is called, beside it."""
    return one.with_name(ROTATED.format(name=one.name, which=which))


def _copied(one: Path, into: Path, most: int, size: int) -> None:
    """The first `most` bytes of `one` into `into`, saying at the end when there was more.

    Opened at `ONLY_MINE` before a byte is written rather than tightened afterwards: what a program
    wrote to its own output is not necessarily fit for everybody to read, and the window between
    creating a file at the umask and narrowing it is a window the content is already in.
    """
    ended = True
    holding = os.open(into, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, files.ONLY_MINE)
    with open(holding, "wb") as writing:
        with open(one, "rb") as reading:
            left = most
            while left > 0:
                block = reading.read(min(BLOCK_BYTES, left))
                if not block:
                    break
                writing.write(block)
                ended = block.endswith(b"\n")
                left -= len(block)
        if size > most:
            said = SAID.format(when=stamp(), level=f"{WARNING}:".ljust(WIDEST),
                               said=DROPPED.format(size=size, kept=most))
            writing.write(("" if ended else "\n").encode("utf-8") + said.encode("utf-8"))


def the_day_of(name: str) -> Optional[datetime.date]:
    """The day a file is named for, or `None` when it is not one of ours.

    The shape is checked and then the date is parsed, because they refuse different things:
    `notes.log` is not shaped like a day, and `2026-02-31.log` is shaped exactly like one and is not
    a date. Either way it is somebody else's file.
    """
    if not NAMED_FOR_A_DAY.match(name):
        return None
    try:
        return datetime.datetime.strptime(name[:-len(ENDS_WITH)], DAY).date()
    except ValueError:
        return None


def _listed(into: Path) -> Tuple[str, List[Path], str]:
    """The day files newest first, and which of the three answers the directory itself was.

    A directory nobody has written in yet and one nobody may read are different facts, and the whole
    of `tail`'s third answer rests on telling them apart here.
    """
    try:
        there = list(into.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return NOTHING_YET, [], f"nothing has been written in {into} yet"
    except OSError as trouble:
        return UNREADABLE, [], f"{into} could not be read ({trouble})"
    days = sorted((one for one in there if the_day_of(one.name) is not None),
                  key=lambda one: one.name, reverse=True)
    return READ, days, ""


def _the_end_of(one: Path, wanted: int) -> List[str]:
    """The last `wanted` lines of one file, without reading the rest of it.

    Seeks to the end and walks backwards a block at a time until there are enough line endings to be
    sure the topmost line in hand is a whole one. The answer costs the same whether the file is a
    kilobyte or a gigabyte.

    Decoded with `replace`, because a block boundary lands in the middle of a character sooner or
    later and the end of a log is not worth an exception. Lines are counted after decoding, so a
    partial first line is dropped by the slice rather than offered as a line somebody wrote.
    """
    if wanted <= 0:
        return []
    with open(one, "rb") as reading:
        reading.seek(0, os.SEEK_END)
        standing_at = reading.tell()
        held = b""
        while standing_at > 0 and held.count(b"\n") <= wanted:
            step = min(BLOCK_BYTES, standing_at)
            standing_at -= step
            reading.seek(standing_at)
            held = reading.read(step) + held
    return held.decode("utf-8", "replace").splitlines()[-wanted:]
