# tests/test_cursor_sessions.py
import json, sqlite3, tempfile, unittest
import unittest.mock
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

def make_global(user_dir, composer_id, bubbles, created=1000):
    """造 globalStorage/state.vscdb : composerData + 若干 bubbleId 行。
    bubbles: [(type, text, createdAt, [files])]。"""
    g = Path(user_dir) / "globalStorage"; g.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(g / "state.vscdb")
    con.execute("CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?,?)",
                (f"composerData:{composer_id}", json.dumps({"createdAt": created, "text": ""})))
    for i, (typ, text, ts, files) in enumerate(bubbles):
        con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?,?)",
                    (f"bubbleId:{composer_id}:b{i}",
                     json.dumps({"type": typ, "text": text, "createdAt": ts,
                                 "relevantFiles": files})))
    con.commit(); con.close()
    return g / "state.vscdb"

class TestParseComposer(unittest.TestCase):
    def test_maps_bubbles_to_prompts_excerpts_files_ts(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            root = Path(t) / "repo"; root.mkdir()
            db = make_global(user, "cid", [
                (1, "为什么用乐观锁", 1000, ["a.py"]),
                (2, "因为实现简单可靠,且 " + "x" * 400, 2000, ["a.py", "b.py"]),
            ])
            con = cs._open_ro(db)
            s = cs._parse_composer(con, "cid", root); con.close()
            self.assertEqual(s["session_id"], "cid")
            self.assertEqual(s["prompts"], ["为什么用乐观锁"])
            self.assertEqual(len(s["excerpts"]), 1)
            self.assertLessEqual(len(s["excerpts"][0]), cs.EXCERPT_CAP)
            self.assertEqual(s["files_written"], {str(root / "a.py"), str(root / "b.py")})
            self.assertEqual(s["start"].year, cs._ms(1000).year)
            self.assertTrue(s["start"] < s["end"])

    def test_secret_in_bubble_is_redacted(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir(); root = Path(t) / "r"; root.mkdir()
            db = make_global(user, "c", [(1, "key sk-abcdef0123456789ABCD here", 5, [])])
            con = cs._open_ro(db); s = cs._parse_composer(con, "c", root); con.close()
            self.assertIn("[REDACTED]", s["prompts"][0])
            self.assertNotIn("sk-abcdef0123456789ABCD", s["prompts"][0])

from vibetrace.cache import Cache

class TestScanSessions(unittest.TestCase):
    def _setup(self, t):
        user = Path(t) / "User"; user.mkdir()
        proj = Path(t) / "repo"; proj.mkdir()
        make_workspace(user, proj, ["cid"])
        make_global(user, "cid", [(1, "问题", 1000, ["a.py"]),
                                  (2, "回答" + "y" * 90, 2000, ["a.py"])])
        return user, proj

    def test_scan_returns_session_for_project(self):
        with tempfile.TemporaryDirectory() as t:
            user, proj = self._setup(t)
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertIsNone(err)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["session_id"], "cid")
            self.assertIn("files_written", out[0])

    def test_no_cursor_dir_degrades(self):
        with unittest.mock.patch.object(cs, "_USER_DIRS",
                                        [Path("/nonexistent/x")]):
            out, err = cs.scan_sessions("/tmp/whatever", None, None)
        self.assertEqual(out, [])
        self.assertIsNotNone(err)

    def test_cache_incremental_hit(self):
        with tempfile.TemporaryDirectory() as t:
            user, proj = self._setup(t)
            cache = Cache(":memory:")
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                cs.scan_sessions(proj, None, cache)          # 首次写缓存
                hit = cache.get_session("cid")
                self.assertIsNotNone(hit)
                out2, _ = cs.scan_sessions(proj, None, cache)  # 二次命中
            self.assertEqual(len(out2), 1)

if __name__ == "__main__":
    unittest.main()
