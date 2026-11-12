"""The visual comparison must preserve real Git lines, never fabricate file state."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node is needed for the browser helper check")
class ReadingDiffCase(unittest.TestCase):
    def test_sides_preserve_headers_context_and_missing_newline_marker(self):
        source = Path(__file__).resolve().parents[1] / "codetalk/reading-room-actions.js"
        code = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const scope = {document:{addEventListener(){}}};
vm.createContext(scope);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), scope);
const diff = '--- a/example.py\n+++ b/example.py\n@@ -1,2 +1,2 @@\n context\n-old <tag>\n+new & text\n\\ No newline at end of file';
const result = scope.roomDiffSides(diff);
assert.equal(result.before, '--- a/example.py\n+++ b/example.py\n@@ -1,2 +1,2 @@\n context\n-old <tag>\n\\ No newline at end of file');
assert.equal(result.after, '--- a/example.py\n+++ b/example.py\n@@ -1,2 +1,2 @@\n context\n+new & text\n\\ No newline at end of file');
assert.equal(scope.roomDiffSides('').before, '');
assert.equal(scope.roomDiffSides('').after, '');
'''
        result = subprocess.run([shutil.which("node"), "-e", code, str(source)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
