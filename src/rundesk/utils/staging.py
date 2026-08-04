"""Building something beside what it replaces, and renaming it into place.

The convention everything in this product follows when it replaces something on disk: build the new
thing under a name that is **not** the name of the finished article, and rename it over the old one
only once all of it is there.

The guarantee is one sentence — *a reader never sees a half-written thing under a name that says it
is finished* — and it is worth more than it looks. Half a JSON document is not a smaller record, it
is an unreadable one. A program directory holding half a release is not an older version, it is
neither. A backup interrupted halfway and nevertheless called `2026-08-04T03-00-00Z` is worse than no
backup at all, because it is the one somebody reaches for.

The names live here rather than in each caller because a swap and the walk that has to skip it must
agree, and two modules that spell the same convention separately are two modules that will
eventually spell it differently. `os.replace`/`os.rename` within one filesystem is what makes the
final step atomic; staging beside the target rather than in a temporary directory is what keeps it
within one filesystem.

The leading dot keeps staging out of an ordinary listing. Knows nothing about rundesk.
"""

import shutil
from pathlib import Path
from typing import Callable, Optional

#: What a thing being built is called until all of it is there.
INCOMING = ".{name}.incoming"

#: What the thing being replaced is called while the swap is in flight, so it can be put back.
OUTGOING = ".{name}.outgoing"


def staged(name: str) -> bool:
    """Whether this is a name a swap is using rather than a finished thing.

    Asked by every walk over a directory something stages into, so a listing never offers half a
    copy and a move never carries one somewhere else.
    """
    return name.startswith(".") and name.endswith((".incoming", ".outgoing"))


def discard(where: Path) -> None:
    """Remove a staging entry, whatever kind it is.

    **Only ever used on a name the caller chose**, never on something an owner keeps — which is why
    it may be this forgiving about failing. A staging entry left behind is tidied by the next swap;
    raising here would turn a successful operation into a reported failure over litter.
    """
    if where.is_dir() and not where.is_symlink():
        shutil.rmtree(where, ignore_errors=True)
    elif where.exists() or where.is_symlink():
        try:
            where.unlink()
        except OSError:
            pass


def stage_copy(entry: Path, into: Path, ignore: Optional[Callable] = None) -> Path:
    """Copy `entry` into `into` under its staged name, and hand back where it landed.

    The caller decides when — or whether — to rename the result into place, because that is the part
    that genuinely differs: one caller stages every entry and swaps them together, another renames
    each as it lands. What is identical is this, and it has one subtlety worth having in one place.

    **A symlink is copied as a symlink, never followed.** `is_dir()` answers `True` for a link
    pointing at a directory, so a copy that asked only that question would walk through the link and
    duplicate the tree on the other side of it — silently, and only for the owner who had one.
    """
    pending = into / INCOMING.format(name=entry.name)
    discard(pending)
    if entry.is_dir() and not entry.is_symlink():
        shutil.copytree(entry, pending, symlinks=True, ignore=ignore)
    else:
        shutil.copy2(entry, pending, follow_symlinks=False)
    return pending
