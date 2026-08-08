"""Catalogs and skills built on disk, for the suites that work on them.

Not named `test_…`, so `scripts/suites` does not try to run it as one.

**Everything here writes its own JSON and its own frontmatter rather than going through the product's
readers and writers.** A fixture built by the code under test is a fixture that agrees with a bug in
it: a validator that accepted the wrong thing would be handed exactly the wrong thing to accept, and
every case would pass. These builders are deliberately dumb.
"""

import json
import shutil
import tarfile
from pathlib import Path
from typing import Dict, Iterable, Optional

# Imported for what it does on the way in rather than for anything it exports: `support` is what
# puts `src/` on the path. Stated here rather than left to the importing suite, because whether this
# module works would otherwise depend on which of the two a linter decided to sort first.
import support  # noqa: F401  (isort: this must precede `rundesk`)
from rundesk.skills import library

A_SKILL = """---
name: {name}
description: {description}
---

# {name}

Do the thing.
"""


def written(where: Path, value: dict) -> None:
    """A JSON fixture, written by hand."""
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(value), encoding="utf-8")


def a_skill(at: Path, name: str = "", description: str = "Plan work. Use when planning.",
            needs: Optional[Dict[str, str]] = None,
            scripts: Iterable[str] = ()) -> Path:
    """A valid skill standing at `at`, with what it declares and the commands it ships."""
    at.mkdir(parents=True, exist_ok=True)
    (at / library.DECLARED).write_text(
        A_SKILL.format(name=name or at.name, description=description), encoding="utf-8")
    if needs is not None:
        written(at / "rundesk.json", {"needs": needs})
    for one in scripts:
        runnable = at / library.SCRIPTS / one
        runnable.parent.mkdir(parents=True, exist_ok=True)
        runnable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        runnable.chmod(0o755)
    return at


def a_catalog(at: Path, name: str = "acme", version: str = "1.0.0",
              skills: Iterable[str] = ("writing-plans",)) -> Path:
    """A catalog tree standing at `at` — a manifest, and the skills named."""
    tree = at / library.TREE
    (tree / library.INSIDE).mkdir(parents=True, exist_ok=True)
    written(tree / library.MANIFEST, {
        "schema": library.SCHEMA, "name": name, "version": version,
        "description": f"Skills for {name}."})
    for one in skills:
        a_skill(tree / library.INSIDE / one)
    return at


def a_published_catalog(at: Path, name: str = "acme", version: str = "1.0.0",
                        skills: Iterable[str] = ("writing-plans",)) -> Path:
    """A catalog as a repository holds it — the manifest at the top, not inside an `app/`.

    **Builds exactly what was asked for**, clearing any skills a previous call left. A builder that
    added to what was there made "publish a version with one skill removed" impossible to express,
    which is the case every retirement test needs.
    """
    shutil.rmtree(at / library.INSIDE, ignore_errors=True)
    (at / library.INSIDE).mkdir(parents=True, exist_ok=True)
    written(at / library.MANIFEST, {
        "schema": library.SCHEMA, "name": name, "version": version,
        "description": f"Skills for {name}."})
    for one in skills:
        a_skill(at / library.INSIDE / one)
    return at


def a_tarball(tree: Path, to: Path, wrapper: str = "") -> Path:
    """`tree` as a gzipped tar, optionally under one wrapper directory the way GitHub sends it."""
    with tarfile.open(to, "w:gz") as writing:
        for one in sorted(tree.rglob("*")):
            inside = one.relative_to(tree)
            writing.add(one, arcname=str(Path(wrapper) / inside) if wrapper else str(inside))
    return to
