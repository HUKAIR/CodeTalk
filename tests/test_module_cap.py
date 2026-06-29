"""M0 red line: every vibetrace/*.py module must stay under 300 lines.

A single test that walks the package and fails on any violation —
catches cap breaches before they merge, not after."""
import unittest
from pathlib import Path

CAP = 300
PKG = Path(__file__).resolve().parent.parent / "vibetrace"


class TestModuleCap(unittest.TestCase):
    def test_all_modules_under_300_lines(self):
        violations = []
        for py in sorted(PKG.glob("*.py")):
            count = sum(1 for _ in py.open(encoding="utf-8"))
            if count > CAP:
                violations.append(f"{py.name}: {count} lines (cap={CAP})")
        self.assertEqual(violations, [],
                         f"Module(s) over {CAP}-line cap:\n" +
                         "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
