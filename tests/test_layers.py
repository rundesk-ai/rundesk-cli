"""The direction the tree points, checked rather than remembered.

    commands → lifecycle → core → utils

Four layers, and every import crosses that line one way. The rule is written down in `AGENTS.md` and
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
import unittest
from pathlib import Path

import support

#: Which package may import which. `utils` is absent from every list on purpose.
MAY_IMPORT = {
    "utils": (),
    "core": ("utils",),
    "lifecycle": ("core", "utils"),
    "commands": ("lifecycle", "core", "utils"),
}

#: Below the layers rather than in them: the version this is, and what a command may exit with.
#: Constants with no behaviour, which is why importing one cannot invert anything — but `utils` is
#: held to the stricter rule and may not reach even these.
UNDERNEATH = ("rundesk", "rundesk.exits")

WHERE = support.CHECKOUT / "src" / "rundesk"


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


def modules_of(package: str):
    """Every module in one package, so a file added to it is checked the day it lands."""
    return sorted((WHERE / package).rglob("*.py"))


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

    def test_nothing_below_commands_knows_what_argparse_is(self):
        # The command line is one layer's business. A lifecycle module taking a `Namespace` would be
        # a module that cannot be driven except by typing at it.
        for package in ("utils", "core", "lifecycle"):
            for module in modules_of(package):
                with self.subTest(module=f"{package}/{module.name}"):
                    self.assertNotIn("argparse", module.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
