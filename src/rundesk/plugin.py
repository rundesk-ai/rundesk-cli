"""A plugin somebody else wrote: what one is, where it stands, and moving between versions.

**A plugin is files, never code rundesk loads.** It contributes an executable an agent runs
in its own process, and Markdown a brain reads by itself. Nothing here imports a stranger's
module into the gateway that holds every other agent — the same line `provider-adapter`
draws, drawn once more. The only plugin code rundesk itself executes is a migration step,
and that runs in the window an update already stands every gateway down for.

**Two directories, and the split is the whole design.** `app/` is the release: replaced whole
by an update, taken whole by a removal. `state/` is what the plugin keeps: never replaced,
kept when the plugin is removed unless somebody asks for it to go. That is `ROOT` and
`data_home()` one level down, and for the same reason — an update is then structurally
incapable of costing an owner a year of cached data rather than careful about it.

**One install, every agent, one copy of the records.** A plugin's command is linked into the
shared script library, which every agent already receives first on its PATH, so installing
one is what shares it. Its records are one database that several agents reach at once, which
is why a plugin opens them in WAL and why every step that changes their shape runs while
nothing an owner runs is up.

**Nothing here can replace a file it did not lay down.** A name is not proof — `skill.py`
learned that when a release shipped a built-in whose name an owner had already used — so a
plugin's directory carries a marker, and a link is removed only when it is a link rundesk
made into this plugin. An owner's own script called `jira` refuses the install rather than
being overwritten by one.
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
from pathlib import Path

from rundesk import plugins_home
from rundesk import migration, script, skill, updater

#: The file that makes a directory a plugin, and the whole of its contract.
MANIFEST = "manifest.json"

#: The highest manifest *format* this release can read. Not the plugin's version — the
#: shape of the file that declares it. A plugin written against a format from next year is
#: refused and says so, rather than being read hopefully by code that cannot know which
#: fields moved. Same posture as a migration: a step forward exists, and a step back does
#: not (R-PLG-3).
SCHEMA = 1

#: The proof that a directory under the plugins home is rundesk's to replace or remove.
#: Written when a plugin lands, and asked before anything is taken away.
OWNED = ".rundesk-plugin"

#: What is installed, where each came from, and at which tag — the one record of provenance.
#: Written only after the thing it describes is actually on disk.
LEDGER = "plugins.json"

#: The release, and what the plugin keeps. Named here so nothing else spells them.
APP = "app"
STATE = "state"

#: Where a release is assembled before it is swapped in. Built whole beside the live one and
#: renamed over it, the trick `skill.lay_down` uses: the worst an interrupted update can
#: leave is the version that was already working.
COMING = ".app.coming"

#: Where the records this update might have to put back are kept, for exactly as long as the
#: move they insure is unproved.
ROLLBACK = ".state.rollback"

#: What a plugin, a command and a skill may be called. The tightest of the three brains
#: rather than ours, borrowed from `skill.ALLOWED` so a plugin cannot ship a skill whose
#: name a loader silently drops — and applied to command names too, because a command is a
#: word somebody types and `rm -rf` is also a word somebody could type.
ALLOWED = skill.ALLOWED

#: How long a name may be, for the same reason `skill.NAMED_LIMIT` exists.
NAMED_LIMIT = skill.NAMED_LIMIT

#: The comparisons a `requires` range may use. Deliberately short, and the refusal is
#: deliberate too: `dependencies.py` already decided that a narrow answer with an honest
#: refusal beats a broad guess, and a plugin that declares a range this cannot judge is
#: refused rather than assumed to fit.
UNDERSTOOD = (">=", "==", "<")

_RANGE = re.compile(r"^(>=|==|<)\s*(\d+(?:\.\d+){0,2})$")

#: Where a plugin's own release is published. One constant, as `updater.REPO_SLUG` is.
PLUGIN_RELEASES_URL = "https://api.github.com/repos/{slug}/releases/latest"
PLUGIN_ARCHIVE_URL = "https://github.com/{slug}/archive/refs/tags/{tag}.tar.gz"

#: `owner/repo`, optionally `@v1.2.0`. Anything else is a path on this machine, which is
#: the primitive: fetching is a convenience laid over installing from a directory.
SLUG = re.compile(r"^(?P<slug>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)(?:@(?P<tag>[^@/\s]+))?$")


class NotAPlugin(Exception):
    """A directory that is not a plugin, and the reason nobody could install it."""


class InTheWay(Exception):
    """Something already stands where a plugin's file would, and rundesk did not put it there."""


class Unknown(Exception):
    """A plugin nobody has installed."""


def home() -> Path:
    """Where installed plugins stand — resolved in one place, and only one (`plugins_home`).

    **Everything else here resolves the same way**, through the module that owns the
    question: `script.home()` and `skill.home()` rather than the paths under them. Those two
    read an override that the raw resolvers do not, so linking through the raw ones answered
    about the real machine while every other part of a scratch install answered about the
    scratch one — and the suite proved it by leaving a live link in the developer's own
    script library, pointing into a temporary directory that was already gone.
    """
    return plugins_home()


class Manifest:
    """What one plugin declares about itself, read and checked, never guessed at."""

    __slots__ = ("name", "version", "description", "requires", "commands", "skills",
                 "credentials", "migrations", "at")

    def __init__(self, name, version, description, requires, commands, skills,
                 credentials, migrations, at):
        self.name = name
        self.version = version
        self.description = description
        self.requires = requires
        self.commands = commands        # ((name, relative path), ...)
        self.skills = skills            # (relative path, ...)
        self.credentials = credentials  # ((name, required, about), ...)
        self.migrations = migrations    # a relative path, or None
        self.at = at                    # the directory it was read from

    def steps(self) -> list:
        """Every migration step this release ships, in the order they must run."""
        if self.migrations is None:
            return []
        return migration.found(self.at / self.migrations)

    def wants(self) -> int:
        """The records version this release expects, read off the steps it ships.

        Off the steps rather than out of the manifest, exactly as rundesk reads its own
        (R-MIG-15): a number declared twice is a number that disagrees with itself the day
        somebody adds a step and forgets the other place.
        """
        steps = self.steps()
        return steps[-1].version if steps else 0


def read(at: Path) -> Manifest:
    """One plugin's manifest, or a refusal naming the first thing wrong with it.

    **Everything is checked here, before anything is written where it counts.** An install
    that discovers a bad skill name half way through has already put a directory on a
    machine somebody now has to clean up by hand, so the whole of the refusal happens
    against a temporary directory (R-PLG-2).
    """
    at = Path(at)
    page = at / MANIFEST
    if not page.is_file():
        raise NotAPlugin(f"there is no {MANIFEST} in {at}")
    try:
        said = json.loads(page.read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        raise NotAPlugin(f"{MANIFEST} could not be read: {why}")
    if not isinstance(said, dict):
        raise NotAPlugin(f"{MANIFEST} is not an object")

    schema = said.get("manifest")
    if not isinstance(schema, int) or schema < 1:
        raise NotAPlugin(
            f"{MANIFEST} does not say which manifest format it is written in — "
            f'it needs "manifest": {SCHEMA}'
        )
    if schema > SCHEMA:
        raise NotAPlugin(
            f"this plugin is written against manifest format {schema} and this rundesk "
            f"reads {SCHEMA} — update rundesk first"
        )

    name = said.get("name")
    why = _why_not_a_name(name, "plugin")
    if why:
        raise NotAPlugin(why)
    version = said.get("version")
    if not isinstance(version, str) or updater.parse_version(version) is None:
        raise NotAPlugin(f"{name} does not carry a version anybody could compare")

    requires = said.get("requires") or {}
    if not isinstance(requires, dict):
        raise NotAPlugin(f"{name}'s requires is not an object")
    wanted = requires.get("rundesk")
    if wanted is not None and not isinstance(wanted, str):
        raise NotAPlugin(f"{name}'s requires.rundesk is not a version range")
    if isinstance(wanted, str) and _range(wanted) is None:
        raise NotAPlugin(
            f"{name} needs rundesk '{wanted}', which this cannot judge — "
            f"a range is one or more of {', '.join(UNDERSTOOD)} separated by commas"
        )

    provides = said.get("provides") or {}
    if not isinstance(provides, dict):
        raise NotAPlugin(f"{name}'s provides is not an object")
    commands = _commands(provides.get("commands") or [], at, name)
    skills = _skills(provides.get("skills") or [], at, name)
    if not commands and not skills:
        raise NotAPlugin(f"{name} provides no command and no skill, so installing it "
                         "would give every agent nothing")

    credentials = _credentials(said.get("credentials") or [], name)
    migrations = _migrations(said.get("migrations"), at, name)

    return Manifest(name, version, str(said.get("description") or ""), wanted,
                    commands, skills, credentials, migrations, at)


def _why_not_a_name(name, what: str) -> str | None:
    if not isinstance(name, str) or not name:
        return f"this {what} has no name"
    if len(name) > NAMED_LIMIT:
        return f"the {what} name {name} is longer than {NAMED_LIMIT} characters"
    if not ALLOWED.match(name):
        return (f"the {what} name {name} is not lowercase letters, digits and single "
                "hyphens, which is the only shape every brain and every shell accepts")
    return None


def _inside(at: Path, said, name: str, what: str) -> Path:
    """A path a manifest named, held to landing inside the plugin that named it.

    **The check that keeps a manifest from naming any file on the machine.** `Path("/a") /
    "../../etc/passwd"` is a real path outside `/a`, and an absolute one discards the left
    side entirely — so a command could otherwise be linked to `/bin/rm` and a removal would
    then unlink it. Same rule `updater._lands_inside` holds a tarball to, one layer up.
    """
    if not isinstance(said, str) or not said:
        raise NotAPlugin(f"{name} names a {what} that is not a path")
    if Path(said).is_absolute():
        raise NotAPlugin(f"{name} names an absolute {what} path, which is never inside it")
    landing = (at / said).resolve()
    root = at.resolve()
    if root != landing and root not in landing.parents:
        raise NotAPlugin(f"{name}'s {what} '{said}' points outside the plugin")
    return landing


def _commands(said, at: Path, name: str) -> tuple:
    if not isinstance(said, list):
        raise NotAPlugin(f"{name}'s provides.commands is not a list")
    found = []
    for one in said:
        if not isinstance(one, dict):
            raise NotAPlugin(f"{name} lists a command that is not an object with a "
                             "name and a path")
        called = one.get("name")
        why = _why_not_a_name(called, "command")
        if why:
            raise NotAPlugin(f"{name}: {why}")
        landing = _inside(at, one.get("path"), name, "command")
        if not landing.is_file():
            raise NotAPlugin(f"{name} says its command {called} is at "
                             f"{one.get('path')}, and there is no such file")
        if not os.access(landing, os.X_OK):
            raise NotAPlugin(f"{name}'s command {called} is not executable — "
                             f"chmod +x {one.get('path')} before publishing")
        found.append((called, one["path"]))
    named = [one for one, _ in found]
    if len(set(named)) != len(named):
        raise NotAPlugin(f"{name} lists one command name twice")
    return tuple(found)


def _skills(said, at: Path, name: str) -> tuple:
    if not isinstance(said, list):
        raise NotAPlugin(f"{name}'s provides.skills is not a list")
    found = []
    for one in said:
        landing = _inside(at, one, name, "skill")
        why = skill.valid(landing)
        if why:
            raise NotAPlugin(f"{name} ships a skill that no brain would index: {why}")
        found.append(one)
    named = [Path(one).name for one in found]
    if len(set(named)) != len(named):
        raise NotAPlugin(f"{name} ships two skills under one name")
    return tuple(found)


def _credentials(said, name: str) -> tuple:
    """The names a plugin needs in its environment — and never, ever their values.

    Declared so `rundesk plugins` can say which are missing before an agent finds out
    mid-turn. A manifest carrying something that looks like a value is refused outright:
    this file is published in a public repository, and the mistake is worth catching on
    the machine of whoever wrote it (R-PLG-8).
    """
    if not isinstance(said, list):
        raise NotAPlugin(f"{name}'s credentials is not a list")
    found = []
    for one in said:
        if not isinstance(one, dict):
            raise NotAPlugin(f"{name} lists a credential that is not an object")
        called = one.get("name")
        if not isinstance(called, str) or not called or not called.replace("_", "").isalnum():
            raise NotAPlugin(f"{name} lists a credential with no usable name")
        if "value" in one or "secret" in one or "token" in one:
            raise NotAPlugin(
                f"{name}'s credential {called} carries a value in the manifest — "
                "a manifest is published, so it holds names and never values"
            )
        found.append((called, bool(one.get("required")), str(one.get("about") or "")))
    return tuple(found)


def _migrations(said, at: Path, name: str):
    if said is None:
        return None
    landing = _inside(at, said, name, "migrations")
    if not landing.is_dir():
        raise NotAPlugin(f"{name} says its steps are in '{said}', and there is no such "
                         "directory")
    try:
        migration.found(landing)
    except ValueError as why:
        raise NotAPlugin(f"{name}'s steps cannot be ordered: {why}")
    return said


def _range(said: str):
    """A version range as clauses this understands, or None when it cannot judge it."""
    clauses = []
    for part in said.split(","):
        match = _RANGE.match(part.strip())
        if not match:
            return None
        clauses.append((match.group(1), updater.parse_version(match.group(2))))
    return clauses or None


def fits(wanted, version: str) -> bool:
    """Whether a rundesk of this version satisfies what a plugin asked for.

    A plugin that named no range fits anything, which is the honest reading of saying
    nothing — and the range it did name is judged against the rundesk **about to run**,
    never the one running now (R-PLG-14).
    """
    if not wanted:
        return True
    clauses = _range(wanted)
    if clauses is None:
        return False
    here = updater.parse_version(version)
    if here is None:
        return False
    for how, against in clauses:
        if how == ">=" and not here >= against:
            return False
        if how == "==" and not here == against:
            return False
        if how == "<" and not here < against:
            return False
    return True


class Outcome:
    """What became of one plugin when something tried to move it.

    **A row, not a sentence.** An update reports every plugin it looked at, in order, and a
    reader needs to see at a glance which moved and which did not — so what happened is a
    state and two versions rather than prose somebody has to parse back out. The sentence is
    still there, because a single plugin moved on its own deserves one.
    """

    #: The four words a row can end in, and the line between them is **whether the plugin
    #: still works**. `skipped` is a plugin that was not moved and is fine where it is;
    #: `failed` is one that is now unreachable — off every agent's PATH until somebody
    #: looks. That is the distinction somebody acts on, so it is the one the words carry.
    UPDATED = "updated"
    CURRENT = "up to date"
    FAILED = "failed"
    SKIPPED = "skipped"

    __slots__ = ("name", "was", "now", "state", "why")

    def __init__(self, name: str, state: str, was: str | None = None,
                 now: str | None = None, why: str | None = None):
        self.name = name
        self.state = state
        self.was = was
        self.now = now
        self.why = why

    @property
    def moved(self) -> bool:
        return self.state == self.UPDATED

    @property
    def held(self) -> bool:
        """Installed and unreachable — the only state anybody has to do something about."""
        return self.state == self.FAILED

    def __str__(self) -> str:
        """One plugin on its own, which is the one place there is room for the reason.

        A row in a list says only what became of it; a plugin somebody asked about by name
        says why as well, because there is nothing else on the line to compete with it.
        """
        if self.state == self.UPDATED:
            return f"{self.name}: {self.was} -> {self.now}"
        if self.state == self.CURRENT and not self.why:
            return f"{self.name}: up to date"
        return f"{self.name}: {self.state}" + (f" — {self.why}" if self.why else "")

    def __repr__(self) -> str:
        return f"<{self.name} {self.state}>"


class Installed:
    """One plugin as it stands on this machine right now."""

    __slots__ = ("name", "at", "manifest", "why_unfit")

    def __init__(self, name: str, at: Path, manifest, why_unfit: str | None = None):
        self.name = name
        self.at = at
        self.manifest = manifest
        self.why_unfit = why_unfit

    @property
    def version(self) -> str:
        return self.manifest.version if self.manifest else "?"

    @property
    def app(self) -> Path:
        return self.at / APP

    @property
    def state(self) -> Path:
        return self.at / STATE

    @property
    def quarantined(self) -> bool:
        """Installed, held away from every agent, and waiting for somebody to look.

        A plugin whose update went wrong, or which no longer fits the rundesk now running.
        It is not removed — an owner's records are in it — and it is not linked, because a
        half-working command reaching an agent is the failure this exists to prevent.
        """
        return self.why_unfit is not None


def installed(where: Path | None = None) -> dict:
    """Every plugin on this machine, by name, whether or not each is usable.

    An unreadable manifest is a plugin that is *there and broken*, which is a different
    fact from one that is absent — so it is listed, with why, rather than skipped into
    silence.
    """
    where = where or home()
    try:
        found = sorted(one for one in where.iterdir()
                       if one.is_dir() and not one.name.startswith("."))
    except OSError:
        return {}
    standing = {}
    for at in found:
        if not (at / OWNED).is_file():
            continue
        try:
            manifest = read(at / APP)
            standing[at.name] = Installed(at.name, at, manifest, _held(at))
        except NotAPlugin as why:
            standing[at.name] = Installed(at.name, at, None, str(why))
    return standing


#: Written beside a plugin when it may not be linked, holding the reason in words. A file
#: rather than a field in the ledger: the ledger says what an owner installed, and this says
#: what rundesk did about it — and a plugin whose ledger entry was lost must still stay away
#: from every agent.
UNFIT = ".unfit"


def _held(at: Path) -> str | None:
    try:
        return (at / UNFIT).read_text(encoding="utf-8").strip() or "held back"
    except OSError:
        return None


def hold(at: Path, why: str) -> None:
    """Keep this plugin away from every agent, and say why in a place somebody will read."""
    with contextlib.suppress(OSError):
        (at / UNFIT).write_text(why + "\n", encoding="utf-8")


def release(at: Path) -> None:
    """Let a plugin be linked again, now that whatever held it back is settled."""
    with contextlib.suppress(OSError):
        (at / UNFIT).unlink()


def ledger(where: Path | None = None) -> dict:
    """Where each installed plugin came from, and at which tag.

    Unreadable is not empty and is never written back as empty: a ledger that could not be
    parsed is a fact to report, and rewriting it with `{}` would erase the provenance of
    every plugin on the machine to tidy up one bad character.
    """
    at = (where or home()) / LEDGER
    try:
        said = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as why:
        raise NotAPlugin(f"{at} could not be read: {why}")
    return said if isinstance(said, dict) else {}


def remember(name: str, entry: dict, where: Path | None = None) -> None:
    """Record where a plugin came from — only once it is actually on disk."""
    where = where or home()
    where.mkdir(parents=True, exist_ok=True)
    try:
        held = ledger(where)
    except NotAPlugin:
        held = {}
    held[name] = entry
    at = where / LEDGER
    coming = at.with_name(f".{LEDGER}.coming")
    coming.write_text(json.dumps(held, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(coming, at)


def forget(name: str, where: Path | None = None) -> None:
    where = where or home()
    try:
        held = ledger(where)
    except NotAPlugin:
        return
    if held.pop(name, None) is None:
        return
    at = where / LEDGER
    coming = at.with_name(f".{LEDGER}.coming")
    coming.write_text(json.dumps(held, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(coming, at)


# ---------------------------------------------------------------------------
# Getting one onto the machine
# ---------------------------------------------------------------------------

def source_is_remote(source: str) -> tuple[str, str | None] | None:
    """`owner/repo[@tag]` as its two parts, or None when this names a path instead.

    A directory on the machine is the primitive and a slug is the convenience — so this
    answers "did somebody mean the network", and everything else is a path. A local
    directory that happens to be called `a/b` is still a path: it is checked first.
    """
    match = SLUG.match(source.strip())
    if not match or Path(source).exists():
        return None
    return match.group("slug"), match.group("tag")


def latest_release(slug: str) -> tuple[str | None, str | None]:
    """The newest published release of a plugin, and which kind of nothing when there is none.

    The same shape and the same refusals as `updater.latest_version_online`, including
    carrying no credentials: a plugin is published in the open, and a machine that happens
    to have a token exported must not send it on a question nobody asked to authenticate.
    """
    request = urllib.request.Request(PLUGIN_RELEASES_URL.format(slug=slug),
                                     headers={"User-Agent": updater.USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=updater.HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return None, (updater.NOTHING_PUBLISHED if err.code == 404 else updater.UNREACHABLE)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, updater.UNREACHABLE
    if not isinstance(payload, dict):
        return None, updater.UNREACHABLE
    tag = payload.get("tag_name")
    if isinstance(tag, str) and tag:
        return tag, None
    return None, updater.UNREACHABLE


def download(slug: str, tag: str, into: Path) -> Path:
    """Fetch that tag of that repository and unpack it, returning what came out."""
    url = PLUGIN_ARCHIVE_URL.format(slug=slug, tag=tag)
    request = urllib.request.Request(url, headers={"User-Agent": updater.USER_AGENT})
    archive = into / "plugin.tar.gz"
    try:
        with urllib.request.urlopen(request, timeout=updater.DOWNLOAD_TIMEOUT) as response:
            archive.write_bytes(response.read())
    except (urllib.error.URLError, TimeoutError, OSError) as why:
        raise NotAPlugin(f"{slug} {tag} could not be downloaded: {why}")
    return unpack(archive, into / "unpacked")


def unpack(source: Path, into: Path) -> Path:
    """A plugin's files out of a directory or a tarball, and where its manifest stands.

    A tarball is extracted through the same traversal guard an update uses — a plugin
    archive is a stranger's, which is exactly the case that guard was written for — and a
    release archive from a forge holds one directory that everything is under, so the
    manifest is looked for at the root and one level down and nowhere else.
    """
    source = Path(source)
    if source.is_dir():
        return _rooted(source, source)
    into.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(source) as tar:
            updater.safe_extract(tar, into)
    except (tarfile.TarError, ValueError, OSError) as why:
        raise NotAPlugin(f"{source.name} is not an archive this can open: {why}")
    return _rooted(into, source)


def _rooted(at: Path, called) -> Path:
    if (at / MANIFEST).is_file():
        return at
    inside = [one for one in sorted(at.iterdir()) if one.is_dir()]
    if len(inside) == 1 and (inside[0] / MANIFEST).is_file():
        return inside[0]
    raise NotAPlugin(f"there is no {MANIFEST} in {getattr(called, 'name', called)}")


def install(source, where: Path | None = None, scripts_dir: Path | None = None,
            skills_dir: Path | None = None, version: str | None = None,
            fetch=None, note=None, clock=None) -> Installed:
    """Put a plugin on this machine, or leave the machine exactly as it was.

    **Linking is last, and that is the whole shape of it** (R-PLG-9). Everything that can
    fail — reading the manifest, refusing a name already taken, laying the release down,
    running its steps — happens while no agent can see any of it. Only once all of that has
    worked does a command appear on every agent's PATH, so a failed install is invisible
    rather than half visible.
    """
    where = where or home()
    say = note or (lambda said: None)
    from rundesk import __version__

    with tempfile.TemporaryDirectory() as work:
        got = (fetch or _fetch)(source, Path(work), say)
        manifest = read(got.at)
        if got.tag and not _tag_matches(got.tag, manifest.version):
            raise NotAPlugin(
                f"{manifest.name} is published as {got.tag} and its manifest says "
                f"{manifest.version} — a release tagged differently from what it declares "
                "is one nobody can reason about"
            )
        if not fits(manifest.requires, version or __version__):
            raise NotAPlugin(
                f"{manifest.name} {manifest.version} needs rundesk "
                f"'{manifest.requires}', and this is {version or __version__}"
            )
        standing = installed(where).get(manifest.name)
        # **A removal that kept the records leaves a directory, and installing over it is
        # the thing that directory exists for** (R-PLG-42). What is left has no release in
        # it, so there is nothing to update and refusing would tell an owner to run a verb
        # that cannot work — while the records they were promised sit there unreachable.
        if standing is not None and (standing.at / APP).is_dir():
            raise InTheWay(f"{manifest.name} is already installed — "
                           f"use: rundesk plugins update {manifest.name}")
        _refuse_taken_names(manifest, scripts_dir, skills_dir, where)

        at = where / manifest.name
        at.mkdir(parents=True, exist_ok=True)
        (at / OWNED).write_text("rundesk plugin\n", encoding="utf-8")
        # Whatever held the remnant back was about the release that is now gone, and the
        # release replacing it has not been judged yet — so the mark comes off here rather
        # than being carried into a plugin that is being installed fresh.
        release(at)
        _lay_down(got.at, at)
        say(f"{manifest.name} {manifest.version}: installed")
        went_wrong = carry(at, manifest, note=say, clock=clock)
        if went_wrong:
            shutil.rmtree(at, ignore_errors=True)
            raise NotAPlugin(f"{manifest.name}'s records could not be made: {went_wrong}")
        link(manifest, at, scripts_dir, skills_dir)
        remember(manifest.name, {
            "source": got.source,
            "tag": got.tag,
            "sha256": got.sha256,
            "version": manifest.version,
            "installed_at": (clock or migration._now)(),
        }, where)
    return Installed(manifest.name, at, read(at / APP))


class Got:
    """A plugin's files, wherever they came from, and what is known about where that was."""

    __slots__ = ("at", "source", "tag", "sha256")

    def __init__(self, at: Path, source: str, tag: str | None, sha256: str | None):
        self.at = at
        self.source = source
        self.tag = tag
        self.sha256 = sha256


def _fetch(source, work: Path, say) -> Got:
    """A plugin from a slug or from a path on this machine.

    The network is reached only when a slug was named, and it is behind this one function
    so the whole of install and update is exercised without it.
    """
    remote = source_is_remote(str(source))
    if remote is None:
        at = Path(source)
        if not at.exists():
            raise NotAPlugin(f"there is nothing at {at}")
        return Got(unpack(at, work / "unpacked"), str(at), None,
                   _sha256(at) if at.is_file() else None)
    slug, tag = remote
    if tag is None:
        tag, why = latest_release(slug)
        if tag is None:
            raise NotAPlugin(
                f"{slug}: nothing is published there" if why == updater.NOTHING_PUBLISHED
                else f"{slug} could not be reached"
            )
    say(f"{slug} {tag}: downloading")
    at = download(slug, tag, work)
    archive = work / "plugin.tar.gz"
    return Got(at, slug, tag, _sha256(archive) if archive.is_file() else None)


def _sha256(at: Path) -> str | None:
    import hashlib
    try:
        return hashlib.sha256(at.read_bytes()).hexdigest()
    except OSError:
        return None


def _tag_matches(tag: str, version: str) -> bool:
    """A plugin is held to the rule rundesk holds itself to (`updater.tag_matches`)."""
    return updater.tag_matches(tag, version)


def _refuse_taken_names(manifest: Manifest, scripts_dir, skills_dir, where) -> None:
    """Refuse before landing anything when a name an owner already uses is claimed.

    **A name is never proof of ownership.** An owner's own `jira` script and a plugin that
    provides one are two different files, and the plugin does not get to win — the whole
    lesson `skill.py` records about built-ins, applied to a stranger's release, where it
    matters more.
    """
    scripts_dir = scripts_dir or script.home()
    skills_dir = skills_dir or skill.home()
    for called, _path in manifest.commands:
        standing = scripts_dir / called
        if standing.is_symlink() or standing.exists():
            if not _linked_here(standing, where):
                raise InTheWay(f"{standing} is already there and rundesk did not put it "
                               f"there — {manifest.name} would replace it")
    for one in manifest.skills:
        standing = skills_dir / Path(one).name
        if standing.is_symlink() or standing.exists():
            if not _linked_here(standing, where):
                raise InTheWay(f"a skill called {Path(one).name} is already in the "
                               f"library and {manifest.name} would replace it")


def whose(entry: Path, where: Path | None = None) -> str | None:
    """Which plugin this library entry really belongs to, or None when it is nobody's.

    Asked by the skills catalog. A skill a plugin shipped is a link into that plugin, and
    calling it the owner's — which is what "not a built-in" used to mean — tells somebody
    a third party's file is theirs to edit, and hides the one fact that matters when it
    changes under them: it will be replaced by the next `plugins update`.
    """
    if not entry.is_symlink():
        return None
    root = (where or home()).resolve()
    try:
        target = entry.resolve()
    except OSError:
        return None
    if root not in target.parents:
        return None
    return target.relative_to(root).parts[0]


def _linked_here(entry: Path, where: Path | None = None) -> bool:
    """Whether this is a link rundesk made into the plugins directory.

    Asked before anything is replaced or removed. A real file somebody wrote, and a link
    pointing somewhere else entirely, are both things rundesk did not put there — the same
    question `skill.ours` asks, and it has to be incapable of removing an owner's work
    rather than careful about it.
    """
    if not entry.is_symlink():
        return False
    root = (where or home()).resolve()
    try:
        target = entry.resolve()
    except OSError:
        return False
    return root in target.parents


def _lay_down(got: Path, at: Path) -> None:
    """Put a release into place beside the records, without ever touching them.

    Assembled under another name and renamed over the live one: if anything fails between
    the two, what is left is the version that was already working rather than a directory
    that exists and is not a plugin.
    """
    coming = at / COMING
    shutil.rmtree(coming, ignore_errors=True)
    shutil.copytree(got, coming, symlinks=True)
    app = at / APP
    if app.exists():
        shutil.rmtree(app)
    os.replace(coming, app)
    (at / STATE).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# The records a plugin keeps, and moving them
# ---------------------------------------------------------------------------

def carry(at: Path, manifest: Manifest, note=None, clock=None) -> str | None:
    """Bring one plugin's shared records up to what its release expects.

    Says what went wrong rather than raising it, because every caller is a decision about
    an install or an update and not a place to handle a database error.

    **One store, not one per agent.** Rundesk walks every agent because two are never at
    the same version; a plugin has exactly one set of records and therefore one version, so
    this is a single pass. Everything else is the same runner — a step is found rather than
    listed, and its work and its version stamp commit together.
    """
    want = manifest.wants()
    if not want:
        return None
    state = at / STATE
    state.mkdir(parents=True, exist_ok=True)
    steps = manifest.at / manifest.migrations
    kept = _set_records_aside(state, at / ROLLBACK)
    try:
        migration.carry(state / migration.RECORDS, at, want, where=steps, note=note,
                        clock=clock, log=LOG)
    except Exception as stopped:      # noqa: BLE001 — a boundary, reporting truthfully
        _put_records_back(kept)
        return str(stopped)
    _let_records_go(at / ROLLBACK)
    return None


#: Where a plugin's own log goes. Beside the release rather than in it, so an update that
#: replaces `app/` does not take away the only account of what the update did.
LOG = "logs/plugin.log"


def _set_records_aside(state: Path, aside: Path) -> list:
    """A copy of what a plugin keeps, taken while nothing an owner runs is up.

    The way back is not a reverse step — there is no such thing — but a copy taken before
    anything ran, which is the same shape `migration.carry_every_or_put_back` uses one
    level up (R-MIG-19).
    """
    shutil.rmtree(aside, ignore_errors=True)
    records = state / migration.RECORDS
    if not records.exists():
        return []
    aside.mkdir(parents=True, exist_ok=True)
    copy = aside / migration.RECORDS
    shutil.copy2(records, copy)
    return [(records, copy)]


def _put_records_back(kept: list) -> None:
    for records, copy in kept:
        with contextlib.suppress(OSError):
            shutil.copy2(copy, records)
            for beside in (records.with_name(records.name + "-wal"),
                           records.with_name(records.name + "-shm")):
                if beside.exists():
                    os.remove(beside)


def _let_records_go(aside: Path) -> None:
    shutil.rmtree(aside, ignore_errors=True)


# ---------------------------------------------------------------------------
# What every agent sees
# ---------------------------------------------------------------------------

def link(manifest: Manifest, at: Path, scripts_dir: Path | None = None,
         skills_dir: Path | None = None) -> None:
    """Put this plugin's command on every agent's PATH and its skills in the library.

    **This is what sharing is.** Nothing is copied into an agent and nothing is recorded
    against one: the command stands in the directory every agent already receives, and the
    skills stand in the library every agent's grants resolve through. One install serves
    all of them, and one removal takes it from all of them.

    Relative links, so moving or copying an install does not leave every command pointing
    at where the old machine kept its plugins.
    """
    scripts_dir = scripts_dir or script.home()
    skills_dir = skills_dir or skill.home()
    for called, path in manifest.commands:
        _stand(scripts_dir, called, at / APP / path, at.parent)
    for one in manifest.skills:
        _stand(skills_dir, Path(one).name, at / APP / one, at.parent)


def _stand(where: Path, name: str, target: Path, plugins: Path) -> None:
    where.mkdir(parents=True, exist_ok=True)
    standing = where / name
    if standing.is_symlink() or standing.exists():
        if not _linked_here(standing, plugins):
            raise InTheWay(f"{standing} is not something rundesk put there")
        standing.unlink()
    standing.symlink_to(os.path.relpath(target, where))


def unlink(manifest, at: Path, scripts_dir: Path | None = None,
           skills_dir: Path | None = None) -> None:
    """Take a plugin's command and skills back out, and touch nothing else.

    Walks what is standing rather than only what a manifest names, because the manifest
    that named them may be the one that could not be read — and a command left on every
    agent's PATH pointing into a plugin that is being taken away is the worst of both.
    """
    scripts_dir = scripts_dir or script.home()
    skills_dir = skills_dir or skill.home()
    for where in (scripts_dir, skills_dir):
        try:
            standing = sorted(where.iterdir())
        except OSError:
            continue
        for entry in standing:
            if entry.is_symlink() and _points_into(entry, at):
                with contextlib.suppress(OSError):
                    entry.unlink()


def _points_into(entry: Path, at: Path) -> bool:
    try:
        target = entry.resolve()
    except OSError:
        return False
    at = at.resolve()
    return at == target or at in target.parents


def relink(where: Path | None = None, scripts_dir: Path | None = None,
           skills_dir: Path | None = None) -> list:
    """Make what every agent sees agree with what is installed, and say what moved.

    Run after an update, where a new release may provide a command the old one did not and
    may have stopped providing one it did. A plugin being held back is unlinked rather than
    skipped: quarantine that leaves the old command standing is not quarantine.
    """
    where = where or home()
    moved = []
    for name, one in sorted(installed(where).items()):
        if one.quarantined or one.manifest is None:
            unlink(one.manifest, one.at, scripts_dir, skills_dir)
            moved.append(f"-{name}")
            continue
        unlink(one.manifest, one.at, scripts_dir, skills_dir)
        link(one.manifest, one.at, scripts_dir, skills_dir)
        moved.append(name)
    return moved


# ---------------------------------------------------------------------------
# Moving one forward, and taking one away
# ---------------------------------------------------------------------------

def update(name: str, where: Path | None = None, scripts_dir: Path | None = None,
           skills_dir: Path | None = None, version: str | None = None,
           fetch=None, note=None, clock=None) -> str | None:
    """Move one plugin to what is published, or leave it exactly where it was.

    Returns an `Outcome` — always one, never None, because "nothing happened" is a row an
    update has to be able to show rather than a silence a reader has to interpret. **A
    failure never raises past here**: the caller is either an owner who asked for one
    plugin, or an update that must land whatever a stranger's release does.
    """
    where = where or home()
    say = note or (lambda said: None)
    from rundesk import __version__
    running = version or __version__

    standing = installed(where).get(name)
    if standing is None:
        raise Unknown(f"there is no plugin called {name}")
    entry = {}
    with contextlib.suppress(NotAPlugin):
        entry = ledger(where).get(name) or {}
    source = entry.get("source")
    if not source:
        return Outcome(name, Outcome.SKIPPED, was=standing.version,
                       why="no record of where it came from")
    if entry.get("pinned"):
        return Outcome(name, Outcome.CURRENT, was=standing.version)

    at = standing.at
    with tempfile.TemporaryDirectory() as work:
        try:
            got = (fetch or _fetch)(source, Path(work), say)
            coming = read(got.at)
        except NotAPlugin as why:
            return Outcome(name, Outcome.SKIPPED, was=standing.version, why=str(why))
        if coming.name != name:
            return Outcome(name, Outcome.SKIPPED, was=standing.version,
                           why=f"what is published there now calls itself {coming.name}")
        if standing.manifest and not updater.is_newer(coming.version, standing.version):
            # Not newer is not the same as broken, and it is not a failure: a plugin that
            # is current stays linked and stays quiet.
            if standing.quarantined and fits(coming.requires, running):
                release(at)
                relink(where, scripts_dir, skills_dir)
                return Outcome(name, Outcome.UPDATED, was=standing.version,
                               now=standing.version, why="fits again, and is back")
            return Outcome(name, Outcome.CURRENT, was=standing.version)
        if not fits(coming.requires, running):
            # **Held at the version it is on, never dragged into a rundesk it disclaims**
            # (R-PLG-14). The plugin that is installed still works; the new one would not.
            return Outcome(name, Outcome.SKIPPED, was=standing.version,
                           why=f"{coming.version} needs rundesk '{coming.requires}' and "
                               f"this is {running}")
        if got.tag and not _tag_matches(got.tag, coming.version):
            return Outcome(name, Outcome.SKIPPED, was=standing.version,
                           why=f"published as {got.tag} but its manifest says "
                               f"{coming.version}")

        kept = _set_app_aside(at)
        try:
            _lay_down(got.at, at)
            went_wrong = carry(at, read(at / APP), note=say, clock=clock)
            if went_wrong:
                raise NotAPlugin(went_wrong)
        except (NotAPlugin, InTheWay, OSError) as why:
            _put_app_back(at, kept)
            hold(at, f"the move to {coming.version} failed: {why}")
            unlink(standing.manifest, at, scripts_dir, skills_dir)
            return Outcome(name, Outcome.FAILED, was=standing.version, now=coming.version,
                           why=f"could not be moved to {coming.version}: {why}")
        _let_app_go(kept)
        release(at)
        try:
            unlink(standing.manifest, at, scripts_dir, skills_dir)
            link(read(at / APP), at, scripts_dir, skills_dir)
        except InTheWay as why:
            hold(at, str(why))
            return Outcome(name, Outcome.FAILED, was=standing.version, now=coming.version,
                           why=str(why))
        remember(name, {**entry, "tag": got.tag, "sha256": got.sha256,
                        "version": coming.version,
                        "installed_at": (clock or migration._now)()}, where)
    return Outcome(name, Outcome.UPDATED, was=standing.version, now=coming.version)


#: Where the release an update is replacing waits until the new one is proved.
PREVIOUS = ".app.previous"


def _set_app_aside(at: Path) -> Path | None:
    app = at / APP
    if not app.is_dir():
        return None
    kept = at / PREVIOUS
    shutil.rmtree(kept, ignore_errors=True)
    os.replace(app, kept)
    return kept


def _put_app_back(at: Path, kept: Path | None) -> None:
    if kept is None or not kept.is_dir():
        return
    app = at / APP
    shutil.rmtree(app, ignore_errors=True)
    with contextlib.suppress(OSError):
        os.replace(kept, app)


def _let_app_go(kept: Path | None) -> None:
    if kept is not None:
        shutil.rmtree(kept, ignore_errors=True)


def bring_forward(where: Path | None = None, scripts_dir: Path | None = None,
                  skills_dir: Path | None = None, version: str | None = None,
                  fetch=None, note=None, clock=None) -> list:
    """Move every plugin forward inside an update's window, and never fail it.

    **A stranger's release cannot take an owner's agents down** (R-PLG-15). This runs after
    every agent's records are forward and before anything comes back up, and whatever it
    meets it returns words rather than raising: a plugin that cannot be moved is held back,
    unlinked and named, and the update it was riding still lands.
    """
    where = where or home()
    say = note or (lambda said: None)
    from rundesk import __version__
    running = version or __version__
    said = []
    for name, one in sorted(installed(where).items()):
        # A plugin whose own manifest cannot be read has nothing to judge and nothing to
        # move. It is already held back by `installed`; saying so is the whole of what is
        # left to do about it.
        if one.manifest is None:
            unlink(None, one.at, scripts_dir, skills_dir)
            said.append(Outcome(name, Outcome.FAILED, why=one.why_unfit))
            continue
        # A plugin that no longer fits the rundesk about to run is held back before it is
        # asked to move, because the version it would move to is not the question — the
        # one already installed is the thing that no longer belongs on every agent's PATH.
        if not fits(one.manifest.requires, running):
            why = (f"needs rundesk '{one.manifest.requires}' and this is {running}")
            hold(one.at, f"{one.version} {why}")
            unlink(one.manifest, one.at, scripts_dir, skills_dir)
            said.append(Outcome(name, Outcome.FAILED, was=one.version, why=why))
            continue
        try:
            said.append(update(name, where, scripts_dir, skills_dir, running,
                               fetch=fetch, note=say, clock=clock))
        except Exception as trouble:    # noqa: BLE001 — a boundary; an update must land
            hold(one.at, str(trouble))
            with contextlib.suppress(Exception):
                unlink(one.manifest, one.at, scripts_dir, skills_dir)
            said.append(Outcome(name, Outcome.FAILED, was=one.version, why=str(trouble)))
    return said


def remove(name: str, where: Path | None = None, scripts_dir: Path | None = None,
           skills_dir: Path | None = None, purge: bool = False) -> str:
    """Take a plugin off this machine, and say what is left.

    **What it kept stays unless somebody asks for it to go.** Removing a plugin to reinstall
    it must not be the thing that costs an owner a year of records, and a removal that
    silently took them would be discovered exactly once.

    Only a directory carrying the marker is touched, and only links that point into it are
    pulled — so nothing here can reach an owner's own script that happens to share a name.
    """
    where = where or home()
    at = _standing(where, name)
    if not (at / OWNED).is_file():
        raise Unknown(f"there is no plugin called {name}")
    manifest = None
    with contextlib.suppress(NotAPlugin):
        manifest = read(at / APP)
    unlink(manifest, at, scripts_dir, skills_dir)
    kept = at / STATE
    if purge:
        shutil.rmtree(at, ignore_errors=True)
        forget(name, where)
        return f"{name} is gone, and so is everything it kept"
    held = None
    if kept.is_dir() and any(kept.iterdir()):
        held = where / f".{name}.state"
        shutil.rmtree(held, ignore_errors=True)
        os.replace(kept, held)
    shutil.rmtree(at, ignore_errors=True)
    if held is not None:
        at.mkdir(parents=True, exist_ok=True)
        (at / OWNED).write_text("rundesk plugin\n", encoding="utf-8")
        os.replace(held, at / STATE)
        hold(at, "removed — its records are kept; install it again, or use --purge")
    forget(name, where)
    return (f"{name} is gone; what it kept is still in {at / STATE}" if held is not None
            else f"{name} is gone")


def _standing(where: Path, name: str) -> Path:
    """Where a plugin by that name would stand, or a refusal.

    **A name is one path component and is checked before it is joined to anything.**
    `Path("/a/b") / "/elsewhere"` is `/elsewhere` — the left side is discarded outright — so
    a name taken from a command line and joined without looking is a way to name any
    directory on the machine, and `remove` then deletes it. The same check `skill._standing`
    makes, for the same reason, on a path that is removed rather than unlinked.
    """
    separators = [os.sep] + ([os.altsep] if os.altsep else [])
    if not name or name in (".", "..") or any(one in name for one in separators):
        raise Unknown(f"'{name}' is not a plugin's name")
    return where / name


# ---------------------------------------------------------------------------
# Starting one
# ---------------------------------------------------------------------------

#: What a new plugin is copied from. Beside the agent and skill templates and read the same
#: way — by looking — so a file added to it is scaffolded without a list kept anywhere else.
TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "plugin"

#: The word the template calls itself, in file names and in file contents alike. One token,
#: cased two ways: the command and the skill are lowercase, and the environment variables a
#: credential file uses are upper.
PLACEHOLDER = "example"


def scaffold(name: str, at: Path) -> Path:
    """Write a plugin somebody can build on — one that installs, as it stands.

    **A working plugin rather than a page about one.** The template is checked by the same
    `read` an install uses, so `plugins init` cannot produce something `plugins check`
    refuses; that is a thing to find out here rather than in somebody's first release.
    """
    why = _why_not_a_name(name, "plugin")
    if why:
        raise NotAPlugin(why)
    at = Path(at)
    if at.exists():
        raise InTheWay(f"{at} is already there")
    if not (TEMPLATE / MANIFEST).is_file():
        raise NotAPlugin(f"there is no plugin template at {TEMPLATE}")
    coming = at.with_name(f".{at.name}.coming")
    shutil.rmtree(coming, ignore_errors=True)
    try:
        shutil.copytree(TEMPLATE, coming)
        for one in sorted(coming.rglob("*"), reverse=True):
            if one.is_file():
                _renamed_inside(one, name)
            if PLACEHOLDER in one.name:
                one.rename(one.with_name(one.name.replace(PLACEHOLDER, name)))
        _floor(coming / MANIFEST)
        read(coming)                  # it installs, or nothing is left claiming to
    except BaseException:
        # **A scaffold that failed leaves nothing**, not a hidden half-written directory
        # somebody finds weeks later and cannot explain. Caught broadly and re-raised: what
        # went wrong is the caller's to report, and cleaning up is not a decision.
        shutil.rmtree(coming, ignore_errors=True)
        raise
    os.replace(coming, at)
    return at


def _floor(page: Path) -> None:
    """Declare the rundesk this plugin was actually started against.

    **A template cannot carry a real floor, and a made-up one is worse than none.** The
    version shipped in the file is whatever was current the day somebody wrote it, so it is
    either already stale or — as it was on the first draft — a version that does not exist
    yet, which made `plugins init` produce a plugin `plugins install` refused on the very
    next line. Written here, from the running version, it is true when it is written and its
    author is the one who decides when to raise it.
    """
    from rundesk import __version__
    try:
        said = json.loads(page.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    said.setdefault("requires", {})["rundesk"] = f">={__version__}"
    page.write_text(json.dumps(said, indent=2) + "\n", encoding="utf-8")


def _renamed_inside(at: Path, name: str) -> None:
    """The template's own word for itself, swapped for this plugin's, in both casings.

    **The upper case is not just `.upper()`.** A name may carry hyphens and an environment
    variable may not, so `weather-eu` has to become `WEATHER_EU` — and the draft that did
    the obvious thing produced `WEATHER-EU_TOKEN`, which is not a name any shell can export.
    `read` refused it, so `plugins init` failed for every hyphenated name there is.
    """
    try:
        text = at.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    shouted = name.upper().replace("-", "_")
    swapped = text.replace(PLACEHOLDER.upper(), shouted).replace(PLACEHOLDER, name)
    if swapped != text:
        at.write_text(swapped, encoding="utf-8")


def take_back(where: Path | None = None, scripts_dir: Path | None = None,
              skills_dir: Path | None = None) -> list:
    """Pull every plugin's links on the way out, and say which went.

    An uninstall takes the program; a purge takes the data. What must not survive either is
    a command on every agent's PATH pointing at a directory that is no longer there.
    """
    where = where or home()
    gone = []
    for name, one in sorted(installed(where).items()):
        unlink(one.manifest, one.at, scripts_dir, skills_dir)
        gone.append(name)
    return gone
