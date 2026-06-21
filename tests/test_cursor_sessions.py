# tests/test_cursor_sessions.py
import json, sqlite3, tempfile, unittest
from pathlib import Path
from urllib.parse import quote
from vibetrace import cursor_sessions as cs

def make_workspace(user_dir, folder_path, composer_ids):
    """造一个 workspaceStorage/<h>/ : workspace.json(folder URI) + state.vscdb(ItemTable)。"""
    ws = Path(user_dir) / "workspaceStorage" / "h1"
    ws.mkdir(parents=True)
    uri = "file://" + quote(str(folder_path))
    (ws / "workspace.json").write_text(json.dumps({"folder": uri}))
    con = sqlite3.connect(ws / "state.vscdb")
    con.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO ItemTable VALUES (?,?)",
                ("composer.composerData",
                 json.dumps({"allComposers": [{"composerId": c} for c in composer_ids]})))
    con.commit(); con.close()
    return ws

class TestAttribution(unittest.TestCase):
    def test_workspace_folder_maps_to_composer_ids(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "myrepo"; proj.mkdir()
            make_workspace(user, proj, ["aaa", "bbb"])
            ids, matched = cs.project_composer_ids(user, proj)
            self.assertTrue(matched)
            self.assertEqual(ids, {"aaa", "bbb"})

    def test_no_matching_workspace_returns_false(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; (user / "workspaceStorage").mkdir(parents=True)
            other = Path(t) / "other"; other.mkdir()
            ids, matched = cs.project_composer_ids(user, other)
            self.assertEqual((ids, matched), (set(), False))

if __name__ == "__main__":
    unittest.main()
