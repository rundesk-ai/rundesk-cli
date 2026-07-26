"""rundesk — a lightweight, provider-agnostic multi-agent gateway.

The version here is the one source of it: the CLI reports it, the updater compares
against it, and a release tag is expected to match. So is `ROOT`: where this install
actually is, worked out once from a file that is always inside it.
"""

from pathlib import Path

__version__ = "0.5.2"

#: This install — the directory holding `rundesk`, `src/` and the virtualenv. Resolved
#: rather than assumed, because the command is reached through a symlink on a PATH and
#: the checkout it points into is what an update replaces.
ROOT = Path(__file__).resolve().parent.parent.parent
