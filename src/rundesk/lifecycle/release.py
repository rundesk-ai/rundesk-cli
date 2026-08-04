"""What has been published, and how this install stands against it.

Every call that leaves the machine arrives here as an **argument**, resolved when it is called rather
than bound when the module is defined. That is what makes the whole of this testable with no network:
a default bound in a signature is decided once, at import, and a test can never reach past it.

The one thing this module refuses to do is collapse its three answers. "You are current", "you are
behind" and "nobody could be asked" are different, and the third is not a quiet form of the first —
an install that reports UP TO DATE because GitHub timed out is an install that has silently stopped
updating itself, and nobody finds out until something else breaks.
"""

import json
import re
import urllib.error
import urllib.request
from typing import Callable, Optional, Tuple

#: The repository this install updates from. Deliberately not overridable: an install pointed at one
#: repository but updating from another drifts, and nothing about it looks wrong.
REPO = "rundesk-ai/rundesk-cli"

#: What a release is fetched from — the counted asset, so a published release records each delivery.
ARCHIVE_URL = "https://github.com/{repo}/releases/download/{tag}/rundesk-cli.tar.gz"

#: Where the newest tag is read from. The website's redirect rather than the API, because the
#: anonymous API allows sixty questions an hour and a person updating should never meet that.
LATEST_URL = "https://github.com/{repo}/releases/latest"
LATEST_API = "https://api.github.com/repos/{repo}/releases/latest"

#: What a release page is called, for saying where a version came from.
RELEASE_URL = "https://github.com/{repo}/releases/tag/v{version}"

USER_AGENT = "rundesk-cli"
ASK_SECONDS = 5

#: Nobody could be asked: the network failed, timed out, or answered something unexpected.
UNREACHABLE = "unreachable"

#: There is nothing published at all — told apart from being unable to ask, because the two mean
#: opposite things about whether an update exists.
NOTHING_PUBLISHED = "nothing-published"

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")

#: How the newest published tag is looked up: `(tag, None)`, or `(None, why)` where `why` tells
#: nothing-published from unreachable.
#:
#: Named because it is the shape every caller of `standing` has to honour, and because it is the one
#: thing in this product that leaves the machine — every command that could reach GitHub takes one of
#: these instead, so the network is a value that can be replaced rather than an import that cannot.
Asking = Callable[[], Tuple[Optional[str], Optional[str]]]


def parsed(value: Optional[str]) -> Optional[Tuple[int, int, int]]:
    """A version as three numbers, or `None` when it is not shaped like one."""
    if not value:
        return None
    said = _VERSION.match(value.strip())
    return (int(said.group(1)), int(said.group(2)), int(said.group(3))) if said else None


def newer(published: Optional[str], installed: str) -> bool:
    """Whether `published` is a later version than `installed`.

    **False when either cannot be read.** A version this code does not understand is never treated as
    newer: the alternative is an install that replaces itself from something it could not parse.
    """
    there, here = parsed(published), parsed(installed)
    return bool(there and here and there > here)


def tag_names(tag: str, version: str) -> bool:
    """Whether a release tag names the version the command reports."""
    return parsed(tag) is not None and parsed(tag) == parsed(version)


def archive_url(tag: str) -> str:
    """Where the archive for a tag is fetched from."""
    return ARCHIVE_URL.format(repo=REPO, tag=tag)


def release_url(version: Optional[str]) -> Optional[str]:
    """Where a version's release notes are, or `None` when it is not shaped like a version."""
    return RELEASE_URL.format(repo=REPO, version=version) if parsed(version) else None


def latest_published() -> Tuple[Optional[str], Optional[str]]:
    """Ask GitHub for the newest published tag.

    Returns `(tag, None)`, or `(None, why)` where `why` tells nothing-published from unreachable.
    The only function here that touches the network, so it is the only one a test replaces.
    """
    try:
        asked = urllib.request.Request(
            LATEST_URL.format(repo=REPO),
            headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(asked, timeout=ASK_SECONDS) as answered:
            landed = answered.geturl()
        tag = landed.rstrip("/").rsplit("/", 1)[-1]
        if parsed(tag):
            return tag, None
    except urllib.error.HTTPError as why:
        if why.code == 404:
            return None, NOTHING_PUBLISHED
    except (urllib.error.URLError, OSError, ValueError):
        pass
    return _asked_of_the_api()


def _asked_of_the_api() -> Tuple[Optional[str], Optional[str]]:
    """The second way of asking, for when the redirect did not answer with a tag."""
    try:
        asked = urllib.request.Request(
            LATEST_API.format(repo=REPO),
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(asked, timeout=ASK_SECONDS) as answered:
            said = json.loads(answered.read().decode("utf-8"))
        tag = said.get("tag_name") if isinstance(said, dict) else None
        return (tag, None) if parsed(tag) else (None, UNREACHABLE)
    except urllib.error.HTTPError as why:
        return (None, NOTHING_PUBLISHED) if why.code == 404 else (None, UNREACHABLE)
    except (urllib.error.URLError, OSError, ValueError):
        return None, UNREACHABLE
    # `said` is whatever the other end sent. Valid JSON that is a list, or `null`, would have made
    # `.get` raise out of this function and out of the command as a traceback — an answer nobody
    # could act on, from the one function in the product whose whole job is to come back with one of
    # three states rather than fall over. Asked rather than caught, so the answer stays UNREACHABLE.


def described(installed: str, published: Optional[str], why: Optional[str] = None) -> str:
    """One line saying where this install stands, state first so it reads at a glance."""
    if published is None and why == NOTHING_PUBLISHED:
        return f"{installed}: NO RELEASES — nothing is published, or this install cannot see them"
    if published is None:
        return f"{installed}: UNKNOWN — could not reach GitHub to ask"
    if newer(published, installed):
        return f"{installed}: OUT OF DATE — {published} is available, run: rundesk update"
    return f"{installed}: UP TO DATE"


def standing(installed: str,
             asking: Optional[Asking] = None) -> Tuple[str, Optional[str], bool]:
    """Where this install stands: `(line, published tag or None, could_ask)`.

    `asking` is resolved here rather than in the signature, so a test replaces it and the network is
    never reached. `could_ask` is the third answer kept separate — a caller decides what to do about
    not knowing, and none of them may treat it as being current.
    """
    ask = asking or latest_published
    published, why = ask()
    return described(installed, published, why), published, published is not None
