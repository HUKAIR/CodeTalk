"""ADR 导出:真实决策史 → MADR/Nygard markdown,逐字引真实 commit、出口脱敏。零 LLM。"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codetalk import adr_export
from codetalk.adr_export import to_adr
from codetalk.cache import Cache


def _git(a, c):
    subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)


_SEG = [{"sha": "abc1234" + "0" * 33, "date": "2026-06-01T08:00", "subject": "用乐观锁",
         "why": "为了避免写超时", "decisions": ["放弃悲观锁,改版本号 CAS"],
         "risks": ["高并发下重试风暴待验证"], "evidence": [], "test_refs": [], "pr_refs": []}]


class TestToAdr(unittest.TestCase):
    def test_madr_structure_and_verbatim_source(self):
        out = to_adr("f.py:1-5", _SEG, "madr")
        self.assertIn("## Context and Problem Statement", out)
        self.assertIn("为了避免写超时", out)                 # why → Context(逐字)
        self.assertIn("放弃悲观锁,改版本号 CAS", out)        # decision → Decision(逐字)
        self.assertIn("高并发下重试风暴待验证", out)          # risk → Consequences
        self.assertIn("[abc1234]", out)                      # 来源:真实 commit SHA
        self.assertIn("f.py:1-5", out)                       # 目标

    def test_rejected_renders_considered_options(self):
        seg = [{"sha": "f" * 40, "date": "2026-06-27T08:00", "subject": "走文本归因",
                "why": "", "decisions": ["文本归因闸"],
                "rejected": ["全局 history 无 cwd 泄露其他仓"],
                "risks": [], "evidence": []}]
        out = to_adr("f.py:1-3", seg, "madr")
        self.assertIn("Considered Options", out)               # 否决备选 → Considered Options 段
        self.assertIn("全局 history 无 cwd 泄露其他仓", out)    # 逐字
        self.assertIn("(否决)", out)                           # 来源段每 commit 否决锚点

    def test_no_rejected_omits_considered_options(self):
        out = to_adr("f.py:1-5", _SEG, "madr")                 # _SEG 无 rejected
        self.assertNotIn("Considered Options", out)            # 不撑空节

    def test_nygard_format(self):
        out = to_adr("f.py", _SEG, "nygard")
        self.assertIn("## Status", out)
        self.assertIn("accepted", out)
        self.assertIn("## Decision", out)
        self.assertNotIn("Context and Problem Statement", out)  # 这是 MADR 段名,nygard 不应有

    def test_no_segments_falls_back(self):
        out = to_adr("x.py", [], "madr")
        self.assertIn("无叙事", out)                          # 空也出友好 ADR 骨架,不崩

    def test_redaction(self):
        seg = [{"sha": "e" * 40, "date": "d", "subject": "s",
                "why": "key sk-abcdefghijklmnop1234 别泄漏", "decisions": [],
                "risks": []}]
        out = to_adr("f", seg, "madr")
        self.assertNotIn("sk-abcdefghijklmnop1234", out)
        self.assertIn("[REDACTED]", out)


class TestCycloneDxFormat(unittest.TestCase):
    """CycloneDX 1.5 BOM-Format 子集——把决策史接到 AIBOM 生态。"""

    def test_valid_json_with_required_base_fields(self):
        out = to_adr("f.py:1-5", _SEG, "cyclonedx")
        bom = json.loads(out)                           # 必须是合法 JSON
        self.assertEqual(bom["bomFormat"], "CycloneDX")
        self.assertEqual(bom["specVersion"], "1.5")
        self.assertIn("serialNumber", bom)
        self.assertIn("metadata", bom)
        self.assertIn("components", bom)

    def test_each_commit_becomes_component_with_verbatim_decisions(self):
        out = to_adr("f.py:1-5", _SEG, "cyclonedx")
        bom = json.loads(out)
        self.assertEqual(len(bom["components"]), 1)
        comp = bom["components"][0]
        self.assertEqual(comp["bom-ref"], _SEG[0]["sha"])
        self.assertEqual(comp["name"], "用乐观锁")        # subject → name
        self.assertEqual(comp["description"], "为了避免写超时")  # why → description
        # decisions/risks 进 properties(逐字)
        prop_values = [p["value"] for p in comp["properties"]]
        self.assertIn("放弃悲观锁,改版本号 CAS", prop_values)
        self.assertIn("高并发下重试风暴待验证", prop_values)

    def test_reproducible_no_timestamp_drift(self):
        """同一 target/segments 输出必须字节级一致(timestamp 取自最新 commit,不用 now())。"""
        a = to_adr("f.py:1-5", _SEG, "cyclonedx")
        b = to_adr("f.py:1-5", _SEG, "cyclonedx")
        self.assertEqual(a, b)

    def test_redaction_in_cyclonedx(self):
        seg = [{"sha": "e" * 40, "date": "2026-06-01T08:00", "subject": "s",
                "why": "key sk-abcdefghijklmnop1234 别泄漏",
                "decisions": [], "risks": []}]
        out = to_adr("f", seg, "cyclonedx")
        self.assertNotIn("sk-abcdefghijklmnop1234", out)
        self.assertIn("[REDACTED]", out)

    def test_redaction_quote_delimited_secret(self):
        # 回归守门:JSON 路径须在 dumps 前脱敏。key="value" 形式 secret 经 dumps
        # 引号转义后,若先 dumps 后 redact 会漏过(cache.py:88 记录的坑)。
        seg = [{"sha": "d" * 40, "date": "2026-06-01T08:00", "subject": "s",
                "why": "", "decisions": ['set password="hunter2abcXYZ" here'],
                "rejected": [], "risks": []}]
        out = to_adr("f", seg, "cyclonedx")
        self.assertNotIn("hunter2abcXYZ", out)
        self.assertIn("[REDACTED]", out)
        json.loads(out)                                 # 仍合法 JSON

    def test_serialnumber_is_valid_uuid(self):
        import uuid
        bom = json.loads(to_adr("f.py:1-5", _SEG, "cyclonedx"))
        sn = bom["serialNumber"]
        self.assertTrue(sn.startswith("urn:uuid:"))
        uuid.UUID(sn[len("urn:uuid:"):])                # 非法 UUID 会抛 → 守门 hyphen 修复

    def test_tools_use_non_deprecated_components_form(self):
        # legacy tools[] 不允许 description 字段(schema additionalProperties:false);
        # 用 1.5 的 {components:[...]} 形态既带 description 又过官方 schema 校验。
        bom = json.loads(to_adr("f.py:1-5", _SEG, "cyclonedx"))
        tools = bom["metadata"]["tools"]
        self.assertIsInstance(tools, dict)              # 非 legacy 数组
        self.assertIn("components", tools)
        self.assertEqual(tools["components"][0]["description"],
                         "zero-LLM commit decision provenance")

    def test_empty_segments_emits_valid_bom(self):
        out = to_adr("x.py", [], "cyclonedx")
        bom = json.loads(out)
        self.assertEqual(bom["components"], [])         # 空但合法


class TestExportOnRepo(unittest.TestCase):
    def test_export_grounds_to_real_commit(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("x = 1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", "feat: 初版\n\nVibe-Decision: 选三行布局便于演示"], d)
        db = str(Path(d) / "cache.db")
        with mock.patch("codetalk.config.CACHE_DB_PATH", db):
            out, err = adr_export.export(d, "a.py", fmt="madr")
        self.assertIsNone(err)
        self.assertIn("选三行布局便于演示", out)              # 逐字引真实 Vibe-Decision
        self.assertIn("## Decision Outcome", out)


if __name__ == "__main__":
    unittest.main()
