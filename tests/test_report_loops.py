import unittest
from datetime import datetime, timezone

from vibetrace import report

_STATS = {"commits": 1, "sessions": 0, "cache_hits": 0, "llm_calls": 1,
          "tokens_in": 0, "tokens_out": 0, "model": "m", "elapsed_s": 0.1}


def _commit(open_loops):
    return {"sha": "abc1234def", "subject": "s",
            "date": datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
            "narrative": {"what": "w", "why": "y", "decisions": [],
                          "risks": [], "open_loops": open_loops},
            "matches": []}


class TestReportDropsFillerLoops(unittest.TestCase):
    def test_insufficient_material_and_blank_dropped(self):
        out = report.render("P", "2026-06-19", "ov",
                            [_commit(["真问题", "材料不足,xxx", "  "])],
                            [], None, _STATS)
        self.assertIn("真问题", out)
        self.assertNotIn("材料不足", out)   # 与 brief recent_open_loops 同口径

    def test_risks_section_drops_filler(self):
        cm = _commit([])                       # open_loops 为空
        cm["narrative"]["risks"] = ["真风险", "材料不足以判断"]
        out = report.render("P", "2026-06-19", "ov", [cm], [], None, _STATS)
        self.assertIn("真风险", out)
        self.assertNotIn("材料不足", out)     # 风险段同样滤掉填充


if __name__ == "__main__":
    unittest.main()
