"""narrative_audit.audit 的单测:文件名保真 ghost 检测 + 降级计数(纯函数,零 IO)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.narrative_audit import audit  # noqa: E402


class TestNarrativeAudit(unittest.TestCase):
    def setUp(self):
        # 全仓历史真实存在的 basename
        self.bases = {"llm.py", "cache.py", "config.py", "README.md"}

    def test_clean_narrative_no_ghost(self):
        narr = {"a1b2c3d": {"why": "改 llm.py 加重试", "decisions": ["config.py 加 provider"]}}
        r = audit(narr, self.bases)
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["clean"], 1)
        self.assertEqual(r["ghost_narr"], 0)
        self.assertEqual(r["degraded"], 0)
        self.assertEqual(r["flags"], [])

    def test_ghost_filename_flagged(self):
        narr = {"deadbee": {"why": "重构 fake_module.py 与 cache.py"}}
        r = audit(narr, self.bases)
        self.assertEqual(r["ghost_narr"], 1)
        self.assertEqual(r["clean"], 0)
        self.assertEqual(len(r["flags"]), 1)
        self.assertEqual(r["flags"][0]["sha"], "deadbee")
        self.assertIn("fake_module.py", r["flags"][0]["ghosts"])
        # 真实文件 cache.py 不应进 ghost 名单
        self.assertNotIn("cache.py", r["flags"][0]["ghosts"])

    def test_degraded_counted_not_ghost(self):
        narr = {"f00ba12": {"why": "材料不足,无法判定", "decisions": [], "risks": []}}
        r = audit(narr, self.bases)
        self.assertEqual(r["degraded"], 1)
        self.assertEqual(r["ghost_narr"], 0)
        self.assertEqual(r["clean"], 1)  # 降级但无 ghost → 文件名保真仍算干净

    def test_degraded_flag_field(self):
        narr = {"abc1234": {"why": "正常", "degraded": True}}
        r = audit(narr, self.bases)
        self.assertEqual(r["degraded"], 1)

    def test_non_dict_narrative_skipped(self):
        narr = {"x": "不是 dict", "abc1234": {"why": "改 llm.py"}}
        r = audit(narr, self.bases)
        self.assertEqual(r["total"], 1)  # 字符串叙事被跳过

    def test_risks_text_scanned_for_ghost(self):
        narr = {"e5e5e5e": {"why": "ok", "risks": ["ghost_risk.ts 可能回归"]}}
        r = audit(narr, self.bases)
        self.assertEqual(r["ghost_narr"], 1)
        self.assertIn("ghost_risk.ts", r["flags"][0]["ghosts"])

    def test_cjk_not_glued_to_extension(self):
        # `\w` 曾把中文粘到尾随扩展名上(「Canvas 2D替代Three.js」→ 一个 token)。
        # 修正后路径体限 ASCII:不应抓出含 CJK 的 ghost。
        narr = {"c1c1c1c": {"decisions": ["用 Canvas 2D替代Three.js,零依赖"]}}
        r = audit(narr, self.bases)
        for f in r["flags"]:
            for g in f["ghosts"]:
                self.assertFalse(any("一" <= ch <= "鿿" for ch in g),
                                 f"ghost token 不应含 CJK:{g}")


if __name__ == "__main__":
    unittest.main()
