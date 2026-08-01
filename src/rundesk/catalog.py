"""Versioned repositories of complete skills installed into Rundesk's library.

A catalog is files, never code Rundesk imports or executes. Its manifest names one or
more complete Agent Skills packages. Rundesk keeps one catalog release below the data
directory and exposes each declared skill through the existing library, where grants work
exactly as they do for built-ins and owner-authored skills.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from rundesk import data_home
from rundesk import skill, updater

MANIFEST = "manifest.json"
SCHEMA = 1
OWNED = ".rundesk-catalog"
APP = "app"
COMING = ".app.coming"
PREVIOUS = ".app.previous"
PROVENANCE = "provenance.json"
GITHUB = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
ARCHIVE_URL = "https://api.github.com/repos/{slug}/tarball"
DEFAULT_NAME = "rundesk-skills"
DEFAULT_SOURCE = "https://github.com/rundesk-ai/rundesk-skills"
DEFAULT_SOURCE_ENV = "RUNDESK_DEFAULT_SKILLS_SOURCE"


class NotACatalog(Exception):
    """A source that does not declare a catalog Rundesk can install."""


class InTheWay(Exception):
    """Owner content or another catalog already occupies a required name."""


class Unknown(Exception):
    """A catalog that is not installed."""


class InUse(Exception):
    """A catalog whose skills are still granted to at least one agent."""


class RollbackFailed(Exception):
    """An update failed and Rundesk could not restore the prior catalog release."""


@dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    description: str
    skills: tuple[tuple[str, str], ...]
    at: Path


@dataclass(frozen=True)
class Installed:
    name: str
    version: str
    source: str
    at: Path
    manifest: Manifest


@dataclass(frozen=True)
class Refreshed:
    """What one repository check found, including a failure that did not stop the rest."""

    name: str
    before: str | None
    after: str | None
    why: str | None = None


def home(where: Path | None = None) -> Path:
    """Where managed catalogs stand, below the install's redirected data root."""
    return where if where is not None else data_home() / "catalogs"


def read(at: Path, validate_packages: bool = True) -> Manifest:
    """Read one catalog contract, validating its packages unless recovering an update."""
    page = at / MANIFEST
    try:
        said = json.loads(page.read_text(encoding="utf-8"))
    except FileNotFoundError as why:
        raise NotACatalog(f"there is no {MANIFEST} in {at}") from why
    except (OSError, UnicodeError, json.JSONDecodeError) as why:
        raise NotACatalog(f"{page} could not be read: {why}") from why
    if not isinstance(said, dict):
        raise NotACatalog(f"{page} must hold an object")
    if said.get("schema") != SCHEMA:
        raise NotACatalog(
            f"{page} uses schema {said.get('schema')!r}; this Rundesk reads {SCHEMA}"
        )
    name = _name(said.get("name"), "catalog")
    version = said.get("version")
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        raise NotACatalog(f"{name} has no semantic version such as 1.2.3")
    description = said.get("description")
    if not isinstance(description, str) or not description.strip():
        raise NotACatalog(f"{name} has no description")
    declared = said.get("skills")
    if not isinstance(declared, list) or not declared:
        raise NotACatalog(f"{name} declares no skills")
    found = []
    names = set()
    for entry in declared:
        if not isinstance(entry, dict):
            raise NotACatalog(f"{name} has a skill entry that is not an object")
        called = _name(entry.get("name"), "skill")
        relative = entry.get("path")
        skill_at = _inside(at, relative, name)
        if skill_at.name != called:
            raise NotACatalog(
                f"{name} calls {relative!r} {called}, but the directory is {skill_at.name}"
            )
        if validate_packages:
            why = skill.valid(skill_at)
            if why:
                raise NotACatalog(f"{name}'s {called} is not a usable skill: {why}")
        if called in names:
            raise NotACatalog(f"{name} declares {called} more than once")
        names.add(called)
        found.append((called, str(Path(relative))))
    return Manifest(name, version, description.strip(), tuple(found), at)


def _name(value, what: str) -> str:
    if not isinstance(value, str) or len(value) > skill.NAMED_LIMIT or not skill.ALLOWED.match(value):
        raise NotACatalog(
            f"the {what} name {value!r} is not lowercase letters, digits and single hyphens"
        )
    return value


def _inside(root: Path, relative, name: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise NotACatalog(f"{name} declares a skill with no path")
    given = Path(relative)
    if given.is_absolute():
        raise NotACatalog(f"{name} declares a path outside the catalog: {relative}")
    try:
        landing = (root / given).resolve()
        landing.relative_to(root.resolve())
    except (OSError, ValueError) as why:
        raise NotACatalog(f"{name} declares a path outside the catalog: {relative}") from why
    return landing


def installed(where: Path | None = None) -> dict[str, Installed]:
    """Every usable catalog Rundesk laid down, by declared name."""
    return _installed(where, validate_packages=True)


def _installed(where: Path | None = None,
               validate_packages: bool = True) -> dict[str, Installed]:
    """Managed catalogs, optionally tolerating package drift so an update can repair it."""
    root = home(where)
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return {}
    found = {}
    for entry in entries:
        if not entry.is_dir() or not (entry / OWNED).is_file() or not (entry / APP).is_dir():
            continue
        manifest = read(entry / APP, validate_packages=validate_packages)
        recorded = provenance(entry)
        source = recorded["source"]
        if recorded.get("version") != manifest.version:
            raise NotACatalog(
                f"{entry / PROVENANCE} records version {recorded.get('version')!r}, "
                f"but the installed catalog declares {manifest.version}"
            )
        found[manifest.name] = Installed(
            manifest.name, manifest.version, source, entry, manifest
        )
    return found


def provenance(at: Path) -> dict:
    page = at / PROVENANCE
    try:
        said = json.loads(page.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as why:
        raise NotACatalog(f"{page} could not be read: {why}") from why
    if not isinstance(said, dict) or not isinstance(said.get("source"), str):
        raise NotACatalog(f"{page} does not name where this catalog came from")
    return said


def inspect(source, fetch=None) -> Manifest:
    """Read what a source declares without writing any installed state."""
    with tempfile.TemporaryDirectory(prefix="rundesk-catalog-") as temporary:
        fetched = (fetch or _fetch)(source, Path(temporary))
        return read(fetched)


def install(source, where: Path | None = None, skills_dir: Path | None = None,
            fetch=None, seeded: bool = False) -> Installed:
    """Install every declared skill from one repository, or write nothing."""
    root = home(where)
    library = skills_dir if skills_dir is not None else skill.home()
    with tempfile.TemporaryDirectory(prefix="rundesk-catalog-") as temporary:
        fetched = (fetch or _fetch)(source, Path(temporary))
        manifest = read(fetched)
        with skill.changing_grants(library):
            if manifest.name in _installed(root, validate_packages=False):
                raise InTheWay(
                    f"{manifest.name} is already installed; "
                    f"use: rundesk skills update {manifest.name}"
                )
            target = root / manifest.name
            if target.exists():
                raise InTheWay(f"{target} is already there and Rundesk did not lay it down")
            _preflight(manifest, target, library)
            retired = _retired(manifest, target, library)
            try:
                target.mkdir(parents=True)
                (target / OWNED).write_text("rundesk skill catalog\n", encoding="utf-8")
                _stash(retired, target / PREVIOUS)
                shutil.copytree(fetched, target / APP)
                _write_provenance(target, str(source), manifest.version, seeded=seeded)
                _link_all(read(target / APP), target, library)
            except Exception:
                _unlink_owned(target, library)
                _restore_stash(target / PREVIOUS, library)
                shutil.rmtree(target, ignore_errors=True)
                raise
            shutil.rmtree(target / PREVIOUS, ignore_errors=True)
    return installed(root)[manifest.name]


def refresh(where: Path | None = None, skills_dir: Path | None = None,
            granted=(), fetch=None, default_source=None,
            retiring=None) -> tuple[Refreshed, ...]:
    """Seed Rundesk's general catalog, then check every repository already installed.

    Repositories are independent update units. One unreachable or invalid source is
    reported without keeping the remaining installed repositories from being checked.
    """
    root = home(where)
    library = skills_dir if skills_dir is not None else skill.home()
    source = default_source or os.environ.get(DEFAULT_SOURCE_ENV) or DEFAULT_SOURCE
    results = []
    standing = _installed(root, validate_packages=False)
    if DEFAULT_NAME not in standing:
        try:
            landed = install(source, root, library, fetch=fetch, seeded=True)
        except (NotACatalog, InTheWay, OSError) as why:
            results.append(Refreshed(DEFAULT_NAME, None, None, str(why)))
        else:
            results.append(Refreshed(landed.name, None, landed.version))
    for name, before in sorted(standing.items()):
        try:
            after = update(
                name, root, library, granted=granted, fetch=fetch, retiring=retiring,
            )
        except (NotACatalog, InTheWay, InUse, Unknown, RollbackFailed, OSError) as why:
            results.append(Refreshed(name, before.version, None, str(why)))
        else:
            results.append(Refreshed(name, before.version, after.version))
    return tuple(results)


def update(name: str, where: Path | None = None, skills_dir: Path | None = None,
           granted=(), fetch=None, retiring=None) -> Installed:
    """Move one catalog to a newer declared version, putting the working release back on failure."""
    root = home(where)
    library = skills_dir if skills_dir is not None else skill.home()
    with skill.changing_grants(library):
        current = _installed(root, validate_packages=False).get(name)
        if current is None:
            raise Unknown(f"there is no installed catalog called {name}")
        source = current.source
        seeded = provenance(current.at).get("seeded")
        with tempfile.TemporaryDirectory(prefix="rundesk-catalog-") as temporary:
            fetched = (fetch or _fetch)(source, Path(temporary))
            coming_manifest = read(fetched)
            return _update_to(
                current, coming_manifest, fetched, root, library, granted, retiring, seeded,
            )


def _update_to(current: Installed, coming_manifest: Manifest, fetched: Path,
               root: Path, library: Path, granted, retiring, seeded) -> Installed:
    """Activate one fetched release while the install-wide skill lock is held."""
    name = current.name
    source = current.source
    if coming_manifest.name != name:
        raise NotACatalog(f"{source} now calls itself {coming_manifest.name}, not {name}")
    # The repository release is authoritative even when its version is unchanged:
    # checking it again repairs local edits, additions, and deletions. Only an older
    # repository version is ignored.
    if (coming_manifest.version != current.version
            and not updater.is_newer(coming_manifest.version, current.version)):
        return current
    removed = {called for called, _ in current.manifest.skills} - {
        called for called, _ in coming_manifest.skills
    }
    used = sorted(removed.intersection(granted))
    if used and retiring is None:
        raise InUse(f"cannot remove granted skills: {', '.join(used)}")
    _preflight(coming_manifest, current.at, library)
    retired = _retired(coming_manifest, current.at, library)
    coming = current.at / COMING
    previous = current.at / PREVIOUS
    retirement = retiring(removed) if retiring is not None else contextlib.nullcontext()
    with retirement:
        shutil.rmtree(coming, ignore_errors=True)
        shutil.rmtree(previous, ignore_errors=True)
        shutil.copytree(fetched, coming)
        previous.mkdir()
        _stash(retired, previous / "retired")
        moved_current = False
        activated = False
        try:
            os.replace(current.at / APP, previous / APP)
            moved_current = True
            os.replace(coming, current.at / APP)
            activated = True
            _relink(current.manifest, coming_manifest, current.at, library)
            _write_provenance(current.at, source, coming_manifest.version, seeded=seeded)
        except Exception as original:
            try:
                if activated and (current.at / APP).exists():
                    shutil.rmtree(current.at / APP)
                if moved_current:
                    os.replace(previous / APP, current.at / APP)
                if activated:
                    # `_relink` can fail halfway through. Reassert the complete old view.
                    _unlink_owned(current.at, library)
                    _link_all(current.manifest, current.at, library)
                _restore_stash(previous / "retired", library)
                _write_provenance(current.at, source, current.version, seeded=seeded)
            except Exception as rollback:
                raise RollbackFailed(
                    f"updating {name} failed ({original}); restoring {current.version} "
                    f"also failed ({rollback})"
                ) from rollback
            raise
        shutil.rmtree(previous, ignore_errors=True)
    return installed(root)[name]


def remove(name: str, where: Path | None = None, skills_dir: Path | None = None,
           granted=(), retiring=None) -> list[str]:
    """Remove one catalog, retiring stopped-agent grants when coordinated by a caller."""
    root = home(where)
    library = skills_dir if skills_dir is not None else skill.home()
    with skill.changing_grants(library):
        current = installed(root).get(name)
        if current is None:
            raise Unknown(f"there is no installed catalog called {name}")
        names = {called for called, _ in current.manifest.skills}
        used = sorted(names.intersection(granted))
        if used and retiring is None:
            raise InUse(f"revoke these skills first: {', '.join(used)}")
        with tempfile.TemporaryDirectory(prefix="rundesk-catalog-removal-") as temporary:
            saved = Path(temporary) / current.at.name
            shutil.copytree(current.at, saved)
            retirement = retiring(names) if retiring is not None else contextlib.nullcontext()
            with retirement:
                try:
                    _unlink_owned(current.at, library)
                    shutil.rmtree(current.at)
                except Exception as original:
                    try:
                        _unlink_owned(current.at, library)
                        if current.at.exists():
                            shutil.rmtree(current.at)
                        shutil.copytree(saved, current.at)
                        _link_all(current.manifest, current.at, library)
                    except Exception as rollback:
                        raise RollbackFailed(
                            f"removing {name} failed ({original}); restoring its catalog "
                            f"also failed ({rollback})"
                        ) from rollback
                    raise
    with contextlib.suppress(OSError):
        root.rmdir()
    return sorted(names)


def take_back_seeded(where: Path | None = None,
                     skills_dir: Path | None = None, retiring=None) -> list[str]:
    """Remove only the general catalog Rundesk seeded, for a matching uninstall."""
    root = home(where)
    current = installed(root).get(DEFAULT_NAME)
    if current is None or provenance(current.at).get("seeded") is not True:
        return []
    return remove(DEFAULT_NAME, root, skills_dir, retiring=retiring)


def whose(entry: Path, where: Path | None = None) -> str | None:
    """Which installed catalog owns a library link, if any."""
    if not entry.is_symlink():
        return None
    root = home(where).resolve()
    try:
        target = entry.resolve()
        relative = target.relative_to(root)
    except (OSError, ValueError):
        return None
    return relative.parts[0] if len(relative.parts) > 2 and relative.parts[1] == APP else None


def _preflight(manifest: Manifest, target: Path, library: Path) -> None:
    for called, _ in manifest.skills:
        standing = library / called
        if not standing.is_symlink() and not standing.exists():
            continue
        if _linked_to(standing, target):
            continue
        # A retired built-in is still Rundesk-owned, and an explicit catalog install is
        # its handoff. A current built-in remains product policy and cannot be replaced.
        if ((standing / skill.OWNED).is_file() and called not in skill.shipped()):
            continue
        raise InTheWay(f"the skill {called} is already there and this catalog does not own it")


def _retired(manifest: Manifest, target: Path, library: Path) -> list[Path]:
    """Release-owned packages an explicit catalog install is allowed to adopt."""
    return [
        library / called
        for called, _ in manifest.skills
        if (library / called).is_dir()
        and not (library / called).is_symlink()
        and ((library / called) / skill.OWNED).is_file()
        and called not in skill.shipped()
        and not _linked_to(library / called, target)
    ]


def _stash(entries: list[Path], at: Path) -> None:
    """Move retired built-ins aside, restoring a partial move if one cannot finish."""
    if not entries:
        return
    at.mkdir(parents=True)
    moved = []
    try:
        for entry in entries:
            os.replace(entry, at / entry.name)
            moved.append(entry)
    except OSError:
        for entry in reversed(moved):
            os.replace(at / entry.name, entry)
        with contextlib.suppress(OSError):
            at.rmdir()
        raise


def _restore_stash(at: Path, library: Path) -> None:
    try:
        entries = list(at.iterdir())
    except OSError:
        return
    for saved in entries:
        standing = library / saved.name
        if standing.is_symlink():
            standing.unlink()
        elif standing.exists():
            raise InTheWay(f"cannot restore retired built-in {saved.name}; {standing} is in the way")
        os.replace(saved, standing)
    with contextlib.suppress(OSError):
        at.rmdir()


def _link_all(manifest: Manifest, target: Path, library: Path) -> None:
    library.mkdir(parents=True, exist_ok=True)
    for called, relative in manifest.skills:
        standing = library / called
        if standing.exists() and not standing.is_symlink():
            if (standing / skill.OWNED).is_file() and called not in skill.shipped():
                shutil.rmtree(standing)
            else:
                raise InTheWay(f"the skill {called} is already there")
        elif standing.is_symlink():
            standing.unlink()
        standing.symlink_to(os.path.relpath(target / APP / relative, library))


def _relink(before: Manifest, after: Manifest, target: Path, library: Path) -> None:
    before_names = {called for called, _ in before.skills}
    after_names = {called for called, _ in after.skills}
    for called in sorted(before_names - after_names):
        standing = library / called
        if _linked_to(standing, target):
            standing.unlink()
    _link_all(after, target, library)


def _unlink_owned(target: Path, library: Path) -> None:
    try:
        entries = list(library.iterdir())
    except OSError:
        return
    for standing in entries:
        if _linked_to(standing, target):
            with contextlib.suppress(OSError):
                standing.unlink()


def _linked_to(entry: Path, target: Path) -> bool:
    if not entry.is_symlink():
        return False
    try:
        return target.resolve() in entry.resolve().parents
    except OSError:
        return False


def _write_provenance(at: Path, source: str, version: str, seeded: bool | None = None) -> None:
    page = at / PROVENANCE
    coming = at / f".{PROVENANCE}.coming"
    coming.write_text(
        json.dumps({
            "source": source,
            "version": version,
            **({"seeded": seeded} if seeded is not None else {}),
        }, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(coming, page)


def _fetch(source, work: Path) -> Path:
    """Fetch a GitHub repository URL, or use a local directory/archive."""
    local = Path(str(source))
    if local.exists():
        return unpack(local, work / "unpacked")
    match = GITHUB.match(str(source).strip())
    if match is None:
        raise NotACatalog(
            "the source must be a local path or an https://github.com/<owner>/<repo> URL"
        )
    slug = f"{match.group('owner')}/{match.group('repo')}"
    request = urllib.request.Request(
        ARCHIVE_URL.format(slug=slug), headers={"User-Agent": updater.USER_AGENT}
    )
    archive = work / "catalog.tar.gz"
    try:
        with urllib.request.urlopen(request, timeout=updater.DOWNLOAD_TIMEOUT) as response:
            archive.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as why:
        raise NotACatalog(f"{source} could not be downloaded: {why}") from why
    return unpack(archive, work / "unpacked")


def unpack(source: Path, destination: Path) -> Path:
    if source.is_dir():
        return source
    try:
        with tarfile.open(source, "r:*") as archive:
            updater.safe_extract(archive, destination)
    except (OSError, tarfile.TarError, ValueError) as why:
        raise NotACatalog(f"{source} could not be unpacked safely: {why}") from why
    if (destination / MANIFEST).is_file():
        return destination
    try:
        children = [one for one in destination.iterdir() if one.is_dir()]
    except OSError as why:
        raise NotACatalog(f"{source} has no readable catalog") from why
    if len(children) == 1 and (children[0] / MANIFEST).is_file():
        return children[0]
    raise NotACatalog(f"there is no {MANIFEST} in {source}")
