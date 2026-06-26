import subprocess
import unittest
from unittest import mock

from vibetrace import filetree


class TestLabel(unittest.TestCase):
    def test_codes_map_deterministically(self):
        cases = {
            " M": "已修改", "M ": "已暂存·已修改", "??": "未跟踪",
            "A ": "已暂存·新增", " D": "已删除", "D ": "已暂存·已删除",
            "R ": "已暂存·重命名", "C ": "已暂存·复制", "MM": "已暂存·已修改",
            "AM": "已暂存·新增", "MD": "已删除", "UU": "冲突",
        }
        for code, want in cases.items():
            self.assertEqual(filetree.label(code), want, code)

    def test_unknown_code_does_not_crash(self):
        self.assertEqual(filetree.label("ZZ"), "ZZ")     # 原样 code,不崩


class TestStatus(unittest.TestCase):
    def _raw(self, s):
        return mock.patch.object(filetree.gitlog, "_git", return_value=s)

    def test_parses_codes_and_paths(self):
        with self._raw(" M a.py\x00?? b.py\x00"):
            out = filetree.status("/x")
        self.assertEqual(out, [
            {"path": "a.py", "code": " M", "label": "已修改"},
            {"path": "b.py", "code": "??", "label": "未跟踪"},
        ])

    def test_rename_consumes_oldpath_segment(self):
        with self._raw("R  new.py\x00old.py\x00"):
            out = filetree.status("/x")
        self.assertEqual([e["path"] for e in out], ["new.py"])  # old.py 被消费,不单独成项
        self.assertEqual(out[0]["code"], "R ")

    def test_skips_empty_and_trailing_slash(self):
        with self._raw("?? keep.py\x00?? folded/\x00\x00"):
            out = filetree.status("/x")
        self.assertEqual([e["path"] for e in out], ["keep.py"])  # 尾斜杠条目 + 空段丢弃

    def test_passes_untracked_all_flag(self):
        with mock.patch.object(filetree.gitlog, "_git", return_value="") as g:
            filetree.status("/x")
        args = g.call_args[0][0]
        self.assertIn("--porcelain=v1", args)
        self.assertIn("--untracked-files=all", args)
        self.assertIn("-z", args)

    def test_git_failure_returns_empty(self):
        with mock.patch.object(filetree.gitlog, "_git",
                               side_effect=RuntimeError("not a git repo")):
            self.assertEqual(filetree.status("/x"), [])


class TestBuildTree(unittest.TestCase):
    def test_nests_and_bubbles_changed(self):
        paths = ["a/b.py", "a/c.py", "d.py"]
        sm = {"a/b.py": {"code": " M", "label": "已修改"}}
        root = filetree.build_tree(paths, sm)
        self.assertEqual(root["type"], "dir")
        names = [c["name"] for c in root["children"]]
        self.assertEqual(names, ["a", "d.py"])          # 目录在前、字典序
        a = root["children"][0]
        self.assertTrue(a["changed"])                   # b.py 变更 → 祖先 a changed
        b = next(c for c in a["children"] if c["name"] == "b.py")
        self.assertEqual(b["code"], " M")
        c = next(c for c in a["children"] if c["name"] == "c.py")
        self.assertNotIn("code", c)                     # 未变更文件无 code
        self.assertFalse(root["children"][1].get("changed", False))

    def test_deleted_file_node_present(self):
        root = filetree.build_tree(["x.py"], {"x.py": {"code": " D", "label": "已删除"}})
        self.assertEqual(root["children"][0]["code"], " D")
        self.assertTrue(root["changed"])

    def test_empty_input(self):
        root = filetree.build_tree([], {})
        self.assertEqual(root["children"], [])
        self.assertFalse(root["changed"])

    def test_large_input_no_crash(self):
        paths = ["d%d/f%d.py" % (i // 50, i) for i in range(5000)]
        root = filetree.build_tree(paths, {})
        leaves = []
        stack = [root]
        while stack:
            n = stack.pop()
            if n["type"] == "file":
                leaves.append(n)
            else:
                stack.extend(n["children"])
        self.assertEqual(len(leaves), 5000)


if __name__ == "__main__":
    unittest.main()
