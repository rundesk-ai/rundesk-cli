"""The direction the tree points, checked rather than remembered.

    commands  →  lifecycle  ─┐
              →  gateways   ─┤ →  schedules  ─┐
              →  skills     ─┴───────────────┴→  agents  →  core  →  utils

Seven layers, and every import crosses those lines one way.

`agents` sits below several of them because each reaches down to it for a different reason: an
install migration step may have to carry every agent, a gateway is always the gateway *of* an agent,
a grant lands inside an agent's own home, and a schedule is a row in an agent's own records.
Neither reaches back up, and an agent knows nothing about the process that hosts it — which is what
lets one be made, listed and taken away with no gateway anywhere near the case. The rule is written down in `AGENTS.md` and
in each package's own docstring, and written down is where a rule of this kind stops being true:
nothing goes red when somebody adds the import that inverts it, and the first symptom is a module
nobody can test on its own six months later.

So the imports are read off the modules themselves, with `ast` rather than by running anything — a
walk that imported the tree to inspect it would be a walk that a cycle could hang.

**`utils` is the strict one.** It may import the standard library and its own siblings, and *nothing*
else of this product's — not `paths`, not `config`, not even `exits`. That is the whole membership
rule for the bottom layer, and keeping it mechanical is what stops it becoming the place domain logic
accumulates because it is the file everybody already imports.

Run directly: `python3 tests/test_layers.py`
"""

import ast
import hashlib
import re
import unittest
from pathlib import Path

import support

#: Which package may import which. `utils` is absent from every list on purpose.
MAY_IMPORT = {
    "utils": (),
    "core": ("utils",),
    "agents": ("core", "utils"),
    # `schedules` reaches `agents` because a schedule is a row in one agent's own records and a
    # firing's lock stands in that agent's own directory. It may not reach `gateways`, and that is
    # the direction that matters: **when a schedule is due is a different question from what starts
    # it**, so the arithmetic and the store are answerable by a case with no supervisor, no launchd
    # and no child process anywhere near it.
    "schedules": ("agents", "core", "utils"),
    # `delegations` reaches `agents` because a delegation is a row in one agent's own records, and
    # keeps the same distance from `providers` that `schedules` keeps from `gateways`: **what has
    # been handed over is a different question from what runs it**, so the store and the guards are
    # answerable by a case with no brain and no subprocess anywhere near them.
    "delegations": ("agents", "core", "utils"),
    # `capabilities` is the one package below `commands` that may **not** reach `agents`, and the
    # restriction is the mechanical statement of what it is for: *a grant belongs to a machine, not
    # to an install's agents.* Two gateway shims differing only in the agent they name were measured
    # to be one TCC client, so a module that had to be told which agent was asking would be
    # answering a question nobody can ask. Which agent a process was started for is passed in by
    # `commands`, which may reach both.
    "capabilities": ("core", "utils"),
    # `channels` reaches `agents` for the same reason and keeps the same distance from `gateways`:
    # what a channel *is* — a row in one agent's records, a directory in that agent's own tree — is
    # a different question from what hosts one, and the module that answered both could not be
    # driven by a case with no supervisor and no child process anywhere near it.
    "channels": ("agents", "core", "utils"),
    # `providers` reaches `channels` because a turn's answer is a message in the store `arriving`
    # already owns, cut to the platform's limit by `delivery` and vetted by `files` — three things
    # with one home each, and a second copy of any of them is a second answer that can disagree.
    # It reaches `skills` for one thing: **where an agent's granted skills stand**, which a turn has
    # to tell an adapter and which is `skills`' own to know. Every measured brain discovers skills
    # for itself and each reads a directory of its own, so what is presented and where is the
    # adapter's business — but *where they are* is not something a provider may guess at, and a
    # second copy of that path is a second thing to keep in step with the grants that make it.
    # **The traffic goes one way only**: neither `channels` nor `skills` may reach here, so `hosting`
    # is handed an object exactly as `firing` is handed a `Starting`, and every channel case stays
    # drivable by a test with no brain, no adapter and no subprocess anywhere near it.
    # It reaches `schedules` for the other half of the same seam: a scheduled turn has to know what
    # its schedule asked, and `firing` publishes a `Starting` and takes an object of it exactly as
    # `hosting` publishes an `Answering`. Neither may reach here, which is what keeps "when is this
    # due" and "what does a brain cost" two questions with two answers.
    "providers": ("skills", "channels", "schedules", "agents", "core", "utils"),
    # And `gateways` reaches `schedules` rather than the other way round, because the gateway is
    # what turns "this is due" into work that has started. It is the only long-lived process this
    # product has, so it is the only thing that can hold a child and reap it.
    # It reaches `skills` for one thing: **what an agent may do right now**, so it can say when that
    # changes. A grant is an entry in the agent's own directory and nothing reports itself when one
    # appears — a command, a catalog update that retires one, a catalog removal, a link somebody made
    # by hand, and a change made while this process was not running are five ways in and only one of
    # them could ever have told a gateway. So the directory is watched, and `grants.held` is the one
    # answer to what is in it: it is what decides that a dotfile is not a grant and that a copy being
    # staged under `.<name>.incoming` is not one either. A listing written in this layer instead
    # would announce a half-copied alias as granted and revoke it a second later. The traffic goes
    # one way only — `skills` may not reach here, so a grant is still something that can be made,
    # listed and revoked by code that has never heard of a gateway.
    "gateways": ("skills", "providers", "channels", "schedules", "delegations", "agents",
                 "core", "utils"),
    "lifecycle": ("agents", "core", "utils"),
    # `skills` reaches `agents` because a grant is a directory entry inside an agent's own home and
    # there is nowhere else to ask where that is. The traffic goes one way only: `agents` may not
    # reach here, so an agent is still something that can be made, carried and removed by code that
    # has never heard of a skill, and presenting a new agent's skills is done in `commands`.
    "skills": ("agents", "core", "utils"),
    # `commands` reaches `capabilities` and is the **only** package that does. That is what makes
    # the restriction below it enforceable: `capabilities` may not import `gateways` or `agents`, so
    # the shim prefix a lineage is recognised by and the agent a process was started for are
    # resolved here, where both are legal, and handed down as arguments.
    "commands": ("skills", "providers", "channels", "schedules", "delegations", "gateways",
                 "capabilities", "lifecycle", "agents", "core", "utils"),
}

#: Below the layers rather than in them: the version this is, and what a command may exit with.
#: Constants with no behaviour, which is why importing one cannot invert anything — but `utils` is
#: held to the stricter rule and may not reach even these.
UNDERNEATH = ("rundesk", "rundesk.exits")

WHERE = support.CHECKOUT / "src" / "rundesk"

AGENT_GUIDE_HEADINGS = [
    "# AGENTS",
    "## Purpose",
    "## Before you work",
    "## Repository layout",
    "## Package and artifact contract",
    "## Safety and approval gates",
    "## Delegation",
    "## Architecture and conventions",
    "## Documentation duties",
    "## Build, test, and run",
    "## Pull requests and releases",
    "## Definition of done",
]

PR_TEMPLATE_HEADINGS = [
    "## Summary",
    "## Scope and compatibility",
    "## Critical risk",
    "## Validation",
    "## Repository gates",
    "## Release",
    "## Manual user path",
    "## Agent",
]

PR_TEMPLATE_ANCHORS = [
    "- [ ] `python3 scripts/suites` passes on a current Python.",
    "- [ ] `/usr/bin/python3 scripts/suites` passes on the Python 3.9 floor.",
    "- [ ] `ruff check src tests scripts/suites rundesk`",
    "- [ ] Required GitHub checks pass for the exact head commit.",
    "- [ ] The diff contains no credential, private URL, customer data, owner-specific path, debug output, or unrelated artifact.",
    "- [ ] Commands report only earned outcomes and expose no operation that is not implemented.",
    "- [ ] Layer direction remains `commands` → `lifecycle` → `core` → `utils`; `utils` remains product-agnostic.",
    "- [ ] The live `~/.rundesk` install is exactly as it was before validation.",
    "🤖 by <Agent>",
]

ISSUE_TEMPLATE_HEADINGS = {
    "bug-report.md": [
        "## Problem", "## Reproduction", "## Expected behavior", "## Evidence",
        "## Environment", "## Scope and privacy",
    ],
    "change-proposal.md": [
        "## Problem", "## Desired outcome", "## Users and value",
        "## Scope and compatibility", "## Alternatives", "## Validation",
    ],
}

ISSUE_TEMPLATE_FRONTMATTER = {
    "bug-report.md": [
        "---", "name: Bug report", "about: Report reproducible incorrect behavior",
        'title: "[Bug] "', 'labels: ""', 'assignees: ""', "---",
    ],
    "change-proposal.md": [
        "---", "name: Change proposal",
        "about: Propose a skill, integration, command, or repository improvement",
        'title: "[Proposal] "', 'labels: ""', 'assignees: ""', "---",
    ],
}

ISSUE_TEMPLATE_DIGESTS = {
    "bug-report.md": "747da5c0682a73adc61c35407327fb174c648630e80278c275af4a4542da6caf",
    "change-proposal.md": "2fe6a1d651ce91af2c3d19e98eea150ca26f41ad9a1ed95a6466a692b73eb4d7",
}

SUPPORTED_CATALOG_URLS = [
    "https://github.com/rundesk-ai/rundesk-skills",
    "https://github.com/rundesk-ai/rundesk-skills-apple",
    "https://github.com/rundesk-ai/rundesk-skills-integrations",
    "https://github.com/rundesk-ai/rundesk-skills-google",
    "https://github.com/rundesk-ai/rundesk-skills-gamedev",
    "https://github.com/rundesk-ai/desk-cli",
]

#: Standard library names a module in `utils/` might plausibly be given. Not the whole library —
#: nobody is going to write `utils/xml.py` — just the ones that describe what a shared module here
#: does, which is exactly why they are the dangerous ones.
TEMPTING = {
    "logging", "types", "typing", "select", "signal", "platform", "io", "os", "time", "json",
    "copy", "string", "secrets", "queue", "socket", "shutil", "subprocess", "tempfile", "uuid",
    "hashlib", "random", "operator", "stat", "pathlib", "textwrap", "locale", "code", "token",
}


def imports(module: Path):
    """Every `rundesk.*` name this module imports, read off the source rather than by running it."""
    found = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"), str(module))):
        if isinstance(node, ast.Import):
            found.update(one.name for one in node.names if one.name.split(".")[0] == "rundesk")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.split(".")[0] == "rundesk":
                found.add(node.module)
    return found


def reaches_for(module: Path, held_in: str, called: str):
    """Every line in `module` that really calls `held_in.called`, ignoring prose that names it.

    A module that explains in its own docstring why it must not reach for something would fail a
    search of its text, so the only way to pass would be to delete the explanation. Asked of the
    tree instead: this finds the attribute access and nothing that merely spells it.
    """
    said = ast.parse(module.read_text(encoding="utf-8"))
    return [one.lineno for one in ast.walk(said)
            if isinstance(one, ast.Attribute) and one.attr == called
            and isinstance(one.value, ast.Name) and one.value.id == held_in]


def modules_of(package: str):
    """Every module in one package, however deep, so a file added to it is checked the day it lands.

    Deliberately recursive: a migration step is arbitrary code that ships in this tree, and the layer
    rule applies to it exactly as it does to anything else here.
    """
    return sorted((WHERE / package).rglob("*.py"))


def named_in(package: str):
    """The modules a package's table is expected to name: its own, and not what is nested below it.

    A `steps/` directory is documented as a directory — one row, with a trailing slash the table
    checker's own pattern deliberately does not match — because its contents are found rather than
    listed and naming them would be a second list to keep in step with the first.

    Split out from `modules_of` the moment the first step shipped: the recursive walk counted
    `steps/0001_….py` as a module the table had failed to mention, which would have forced either a
    row per step for ever or an exception carved into the checker. Both are worse than saying which
    question is being asked.
    """
    return sorted((WHERE / package).glob("*.py"))


class TheTreePointsOneWay(support.Isolated):
    """Every import in every layer, checked against what that layer may reach."""

    def test_there_is_something_to_check(self):
        # A check that discovers its own work fails when it discovers none: a walk pointed at a
        # directory that had moved would otherwise pass having read nothing.
        for package in MAY_IMPORT:
            with self.subTest(package=package):
                self.assertTrue(modules_of(package), f"no modules found in {package}/")

    def test_no_layer_imports_one_above_it(self):
        for package, allowed in MAY_IMPORT.items():
            reachable = {f"rundesk.{one}" for one in allowed} | set(UNDERNEATH)
            reachable.add(f"rundesk.{package}")
            for module in modules_of(package):
                for name in imports(module):
                    with self.subTest(module=module.name, imports=name):
                        below = ".".join(name.split(".")[:2])
                        self.assertIn(
                            below, reachable,
                            f"{module.relative_to(WHERE)} imports {name}, which {package}/ may not "
                            f"reach — the tree points commands → lifecycle → core → utils")

    def test_utils_reaches_for_nothing_of_this_products_outside_itself(self):
        # Stated as its own case as well as covered by the walk above, because it is the rule that
        # keeps the bottom layer reusable: a util that reached for `paths` or `config` would be a
        # util holding this product's domain under a name that promises common functionality.
        #
        # One util may use another — `table` measures a cell with `style`, because once a cell can
        # carry escape sequences `len()` stops answering how wide it looks. That is still the bottom
        # layer talking to itself, and it takes on no domain. What is forbidden is reaching *up*.
        for module in modules_of("utils"):
            beyond = {name for name in imports(module)
                      if name.split(".")[:2] != ["rundesk", "utils"]}
            with self.subTest(module=module.name):
                self.assertEqual(set(), beyond,
                                 f"{module.name} reaches outside utils — the bottom layer is the "
                                 "standard library and its own siblings, and nothing else")

    def test_nothing_in_skills_reads_a_credentials_value(self):
        # `secrets.value` is the one way a whole value leaves that module, and it exists for the
        # programs rundesk starts — an adapter reaching for its own token. Everything in `skills/`
        # is a listing, a readout or a diagnosis, and none of those is one of those programs.
        #
        # Checked mechanically rather than left as a rule, for the same reason the layer walk is:
        # this is a boundary somebody would cross while doing something that felt reasonable, and
        # the failure — a token in a table, in a log, in a terminal somebody screen-shared — is not
        # one anybody notices from a green suite.
        # Asked of the syntax tree rather than of the text, because these modules *describe* the
        # rule in their own docstrings — a substring check reads that prose as a violation and the
        # only way to keep it quiet is to stop writing down why the rule exists.
        for module in modules_of("skills"):
            with self.subTest(module=module.name):
                self.assertEqual(
                    [], reaches_for(module, "secrets", "value"),
                    f"{module.name} reads a credential's value — ask `secrets.placed` whether it "
                    "is set instead")

    def test_every_kind_the_skills_layer_raises_is_caught_by_the_command_layer(self):
        # `grants.NotPresented` is deliberately outside `TROUBLE`, so that a caller can answer it
        # separately. The cost of that choice is that a verb which does not name it does not catch it
        # *at all* — and one did not, so an ordinary `rundesk skills revoke` under lock contention
        # reached a person as a traceback rather than a refusal.
        #
        # So the rule is not "kept apart" but "caught somehow": named in `TROUBLE`, or given an
        # `except` of its own. Checked mechanically because the failure is silent — nothing goes red,
        # the verb simply crashes in a state nothing tests for, and "did I check every caller of what
        # raises this" is a grep a person forgets.
        said = (WHERE / "commands" / "skills.py").read_text(encoding="utf-8")
        raises = (WHERE / "skills" / "grants.py").read_text(encoding="utf-8")
        trouble = said.split("TROUBLE = (")[1].split(")")[0]
        for name in ("NotPresented", "HalfCopied", "Occupied"):
            with self.subTest(kind=name):
                self.assertIn(f"class {name}(", raises, f"grants.{name} has gone")
                caught = (f"grants.{name}" in trouble) or (f"except grants.{name}" in said)
                self.assertTrue(caught,
                                f"nothing in commands/skills.py catches grants.{name} — it is "
                                "neither in TROUBLE nor given an `except` of its own, so any verb "
                                "reaching it crashes instead of refusing")

    def test_only_the_gateway_process_itself_reaches_the_skills_layer(self):
        # The table is per package, so letting `host` watch what an agent may do lets `standing` and
        # `job` reach `skills` too — and neither should. `standing` is what every command asks about
        # liveness through, and `job` is what hands a gateway to launchd; a skill has nothing to do
        # with either, and an import there would make "is this gateway up" a question that reads a
        # catalog. The edge was opened for one loop, and this is what keeps it that wide.
        for one in modules_of("gateways"):
            if one.name == "host.py":
                continue
            with self.subTest(module=one.name):
                self.assertNotIn("rundesk.skills", imports(one),
                                 f"gateways/{one.name} reaches the skills layer — that edge was "
                                 "opened for host.py's own loop and nothing else")

    def test_the_agents_verb_catches_every_kind_granting_a_skill_can_raise(self):
        # `agents add` gives a new agent the skill it operates this install with, which puts a
        # second layer's exceptions in front of a verb whose own `TROUBLE` names none of them. The
        # guard above reads only `commands/skills.py`, so it would never have seen this — and the
        # failure is the same silent one: the agent is already made and renamed into place by then,
        # so an unguarded kind reaches a person as a traceback out of a command that succeeded.
        said = (WHERE / "commands" / "agents.py").read_text(encoding="utf-8")
        granting = said.split("GRANTING_TROUBLE = (")[1].split(")")[0]
        # **That the tuple is caught, not merely written.** Measured: replacing the `except` with a
        # narrower one left this case green, because a list of names nothing catches reads exactly
        # like a list of names something does.
        self.assertIn("except GRANTING_TROUBLE", said,
                      "GRANTING_TROUBLE is declared and nothing catches it")
        for name in ("library.Refused", "grants.Refused", "grants.NotPresented",
                     "grants.HalfCopied"):
            with self.subTest(kind=name):
                caught = (name in granting) or (f"except {name}" in said)
                self.assertTrue(caught,
                                f"nothing in commands/agents.py catches {name} — giving a new "
                                "agent its skill can raise it, and the agent exists by then")
        # And it stays out of what fails the verb: a grant that could not be made must never report
        # that nothing happened, which sends somebody to make an agent that is already there.
        trouble = said.split("TROUBLE = (")[1].split(")")[0]
        self.assertNotIn("grants.", trouble)
        self.assertNotIn("library.", trouble)

    def test_every_kind_the_schedules_layer_raises_is_caught_by_the_command_layer(self):
        # The same rule `skills` is held to, and it is here because the same thing already went
        # wrong there: a kind kept out of `TROUBLE` so a verb could answer it separately is a kind
        # the verbs that *do not* name it do not catch at all, and one of them reached a person as
        # a traceback rather than a refusal.
        #
        # `Occupied` and `NoRunner` are deliberately outside `TROUBLE` — `run` answers each with a
        # sentence of its own — so the rule is "caught somehow" rather than "named in the tuple".
        said = (WHERE / "commands" / "schedules.py").read_text(encoding="utf-8")
        trouble = said.split("TROUBLE = (")[1].split(")")[0]
        for module, kinds in (("kept", ("Refused",)),
                              ("due", ("NotASchedule",)),
                              ("firing", ("Occupied", "NoRunner"))):
            raises = (WHERE / "schedules" / f"{module}.py").read_text(encoding="utf-8")
            for name in kinds:
                with self.subTest(kind=f"{module}.{name}"):
                    self.assertIn(f"class {name}(", raises, f"{module}.{name} has gone")
                    caught = (f"{module}.{name}" in trouble) or (f"except {module}.{name}" in said)
                    self.assertTrue(caught,
                                    f"nothing in commands/schedules.py catches {module}.{name} — "
                                    "it is neither in TROUBLE nor given an `except` of its own, so "
                                    "any verb reaching it crashes instead of refusing")

    def test_every_package_table_names_what_is_in_its_directory(self):
        # `utils` was checked and `core` was not, so `core`'s table went on listing a module that
        # had moved a whole layer down and nothing said a word. A table a reader trusts is a table
        # worth checking — all of them, not the one that happened to get a test first.
        for package in ("agents", "capabilities", "channels", "core", "gateways", "lifecycle",
                        "providers", "schedules", "skills", "utils"):
            table = (WHERE / package / "__init__.py").read_text(encoding="utf-8")
            # A trailing slash names a directory rather than a module — `steps/` is
            # documented deliberately and has no `.py` of its own to match.
            named = set(re.findall(r"^\| `(\w+)` \|", table, re.M))
            there = {one.stem for one in named_in(package) if one.stem != "__init__"}
            with self.subTest(package=package):
                self.assertTrue(named, f"{package}/__init__.py names no modules at all")
                self.assertEqual(there, named,
                                 f"the table in {package}/__init__.py and the directory disagree")

    def test_the_two_layers_spell_a_gateway_s_own_files_the_same_way(self):
        # `agents` may not import `gateways`, and `gateways.standing` deliberately never derives
        # where an agent lives — so neither can share these constants with the other, and the
        # duplication is the layer boundary being kept clean rather than something to remove.
        #
        # It is not free, though. `directory.forgotten` deletes an agent's lock and record BY NAME,
        # so a rename on one side and not the other would leave both behind on every removal —
        # silently, and exactly the class of litter `records.beside` exists to prevent for `-wal`
        # and `-shm`. Nothing enforced that they match until this case.
        from rundesk.agents import directory
        from rundesk.gateways import standing
        self.assertEqual(standing.LOCK, directory.GATEWAY_LOCK)
        self.assertEqual(standing.RECORD, directory.GATEWAY_RECORD)
        self.assertEqual(standing.LOGS, directory.LOGS)

    def test_the_files_an_agent_lives_by_are_spelled_the_same_way_everywhere(self):
        # Two layers name these files and neither may import the other to ask. `agents.pages` writes
        # them and `providers.environment` tells every adapter what changing one is called. One of
        # them was already wrong: `LIVES_BY` named a `SOUL.md` no release had ever placed, so an edit
        # to one would have been reported as `identity` on a machine where nothing could make one.
        #
        # A name in `LIVES_BY` is a promise the file is really given, so that is the direction
        # checked. `CLAUDE.md` is placed and is not classified separately because it is the same
        # bytes as `AGENTS.md`. Standing rules are loaded by each provider under its native name;
        # the operating prompt identifies that layer without reopening or restating any home file.
        from rundesk.agents import pages
        from rundesk.providers import environment, instructions
        self.assertTrue(pages.PAGES, "agents.pages places nothing at all")
        self.assertEqual(set(), set(environment.LIVES_BY) - set(pages.PAGES),
                         "providers.environment classifies an edit to a file no release places")
        for page in pages.PAGES:
            self.assertNotIn(page, instructions.CORE)

    def test_a_step_is_still_held_to_the_layer_rule(self):
        # `named_in` stops at the package's own modules so a step does not have to be listed in a
        # table. `modules_of` must not: a step is arbitrary code shipping in this tree, it runs
        # against somebody's real data, and it is the last place to relax a rule. Asserted rather
        # than assumed, because the two walks now differ and nothing else would notice if the
        # recursive one quietly stopped recursing.
        stepped = [one for one in modules_of("agents") if one.parent.name == "steps"]
        self.assertTrue(stepped, "no agent migration step was found to check")
        self.assertNotIn(stepped[0], named_in("agents"))

    def test_every_module_in_utils_is_named_in_its_table(self):
        # The table in `utils/__init__.py` is what a reader trusts to know what is down there, and
        # it is the first thing that goes stale: it had already fallen a module behind by the time
        # anybody noticed. Checked rather than remembered, and it fails on an empty walk too.
        table = (WHERE / "utils" / "__init__.py").read_text(encoding="utf-8")
        named = set(re.findall(r"^\| `(\w+)` \|", table, re.M))
        self.assertTrue(named, "the table in utils/__init__.py names nothing at all")
        there = {one.stem for one in modules_of("utils") if one.stem != "__init__"}
        self.assertEqual(there, named,
                         "the table in utils/__init__.py and the directory disagree")

    def test_nothing_in_utils_takes_a_name_the_standard_library_has(self):
        # ruff catches a shadowed builtin and cannot catch a shadowed module. A `utils/logging.py`
        # is imported in preference to the real one by anything inside this package, and the failure
        # is baffling because the name is right.
        #
        # Written out rather than asked of `sys.stdlib_module_names`, which arrived in 3.10 and this
        # runs on 3.9 — the floor caught that on the first run of this very case. These are the names
        # a module down here might plausibly be given, which is the whole risk worth checking.
        taken = {one.stem for one in modules_of("utils")} & TEMPTING
        self.assertEqual(set(), taken, f"{taken} shadows a standard library module")

    def test_nothing_below_commands_knows_what_argparse_is(self):
        # The command line is one layer's business. A lifecycle module taking a `Namespace` would be
        # a module that cannot be driven except by typing at it.
        for package in ("utils", "core", "agents", "channels", "gateways", "lifecycle",
                        "providers", "schedules"):
            for module in modules_of(package):
                with self.subTest(module=f"{package}/{module.name}"):
                    self.assertNotIn("argparse", module.read_text(encoding="utf-8"))


class TheTwoLayersSpellADelegationTheSameWay(support.Isolated):
    """`channels` may not import `delegations`, so the conversation a delegated turn stands in is
    spelled in both. Compared here rather than left to agree by hand — the symptom of drift is an
    answer written into a conversation nobody is reading, which nothing else would notice."""

    def test_the_source_word_is_the_same_in_both(self):
        from rundesk.channels import arriving
        from rundesk.delegations import kept
        self.assertEqual(arriving.FROM_AGENT, kept.FROM_AGENT)

    def test_the_conversation_key_is_built_the_same_way_in_both(self):
        import sqlite3

        from rundesk.agents import directory, records
        from rundesk.channels import arriving
        from rundesk.core import paths
        from rundesk.delegations import kept
        paths.agents().mkdir(parents=True, exist_ok=True)
        directory.made("bob", "a-stand-in")
        landed = arriving.recorded_for_a_delegation("bob", "ava", 12, "audit it")
        with records.reading(directory.records("bob")) as conn:
            conn.row_factory = sqlite3.Row
            stood = conn.execute("SELECT source, source_id FROM conversations WHERE id = ?",
                                 (landed.conversation,)).fetchone()
        self.assertEqual((kept.FROM_AGENT, kept.source_id_for("ava", 12)),
                         (stood["source"], stood["source_id"]))


class AgentGuideContract(unittest.TestCase):
    def test_guides_are_identical_and_keep_the_required_heading_order(self):
        agents = (support.CHECKOUT / "AGENTS.md").read_bytes()
        claude = (support.CHECKOUT / "CLAUDE.md").read_bytes()

        self.assertEqual(agents, claude, "AGENTS.md and CLAUDE.md must be byte-identical")
        headings = [
            line for line in agents.decode("utf-8").splitlines()
            if re.match(r"^#{1,2} ", line)
        ]
        self.assertEqual(AGENT_GUIDE_HEADINGS, headings)
        self.assertIn(b"./dev status", agents)
        self.assertNotIn(b'RUNDESK_HOME="$(mktemp -d)" ./dev status', agents)

    def test_repository_templates_keep_the_required_heading_order(self):
        pull_request = (support.CHECKOUT / ".github" / "pull_request_template.md").read_text(
            encoding="utf-8")
        self.assertEqual(
            PR_TEMPLATE_HEADINGS,
            [line for line in pull_request.splitlines() if line.startswith("## ")])
        for anchor in PR_TEMPLATE_ANCHORS:
            with self.subTest(pull_request_anchor=anchor):
                self.assertIn(anchor, pull_request)
        issue_root = support.CHECKOUT / ".github" / "ISSUE_TEMPLATE"
        self.assertEqual(
            set(ISSUE_TEMPLATE_HEADINGS) | {"config.yml"},
            {path.name for path in issue_root.iterdir() if path.is_file()})
        self.assertEqual(
            b"blank_issues_enabled: false\n",
            (issue_root / "config.yml").read_bytes())
        for name, expected in ISSUE_TEMPLATE_HEADINGS.items():
            with self.subTest(template=name):
                issue_bytes = (issue_root / name).read_bytes()
                issue = issue_bytes.decode("utf-8")
                self.assertEqual(
                    ISSUE_TEMPLATE_DIGESTS[name],
                    hashlib.sha256(issue_bytes).hexdigest())
                self.assertEqual(ISSUE_TEMPLATE_FRONTMATTER[name], issue.splitlines()[:7])
                self.assertEqual(
                    expected,
                    [line for line in issue.splitlines() if line.startswith("## ")])

    def test_readme_and_docs_index_link_the_catalog_guide(self):
        for path in (support.CHECKOUT / "README.md", support.CHECKOUT / "docs" / "README.md"):
            with self.subTest(path=path.name):
                self.assertIn("docs/catalogs.md" if path.name == "README.md"
                              and path.parent == support.CHECKOUT else "catalogs.md",
                              path.read_text(encoding="utf-8"))

    def test_catalog_guide_preserves_the_license_contract(self):
        guide = (support.CHECKOUT / "docs" / "catalogs.md").read_text(encoding="utf-8")
        for required in (
            "├── LICENSE                        required repository license",
            "├── THIRD_PARTY_NOTICES.md         only when adapted work requires attribution",
            "the upstream license and required notices",
            "Never remove or weaken an upstream",
        ):
            with self.subTest(required=required):
                self.assertIn(required, guide)

    def test_readme_lists_every_supported_first_party_catalog(self):
        readme = (support.CHECKOUT / "README.md").read_text(encoding="utf-8")
        directory = readme.split("#### Supported first-party catalogs", 1)[1].split(
            "The skills under this repository's `src/skills/`", 1)[0]
        for url in SUPPORTED_CATALOG_URLS:
            with self.subTest(url=url):
                self.assertIn(url, directory)

    def test_readme_shell_examples_have_no_angle_bracket_metavariables(self):
        readme = (support.CHECKOUT / "README.md").read_text(encoding="utf-8")
        shell_blocks = re.findall(r"^```(?:sh|bash)\n(.*?)^```", readme, re.M | re.S)
        self.assertTrue(shell_blocks, "README.md contains no shell example to check")
        for block in shell_blocks:
            with self.subTest(block=block.splitlines()[0] if block.splitlines() else ""):
                self.assertIsNone(re.search(r"<[^>\n]+>", block))


if __name__ == "__main__":
    unittest.main()
