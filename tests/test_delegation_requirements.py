"""The delegation requirements matrix cites evidence the current suite can find.

Run directly: ``python3 tests/test_delegation_requirements.py``
"""

import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs" / "requirements" / "agent-delegation.md"


class CurrentEvidence(unittest.TestCase):

    def test_every_completed_requirement_names_current_test_evidence(self):
        available = set()
        for path in (ROOT / "tests").glob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            available.update(
                node.name for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            )

        completed = []
        for line in MATRIX.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\| ✅ \| (R-DEL-\d+) \|.*\| (.*) \|$", line)
            if match is None:
                continue
            requirement, evidence = match.groups()
            cited = re.findall(r"`([^`]+)`", evidence)
            self.assertTrue(cited, f"{requirement} cites no test evidence")
            self.assertTrue(
                all(name.startswith("test_") for name in cited),
                f"{requirement} carries historical prose instead of exact test names",
            )
            missing = sorted(set(cited) - available)
            self.assertEqual([], missing, f"{requirement} cites tests that do not exist")
            completed.append(requirement)

        self.assertTrue(completed, "the matrix contained no completed delegation requirements")


if __name__ == "__main__":
    unittest.main()
