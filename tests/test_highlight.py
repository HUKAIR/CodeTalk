import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.highlight import segments, MIN_SPAN


def _cit(i, vb):
    return {"id": i, "verbatim": vb}


class TestSegments(unittest.TestCase):
    def test_verbatim_hit_segments_concat_to_answer(self):
        ans = "模型综合:这是一段真实原话内容,以及别的话"
        segs = segments(ans, [_cit(0, "这是一段真实原话内容")])
        self.assertEqual("".join(s["text"] for s in segs), ans)   # 拼接===answer
        hot = [s for s in segs if s["cite_id"] == 0]
        self.assertTrue(any("这是一段真实原话内容" in s["text"] for s in hot))

    def test_scaffolding_not_matched_redline(self):
        # 脚手架词不在 verbatim → 不高亮(只匹配纯原话,守 R6)
        segs = segments("从测试场景反推设计了重试", [_cit(0, "用显式循环重试")])
        self.assertEqual(segs, [])                                # 「重试」<MIN_SPAN、脚手架不在 verbatim

    def test_short_below_min_span_filtered(self):
        self.assertEqual(segments("abc 重试 def", [_cit(0, "重试")]), [])

    def test_paraphrase_no_overlap_empty(self):
        self.assertEqual(segments("完全不同的综合表述方式", [_cit(0, "另一段毫不相干的原话")]), [])

    def test_overlap_deterministic_non_overlapping(self):
        ans = "AAABBBCCCDDDEEE 公共逐字片段 尾"
        segs = segments(ans, [_cit(0, "公共逐字片段"), _cit(1, "公共逐字片段")])
        self.assertEqual("".join(s["text"] for s in segs), ans)
        hot = [s for s in segs if s["cite_id"] is not None]
        # 互不重叠 + 命中段归一个确定来源(tie-break:cite 0 先)
        self.assertTrue(hot and all(s["cite_id"] == 0 for s in hot))

    def test_empty_and_none(self):
        self.assertEqual(segments("", [_cit(0, "x" * 10)]), [])
        self.assertEqual(segments(None, [_cit(0, "x" * 10)]), [])
        self.assertEqual(segments("有内容但无引用", []), [])

    def test_autojunk_false_long_evidence(self):
        vb = ("重复段落 " * 60) + "唯一可命中的逐字尾巴片段"
        ans = "答案里嵌入 唯一可命中的逐字尾巴片段 收尾"
        segs = segments(ans, [_cit(0, vb)])
        self.assertTrue(any(s["cite_id"] == 0 for s in segs))     # autojunk=False 不丢
