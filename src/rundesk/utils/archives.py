"""Unpacking an archive somebody else made, without letting it write outside where you put it.

An archive is a list of names and a list of bytes, both of them written by whoever built it. Nothing
in the format stops a member being called `../../../etc/something`, and an unpacker that trusts the
names writes exactly where it is told to. The standard library only began refusing that in a version
far newer than the floor this product supports, so it is checked here rather than relied upon.

**Two kinds of link, and they do not resolve their targets the same way.** Checking them as though
they did is a check that passes while the escape happens:

- A **symbolic** link's target is resolved by the filesystem, against the directory the link itself
  stands in.
- A **hard** link's target is resolved by `tarfile`, against the extraction root — literally
  `os.path.join(path, tarinfo.linkname)`, unchanged in every version from the floor upwards.

So a hard link one directory deep naming `../something` was measured against the wrong place, came
out looking contained, and was then created pointing at a real file outside the unpacking. From that
moment its contents are indistinguishable from an ordinary member, and whatever reads the unpacked
tree copies the file into wherever it is putting things.

Checked before anything is written rather than as each member lands. A refusal met halfway through
leaves a partly-unpacked tree that somebody then has to decide what to do with, and the answer is
always "throw it away" — so this decides first and unpacks second.
"""

import tarfile
from pathlib import Path


class Refused(ValueError):
    """An archive that would write somewhere it was not given, named with which member.

    A `ValueError` because that is what an unusable input is, and named so a caller that means to
    tell somebody which file was wrong can.
    """


def unpacked(archive: Path, into: Path) -> Path:
    """Unpack `archive` into `into`, or refuse naming the member that would have escaped.

    `into` is made if it is not there. Everything lands below it, and nothing anywhere else — that
    is the whole guarantee, and it is the only one: what is *in* the archive is still somebody
    else's, and deciding whether it is the thing you asked for is the caller's job.
    """
    into.mkdir(parents=True, exist_ok=True)
    settled = into.resolve()
    with tarfile.open(archive, "r:*") as held:
        for member in held.getmembers():
            lands = (into / member.name).resolve()
            if lands != settled and settled not in lands.parents:
                raise Refused(f"{member.name} would be written outside {into}")
            if not (member.issym() or member.islnk()):
                continue
            # See the module docstring: the two kinds are resolved against different directories,
            # and measuring a hard link against the link's own parent is the check that looks
            # right and lets the escape through.
            against = into if member.islnk() else lands.parent
            points = (against / member.linkname).resolve()
            if points != settled and settled not in points.parents:
                raise Refused(f"{member.name} points outside {into}")
        held.extractall(into)
    return into
