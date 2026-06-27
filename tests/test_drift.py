"""drift_rows 纯函数:AI 工具动作(files_written)vs 高置信对齐提交 → 写了未提交。"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace.drift import drift_rows  # noqa: E402

_DT = datetime(2026, 6, 27, 12, 0, 0)


class TestDriftRows(unittest.TestCase):
    def test_written_not_committed_flagged(self):
        sess = [{"session_id": "s1", "files_written": {"/proj/a.py", "/proj/b.py"},
                 "start": _DT, "end": _DT}]
        commits = [{"sha": "x" * 40, "date": _DT, "files": ["a.py"]}]
        rows = drift_rows(commits, sess, "/proj")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["written"], 2)
        self.assertEqual(r["committed"], 1)
        self.assertEqual(r["missing"], ["b.py"])       # b.py 写了没提交(最硬信号)

    def test_all_committed_no_missing(self):
        sess = [{"session_id": "s1", "files_written": {"/proj/a.py"}, "start": _DT, "end": _DT}]
        commits = [{"sha": "y" * 40, "date": _DT, "files": ["a.py"]}]
        rows = drift_rows(commits, sess, "/proj")
        self.assertEqual(rows[0]["missing"], [])

    def test_no_files_written_session_skipped(self):
        sess = [{"session_id": "empty", "files_written": set(), "start": _DT, "end": _DT}]
        rows = drift_rows([{"sha": "z" * 40, "date": _DT, "files": ["a.py"]}], sess, "/proj")
        self.assertEqual(rows, [])

    def test_exclude_drops_noise(self):
        # exclude(如 .git/ 内部 / gitignore 命中)从 files_written 剔除,不计偏差
        sess = [{"session_id": "s1", "files_written": {"/proj/a.py", "/proj/.git/X"},
                 "start": _DT, "end": _DT}]
        commits = [{"sha": "x" * 40, "date": _DT, "files": ["a.py"]}]
        rows = drift_rows(commits, sess, "/proj", exclude={".git/X"})
        self.assertEqual(rows[0]["written"], 1)        # .git/X 被排除
        self.assertEqual(rows[0]["missing"], [])       # 只剩 a.py、已提交

    def test_out_of_window_not_high_conf_counts_as_missing(self):
        # 提交在会话时间窗外(±30min 之外)→ 非 high 置信 → 不计入「已提交」→ 写了的都算 missing
        sess = [{"session_id": "s1", "files_written": {"/proj/a.py"}, "start": _DT, "end": _DT}]
        commits = [{"sha": "w" * 40, "date": _DT + timedelta(hours=5), "files": ["a.py"]}]
        rows = drift_rows(commits, sess, "/proj")
        self.assertEqual(rows[0]["missing"], ["a.py"])


if __name__ == "__main__":
    unittest.main()
