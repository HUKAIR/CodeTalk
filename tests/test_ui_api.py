"""Selected-project URL handling remains idempotent across render and link wiring."""
import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node is needed for the browser helper check")
class ProjectUrlCase(unittest.TestCase):
    def test_query_and_fragment_survive_repeated_project_scoping(self):
        source = Path(__file__).resolve().parents[1] / "codetalk/ui-api.js"
        code = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const scope = {URL, URLSearchParams,
  location: {href: 'http://127.0.0.1/console?project=%2Fsample%20project#timeline', search:'?project=%2Fsample%20project'},
  document: {addEventListener() {}}};
vm.createContext(scope);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), scope);
const once = scope.apiPath('/console?mode=read#timeline');
assert.equal(scope.apiPath(once), once);
const url = new URL(once, scope.location.href);
assert.equal(url.searchParams.get('project'), '/sample project');
assert.equal(url.searchParams.get('mode'), 'read');
assert.equal(url.searchParams.getAll('project').length, 1);
assert.equal(url.hash, '#timeline');
assert.equal(new URL(scope.apiPath('/review?project=/old'), scope.location.href).searchParams.get('project'), '/sample project');
assert.equal(scope.projectPayload({question:'why'}).project, '/sample project');
scope.location = {href:'about:srcdoc',search:''};
scope.document.baseURI = 'http://127.0.0.1/pages/';
assert.equal(scope.apiPath('/console#timeline'), '/console#timeline');
'''
        result = subprocess.run([shutil.which("node"), "-e", code, str(source)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
