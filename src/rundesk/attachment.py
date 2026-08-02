"""What an answer declares for delivery, and whether it may be sent.

Two things, and nothing about conversations. A brain writes an absolute local Markdown link
to say "send this file" (R-CH-31); this reads those out of what it wrote, and decides
separately whether one may actually leave the machine — that it stands where this agent
works, that no component of the path is a link out of there, and that it is small enough.

Kept apart from `answering.py` because none of it is about who may be answered or what
state a turn is in, which is that module's whole subject. What is here is a security
boundary — containment, symlink refusal and a size ceiling — and it is worth being able to
read that on its own. Nothing here touches a conversation, an agent or a turn, and no
function holds any state.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from pathlib import Path

from rundesk import channel

# Any absolute local Markdown link is delivery intent (R-CH-31). The optional reserved
# prefix remains portable across brains; prefix that form or the opening bracket with a
# backslash when showing one literally. The parser below handles balanced brackets and
# parentheses because both are valid filename characters and regex cannot balance them.
_LOCAL_ATTACHMENT_START = re.compile(r"(?<!\\)(?:rundesk-attach:[ \t]+)?\[")


def approved(declared, roots) -> tuple[dict | None, str | None]:
    """Resolve, contain, and fingerprint one declaration without trusting its path."""
    if not isinstance(declared, dict):
        return None, None
    at = declared.get("at")
    if not isinstance(at, str) or not at or not Path(at).is_absolute():
        return None, None
    try:
        where = Path(at).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None, None
    inside = None
    for candidate in roots:
        try:
            root = candidate.resolve(strict=True)
            where.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        inside = root
        break
    if inside is None:
        return None, f"not sending {where}, which is outside where this agent works"
    try:
        fingerprint = _fingerprint_beneath(where, inside)
    except OSError as why:
        return None, f"not sending {where.name}: {why}"
    if fingerprint is None:
        return None, f"not sending {where.name}, which is too large to attach"
    size, digest, file_identity = fingerprint
    return {
        "name": str(declared.get("name") or where.name),
        "at": str(where),
        "bytes": size,
        "sha256": digest,
        "_file_identity": file_identity,
    }, None


def _fingerprint_beneath(at: Path, inside: Path) -> tuple[int, str, tuple[int, int]] | None:
    """Read through held directory descriptors, refusing links in every component."""
    at.relative_to(inside)
    parts = at.parts[1:]
    if not parts:
        raise OSError("not a regular file")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    descriptor = None
    digest = hashlib.sha256()
    size = 0
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
            dir_fd=directory,
        )
        status = os.fstat(descriptor)
        if not stat.S_ISREG(status.st_mode):
            raise OSError("not a regular file")
        with os.fdopen(descriptor, "rb") as source:
            descriptor = None
            while block := source.read(min(1024 * 1024,
                                            channel.ATTACHED_BYTES + 1 - size)):
                size += len(block)
                if size > channel.ATTACHED_BYTES:
                    return None
                digest.update(block)
        return size, digest.hexdigest(), (status.st_dev, status.st_ino)
    finally:
        os.close(directory)
        if descriptor is not None:
            os.close(descriptor)


def declared_in(text: str) -> tuple[str, list]:
    """Extract absolute local Markdown links and leave only their labels."""
    declared = []
    visible = []
    copied = 0
    searched = 0
    while found := _LOCAL_ATTACHMENT_START.search(text, searched):
        start = found.start()
        # `\rundesk-attach:` is the documented literal form. Without this check the
        # optional prefix would let the search begin again at its otherwise ordinary `[`.
        line_start = text.rfind("\n", 0, start) + 1
        before = text[line_start:start]
        if found.group(0) == "[" and re.search(
                r"\\rundesk-attach:[ \t]+$", before):
            searched = found.end()
            continue

        label_start = found.end()
        label_end = _matching_close(text, label_start, "[", "]")
        if label_end is None or label_end + 1 >= len(text) or text[label_end + 1] != "(":
            searched = found.end()
            continue

        destination_start = label_end + 2
        if destination_start >= len(text):
            break
        if text[destination_start] == "<":
            destination_end = _next_unescaped(text, destination_start + 1, ">")
            if (destination_end is None or destination_end + 1 >= len(text)
                    or text[destination_end + 1] != ")"):
                searched = found.end()
                continue
            at = text[destination_start + 1:destination_end]
            end = destination_end + 2
        else:
            destination_end = _matching_close(text, destination_start, "(", ")")
            if destination_end is None:
                searched = found.end()
                continue
            at = text[destination_start:destination_end]
            end = destination_end + 1

        if not at.startswith("/") or at.startswith("//") or "\n" in at or "\r" in at:
            searched = found.end()
            continue
        if found.group(0).startswith("rundesk-attach:"):
            # Preserve the reserved whole-line form's historical CRLF normalization and
            # trailing-space handling without consuming prose after an ordinary link.
            line_end = end
            while line_end < len(text) and text[line_end] in " \t":
                line_end += 1
            if line_end < len(text) and text[line_end] == "\r":
                line_end += 1
            if line_end == len(text) or text[line_end] == "\n":
                end = line_end
        visible.extend((text[copied:start], text[label_start:label_end]))
        declared.append({"name": Path(at).name, "at": at})
        copied = end
        searched = end
    visible.append(text[copied:])
    return "".join(visible), declared


def _matching_close(text: str, start: int, opened: str, closed: str) -> int | None:
    """Find a balanced Markdown delimiter, ignoring escaped characters."""
    depth = 1
    index = start
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == opened:
            depth += 1
        elif text[index] == closed:
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _next_unescaped(text: str, start: int, wanted: str) -> int | None:
    """Find one Markdown delimiter, ignoring escaped characters."""
    index = start
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == wanted:
            return index
        index += 1
    return None
