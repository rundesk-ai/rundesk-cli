"""rundesk — a lightweight, provider-agnostic multi-agent gateway, in standard library Python.

This package holds one thing: **what version this copy is**. Nothing else lives here, because
everything else has somewhere better to be — where an install keeps its files is `core/paths.py`, what a
command may exit with is `exits.py`, and what the command offers is `cli.py`.

`__version__` is the single source of that answer. The command reports it, an update compares against
it, and a release tag is expected to match it. Nothing anywhere holds a copy: the build this replaces
reported the version through three separate paths and pointed at its own install root through two
different constants, which is two chances for a product to disagree with itself about what it is.
"""

__version__ = "0.37.0"
