"""citation_audit 纯函数单测:逐字引用保真(面包屑对 commit body / evidence 对会话)。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.citation_audit import audit_breadcrumbs, audit_evidence  # noqa: E402


class TestAuditBreadcrumbs(unittest.TestCase):
    def test_verbatim_present(self):
        items = [{"sha": "a1b2c3d",
                  "dec_expected": ["用 urllib 不引三方"], "risk_expected": ["并发待验证"],
                  "decisions": ["LLM 决策 X", "用 urllib 不引三方"], "risks": ["并发待验证"]}]
        r = audit_breadcrumbs(items)
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["verified"], 2)
        self.assertEqual(r["mismatches"], [])

    def test_mismatch_flagged(self):
        items = [{"sha": "deadbee", "dec_expected": ["原话被改写了"], "risk_expected": [],
                  "decisions": ["完全不同的措辞"], "risks": []}]
        r = audit_breadcrumbs(items)
        self.assertEqual(r["verified"], 0)
        self.assertEqual(len(r["mismatches"]), 1)
        self.assertEqual(r["mismatches"][0]["sha"], "deadbee")
        self.assertEqual(r["mismatches"][0]["kind"], "decision")

    def test_watch_checks_risks(self):
        items = [{"sha": "c0ffee0", "dec_expected": [], "risk_expected": ["这条到期回看"],
                  "decisions": [], "risks": ["这条到期回看"]}]
        r = audit_breadcrumbs(items)
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["verified"], 1)

    def test_empty_no_breadcrumbs(self):
        r = audit_breadcrumbs([{"sha": "x", "dec_expected": [], "risk_expected": [],
                                "decisions": ["仅 LLM 决策"], "risks": []}])
        self.assertEqual(r["total"], 0)
        self.assertEqual(r["verified"], 0)


class TestAuditEvidence(unittest.TestCase):
    def test_quote_in_live(self):
        items = [{"sha": "a", "session_id": "s1", "stored": ["怎么把重试改成循环"],
                  "live": ["前文", "怎么把重试改成循环", "后文"]}]
        r = audit_evidence(items)
        self.assertEqual(r["total"], 1)
        self.assertEqual(r["verified"], 1)
        self.assertEqual(r["dangling"], 0)

    def test_truncated_quote_fragments_match(self):
        # head…tail 截断:两段都需在 live 文本中(对 scan 截断鲁棒)
        items = [{"sha": "a", "session_id": "s1", "stored": ["怎么…循环"],
                  "live": ["怎么把重试改成循环"]}]
        r = audit_evidence(items)
        self.assertEqual(r["verified"], 1)

    def test_dangling_when_session_gone(self):
        items = [{"sha": "a", "session_id": "gone", "stored": ["x"], "live": None}]
        r = audit_evidence(items)
        self.assertEqual(r["dangling"], 1)
        self.assertEqual(r["verified"], 0)
        self.assertEqual(r["mismatches"], [])

    def test_mismatch_when_not_in_live(self):
        items = [{"sha": "a", "session_id": "s1", "stored": ["不存在于会话"], "live": ["别的内容"]}]
        r = audit_evidence(items)
        self.assertEqual(r["verified"], 0)
        self.assertEqual(len(r["mismatches"]), 1)


if __name__ == "__main__":
    unittest.main()
