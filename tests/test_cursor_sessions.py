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

def make_global(user_dir, composer_id, bubbles, created=1000, head_text=""):
    """造 globalStorage/state.vscdb : composerData + 若干 bubbleId 行。
    bubbles: [(type, text, createdAt, [files])];head_text=composerData 草稿文本。"""
    g = Path(user_dir) / "globalStorage"; g.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(g / "state.vscdb")
    con.execute("CREATE TABLE IF NOT EXISTS cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?,?)",
                (f"composerData:{composer_id}", json.dumps({"createdAt": created, "text": head_text})))
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
                hit = cache.get_session("cursor:cid")        # 源前缀键,与 Claude 隔离
                self.assertIsNotNone(hit)
                self.assertIsNone(cache.get_session("cid"))  # 旧裸键不再使用
                out2, _ = cs.scan_sessions(proj, None, cache)  # 二次命中
            self.assertEqual(len(out2), 1)

class TestReviewFixes(unittest.TestCase):
    """PR#29 评审发现的修复回归。"""

    def test_title_secret_at_boundary_redacted(self):
        # 无 type==1 提问 → title 取 composerData.text;secret 跨第60字符不得逃过脱敏
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir(); root = Path(t) / "r"; root.mkdir()
            head = "x" * 50 + "sk-ABCDEFGHIJKLMNOP1234567890"
            db = make_global(user, "c", [(2, "ai 回答够长够长够长够长够长够长够长够长", 5, [])],
                             head_text=head)
            con = cs._open_ro(db); s = cs._parse_composer(con, "c", root); con.close()
            self.assertNotIn("sk-ABCDEF", s["title"])   # 旧码(先截断后脱敏)会泄此残片
            self.assertIn("[REDACTED]", s["title"])

    def test_nondict_bubble_does_not_drop_session(self):
        # 一条合法但非对象的 JSON bubble 不应使整条会话丢失
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir(); root = Path(t) / "r"; root.mkdir()
            db = make_global(user, "c", [(1, "真实问题", 1000, [])])
            con = sqlite3.connect(db)   # 注入一条非 dict 的 bubble 值
            con.execute("INSERT INTO cursorDiskKV VALUES (?,?)", ("bubbleId:c:bad", "[]"))
            con.commit(); con.close()
            con = cs._open_ro(db); s = cs._parse_composer(con, "c", root); con.close()
            self.assertEqual(s["prompts"], ["真实问题"])   # 有效 bubble 仍被解析

    def test_blank_summary_has_is_subagent(self):
        self.assertIs(cs._blank_summary("x")["is_subagent"], False)


class TestStringCreatedAt(unittest.TestCase):
    """dogfood 发现:真实 Cursor 数据 createdAt 偶为字符串,scan 不得因类型比较崩/丢会话。"""

    def test_string_createdat_bubble_not_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "repo"; proj.mkdir()
            make_workspace(user, proj, ["cid"])
            make_global(user, "cid", [(1, "为什么", "1763395490552", [])])  # createdAt 是字符串
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertEqual(len(out), 1)            # 字符串 createdAt 不致整条丢失
            self.assertEqual(out[0]["prompts"], ["为什么"])


class TestRealDataTypeHardening(unittest.TestCase):
    """同 createdAt 一类:Cursor 非官方 schema 的字段类型异构不得让整条会话静默丢失
    (对抗审查 sweep 实证可复现的 silent_session_drop)。"""

    def test_nonstr_bubble_text_not_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "repo"; proj.mkdir()
            make_workspace(user, proj, ["cid"])
            make_global(user, "cid", [(1, "正常问题", 1000, []),
                                      (2, {"rich": "x"}, 2000, [])])  # text 为 dict
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertEqual(len(out), 1)            # 非 str text 的 bubble 不拖垮整条会话
            self.assertEqual(out[0]["prompts"], ["正常问题"])

    def test_nonstr_head_text_not_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "repo"; proj.mkdir()
            make_workspace(user, proj, ["cid"])
            # 只有 type2 → prompts 空 → title 兜底读 head.get("text");草稿为 dict
            make_global(user, "cid", [(2, "助手回答", 1000, [])],
                        head_text={"rich": "draft"})
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertEqual(len(out), 1)            # 非 str 草稿不拖垮会话
            self.assertEqual(out[0]["title"], "")    # 降级为空 title

    def test_nondict_composerdata_not_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "repo"; proj.mkdir()
            make_workspace(user, proj, ["cid"])
            db = make_global(user, "cid", [(2, "助手回答", 1000, [])])
            con = sqlite3.connect(db)   # composerData 损坏成非 dict JSON(部分写/版本变)
            con.execute("INSERT OR REPLACE INTO cursorDiskKV VALUES (?,?)",
                        ("composerData:cid", "[1, 2, 3]"))
            con.commit(); con.close()
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertEqual(len(out), 1)            # 非 dict composerData 不拖垮会话

    def test_overflow_string_createdat_not_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            user = Path(t) / "User"; user.mkdir()
            proj = Path(t) / "repo"; proj.mkdir()
            make_workspace(user, proj, ["cid"])
            make_global(user, "cid", [(1, "为什么", "1e400", [])])  # 溢出数字串
            with unittest.mock.patch.object(cs, "_USER_DIRS", [user]):
                out, err = cs.scan_sessions(proj, None, None)
            self.assertEqual(len(out), 1)            # _epoch 按其契约降级为 0,不上抛丢会话
            self.assertEqual(out[0]["prompts"], ["为什么"])


class TestNotice(unittest.TestCase):
    def test_notice_shown_once(self):
        with tempfile.TemporaryDirectory() as t:
            sentinel = Path(t) / ".cursor_notice_shown"
            with unittest.mock.patch.object(cs, "NOTICE_SENTINEL", sentinel):
                self.assertFalse(sentinel.exists())
                cs.maybe_notice()
                self.assertTrue(sentinel.exists())   # 首次创建
                cs.maybe_notice()                    # 第二次不报错、不重复

if __name__ == "__main__":
    unittest.main()
