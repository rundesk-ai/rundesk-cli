"""What a skill says it needs, which profiles it has, and whether each of them is whole.

A skill that talks to something outside this machine needs credentials, and the build this replaces
had nowhere for it to say so. An owner found out a token was missing when a turn failed, at whatever
hour the schedule ran, and the only clue was a program's own error message.

So a skill may stand a `rundesk.json` beside its `SKILL.md`, and it has exactly one key:

    { "needs": { "JIRA_API_TOKEN": "an API token from id.atlassian.com" } }

A map of environment variable to **why it is needed**. That one field drives the install preview, the
guided `configure`, which profiles exist, every listing and every `doctor` verdict. A skill with no
`rundesk.json` declares nothing, needs nothing, and is never reported as blocked.

Everything else a format like this could carry was considered and left out. `optional` — declare what
is required, and a value a script uses if it happens to be there is the skill's own business.
A list of scripts — they are found by walking `scripts/`, and a list is a second thing to keep in
step with a directory. Per-script needs — one declaration per skill, because two granularities is two
ways to be inconsistent for precision nobody asked for. The whole contract is one optional file with
one field, which is the amount somebody can still hold in their head in a year.

## A profile is a whole set of values, not a suffix on one

Three Jira sites is the case that decides the shape. A Jira account is not one credential — it is a
URL, an address and a token, and they **only mean anything together**. A profile is therefore a named
set covering every value the skill declares, and this module reasons about it as a unit.

    JIRA_BASE_URL__ACME   JIRA_EMAIL__ACME   JIRA_API_TOKEN__ACME    -> profile "acme"
    JIRA_BASE_URL__BETA   JIRA_EMAIL__BETA   JIRA_API_TOKEN__BETA    -> profile "beta"
    JIRA_BASE_URL         JIRA_EMAIL         JIRA_API_TOKEN          -> the default profile

**Profiles are found, not declared.** The set of them is the suffixes standing on the names a skill
declares, so adding a fourth site needs no edit to the skill, to its catalog, or to any configuration
— and `core.secrets` is not modified by any of this, because a profile is a naming convention on
names `rundesk env set` already accepts.

**A named profile never falls back to a plain value, and that is the safety property this module
exists to hold.** Falling back is how `JIRA_BASE_URL__ACME` comes to be paired with the default
`JIRA_API_TOKEN`, and a turn then authenticates against one company's site with another's token. A
profile carries all of its own values or it is reported incomplete. Nothing here has a code path that
mixes two.

## Nothing here reads a value

Whether a name holds something usable is asked of `secrets.placed()`, which answers yes or no.
`secrets.value()` exists for the programs rundesk starts, and a listing, a readout and a diagnosis
are none of those. `tests/test_layers.py` checks that rather than trusting it.

## What is deliberately not here

**The environment a skill's own commands are handed.** Nothing in this release starts a provider, so
there is no turn to hand one to, and building the injector now would be a function with no caller
written against a shape nothing had tested. What this module answers is the part that can be
answered honestly today: what a skill says it needs, and which of it this install has.
`docs/research/` records the contract the change that builds providers will implement, so that it is
written down before it is depended on rather than after.
"""

import re
import stat
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

from rundesk.core import secrets
from rundesk.skills import library
from rundesk.utils import files

#: What a skill stands beside its `SKILL.md` to say what it needs. Optional, and most skills have
#: none — a skill that only tells an agent how to do something needs nothing from anybody.
WANTS = "rundesk.json"

#: What separates a name from the profile it belongs to. Two underscores rather than one, because a
#: single one is ordinary inside a name and `JIRA_API_TOKEN` would then appear to be `JIRA_API` in a
#: profile called `TOKEN`.
BETWEEN = "__"

#: What a profile may be called: the same alphabet the rest of a name uses, since the two are joined
#: into one environment variable and `secrets` refuses anything else.
CALLED = re.compile(r"^[A-Z][A-Z0-9_]*$")

#: How the default profile is shown. It has no name — it is the plain, unsuffixed set — and a blank
#: cell in a table reads as missing data rather than as an answer.
DEFAULT_SHOWN = "(default)"


class Refused(Exception):
    """Something a skill declared that cannot be used, named with why."""


class Need(NamedTuple):
    """One value a skill needs, and why it needs it.

    `about` is carried everywhere this goes. It is what turns `JIRA_BASE_URL` from a name somebody
    has to guess at into an instruction they can follow, and it is the one thing an agent reading a
    diagnosis has that tells it what the integration actually is.
    """

    env: str
    about: str


class Profile(NamedTuple):
    """One named set of values for one skill, and how much of it is there.

    `name` is `""` for the default — the plain, unsuffixed set.

    **`exists` and `whole` are different questions and both are asked.** A profile nobody has
    started is not a broken one, and a profile with two of its three values is not an absent one:
    the first is ordinary and the second is the thing somebody has to be told about, at the hour
    they are not looking.
    """

    name: str
    exists: bool
    whole: bool
    missing: List[str]

    @property
    def shown(self) -> str:
        """How this profile is written for a person: lowercase, or the word for having no name."""
        return self.name.lower() if self.name else DEFAULT_SHOWN


def declared(at: Path) -> List[Need]:
    """What the skill standing at `at` says it needs. Empty when it says nothing.

    **In the order the author wrote them, not in name order.** `configure` asks for them in this
    order, and somebody setting up a Jira site expects to be asked for the site, then the account,
    then the token — which is the order a person writes them in and is not the order they sort in.
    Deterministic either way, because a JSON object keeps its order; sorting only replaced the
    author's judgement with the alphabet.

    Refused when the file is there and cannot be used, rather than read as declaring nothing. A
    `rundesk.json` somebody has mistyped is the case where saying "this skill needs nothing" is
    exactly wrong — it needs something, and the thing that was supposed to say so is broken.
    """
    where = at / WANTS
    how, said = files.read_json(where)
    if how == files.MISSING:
        return []
    if how == files.UNREADABLE:
        raise Refused(f"{where} is there and is not readable JSON")
    if not isinstance(said, dict):
        raise Refused(f"{where} holds {type(said).__name__}, and it must be an object")

    wanted = said.get("needs", {})
    if not isinstance(wanted, dict):
        raise Refused(f"{where} must map each environment variable to why it is needed")
    settled = []
    for env in wanted:
        about = wanted[env]
        if not isinstance(about, str) or not about.strip():
            raise Refused(f"{where} gives no reason for {env} — say what it is and where to get it")
        trouble = name_trouble(env)
        if trouble:
            raise Refused(f"{where} declares {env!r}, and {trouble}")
        settled.append(Need(env, about.strip()))
    return settled


def trouble_with(at: Path) -> str:
    """Why what the skill at `at` declares cannot be used, or `""` when it can.

    The sentence form of `declared`, for the callers that are checking rather than reading — an
    install validating a whole catalog, and a diagnosis reporting on one skill.
    """
    try:
        declared(at)
    except Refused as why:
        return str(why)
    return ""


def name_trouble(env: str) -> str:
    """Why `env` may not be a name a skill declares, or `""` when it may.

    Everything `secrets` refuses, plus the one this adds: a declared name may not itself contain the
    profile separator. `JIRA_TOKEN__ACME` declared as a need would be indistinguishable from the
    `ACME` profile of a need called `JIRA_TOKEN`, and every profile this install found from then on
    would be one somebody had not made.
    """
    trouble = secrets.name_trouble(env)
    if trouble:
        return trouble
    if BETWEEN in env:
        return (f"a declared name cannot contain {BETWEEN} — that is how a profile is written, and "
                f"{env} would read as a profile of something else")
    return ""


def profile_trouble(said: str) -> str:
    """Why `said` may not name a profile, or `""` when it may."""
    if not said or not said.strip():
        return "a profile needs a name"
    if not CALLED.match(as_named(said)):
        return (f"{said} is not a name a profile can have — letters, digits and underscores, "
                "starting with a letter, such as acme. It is joined onto each value's own name, so "
                "it has to be something a program can be given")
    return ""


def as_named(profile: str) -> str:
    """A profile as it appears inside an environment variable.

    Upper case, because that is what the name it joins is and `secrets` refuses anything else. So
    `acme` and `ACME` are one profile rather than two that look alike, which is the answer somebody
    typing a command expects and the only one that cannot produce a second half-configured set.
    """
    return profile.strip().upper()


def named(env: str, profile: str) -> str:
    """The environment variable holding `env` for `profile`. The plain name for the default."""
    return f"{env}{BETWEEN}{as_named(profile)}" if profile else env


def profiles(needs: List[Need], at: Optional[Path] = None) -> List[str]:
    """Every profile these needs have values under, in name order. The default is not among them.

    **Found rather than declared.** The set is whatever suffixes are standing on the names this
    skill declares, so a fourth account is four `rundesk env set` lines and nothing else — no edit
    to the skill, its catalog, or any configuration on this machine.
    """
    found = set()
    standing = secrets.names(at)
    for need in needs:
        start = need.env + BETWEEN
        found.update(one[len(start):] for one in standing
                     if one.startswith(start) and CALLED.match(one[len(start):] or ""))
    return sorted(found)


def standing(needs: List[Need], profile: str = "", at: Optional[Path] = None) -> Profile:
    """How much of one profile is there.

    **No fallback, ever.** A value missing from a named profile is missing, and is never answered
    from the plain unsuffixed name. That rule is the whole reason this module reasons about a set
    rather than about one variable at a time: falling back is how a site's own URL comes to be used
    with another site's token, and the request succeeds against the wrong company.
    """
    missing = [named(one.env, profile) for one in needs
               if not secrets.placed(named(one.env, profile), at)]
    return Profile(as_named(profile) if profile else "", len(missing) < len(needs), not missing,
                   missing)


def every(needs: List[Need], at: Optional[Path] = None) -> List[Profile]:
    """The default profile and every named one, in the order a person reads them.

    The default comes first because it is the one a skill with a single account uses, and the named
    ones follow in name order. All of them are returned including those nobody has started, so a
    caller showing what is configured and a caller showing what could be are the same call.
    """
    if not needs:
        return []
    return [standing(needs, "", at)] + [standing(needs, one, at) for one in profiles(needs, at)]


def usable(needs: List[Need], at: Optional[Path] = None) -> List[Profile]:
    """The profiles that exist and are whole — the ones a turn could really use right now."""
    return [one for one in every(needs, at) if one.exists and one.whole]


class Script(NamedTuple):
    """One command a skill ships, and whether the machine would run it.

    `runnable` is the executable bit. To an agent a script that is present and not executable looks
    exactly like one that works, right up until it tries — so it is asked here rather than
    discovered by a turn failing.
    """

    at: Path
    runnable: bool

    @property
    def shown(self) -> str:
        """How this script is named in the skill's own terms, rather than by its whole path."""
        return f"{library.SCRIPTS}/{self.at.name}"


def ships(at: Path) -> List[Script]:
    """Every command the skill at `at` ships, in name order. Found rather than listed.

    Only what stands directly in `scripts/`. Anything deeper is something a command of its own
    reaches for — a library, a template, a fixture — and offering those as commands would be this
    telling an agent to run files nobody meant to be run.
    """
    where = at / library.SCRIPTS
    if not where.is_dir():
        return []
    return [Script(one, bool(one.stat().st_mode & stat.S_IXUSR))
            for one in sorted(where.iterdir(), key=lambda entry: entry.name)
            if one.is_file() and not one.name.startswith(".")]


def about(needs: List[Need]) -> Dict[str, str]:
    """Each declared name and why it is needed, for a caller that has a name and wants the sentence."""
    return {one.env: one.about for one in needs}


def env_trouble(where: Path) -> str:
    """Why the skill directory at `where` cannot be used at all, or `""` when it can.

    Both halves in one answer — the `SKILL.md` and the declaration beside it — because a caller
    checking a skill is checking whether it is usable, and a skill whose credentials nobody can
    parse is as unusable as one no brain will load. Kept here rather than in `library` because
    `library` has no reason to know what a credential is.
    """
    return library.trouble_with(where) or trouble_with(where)
