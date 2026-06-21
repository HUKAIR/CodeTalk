import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from vibetrace import self_report


def _line(command, days_ago=0, **extra):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return json.dumps({"command": command, "ts": ts, **extra}, ensure_ascii=False)


class TestParse(unittest.TestCase):
    def test_skips_bad_lines(self):
        lines = ["not json", "", "  ", _line("brief"), '{"no_ts": 1}']
        recs = self_report.parse_lines(lines)
        # 仅一条合法(brief 带 command+ts);坏行/缺 ts 跳过,不崩
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["command"], "brief")

    def test_filter_by_days(self):
        lines = [_line("brief", days_ago=1), _line("ask", days_ago=30)]
        recs = self_report.parse_lines(lines)
        kept = self_report.within_days(recs, 7)
        self.assertEqual([r["command"] for r in kept], ["brief"])


class TestAggregate(unittest.TestCase):
    def test_command_counts_and_llm_savings(self):
        recs = self_report.parse_lines([
            _line("brief"),
            _line("brief"),
            _line("graph", cache_hits=2),
            _line("ask", llm_calls=1, tokens_in=100, tokens_out=50,
                  cache_hit_tokens=80),
            _line("digest", llm_calls=3, tokens_in=300, tokens_out=200,
                  cache_hit_tokens=400),
        ])
        agg = self_report.aggregate(recs)
        self.assertEqual(agg["counts"]["brief"], 2)
        self.assertEqual(agg["counts"]["graph"], 1)
        self.assertEqual(agg["total_runs"], 5)
        self.assertEqual(agg["llm_calls"], 4)          # 1 + 3
        self.assertEqual(agg["cache_hit_tokens"], 480)  # 80 + 400
        # 零-LLM 命令次数:没有 llm_calls 字段 / 为 0 的运行(brief x2 + graph)
        self.assertEqual(agg["zero_llm_runs"], 3)

    def test_empty(self):
        agg = self_report.aggregate([])
        self.assertEqual(agg["total_runs"], 0)
        self.assertEqual(agg["llm_calls"], 0)


class TestRender(unittest.TestCase):
    def test_report_mentions_value_without_llm(self):
        recs = self_report.parse_lines([_line("brief"), _line("graph")])
        agg = self_report.aggregate(recs)
        out = self_report.render(agg, days=7, fill=(4, 3))
        self.assertIn("7", out)
        self.assertIn("回填", out)        # 回填率出现
        self.assertIn("brief", out)
        # 零 LLM 仍有价值的自证文案在场
        self.assertIn("零", out)

    def test_empty_report_does_not_crash(self):
        out = self_report.render(self_report.aggregate([]), days=7, fill=(0, 0))
        self.assertIsInstance(out, str)
        self.assertIn("暂无", out)


class TestBuild(unittest.TestCase):
    def test_build_from_missing_log(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "nope.log"
            out = self_report.build_self_report(missing, days=7, fill=(0, 0))
            self.assertIn("暂无", out)

    def test_build_reads_log(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "usage.log"
            log.write_text(_line("brief") + "\n" + _line("ask", llm_calls=1)
                           + "\n" + "garbage\n", encoding="utf-8")
            out = self_report.build_self_report(log, days=7, fill=(2, 1))
            self.assertIn("brief", out)
            self.assertIn("ask", out)


if __name__ == "__main__":
    unittest.main()
