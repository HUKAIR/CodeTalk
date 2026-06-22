import tempfile, unittest
import unittest.mock
from pathlib import Path
from vibetrace import report


class TestUsageLogRedacted(unittest.TestCase):
    """M0 红线:usage.log 落盘前对 secret 脱敏(此前是唯一未脱敏的落盘点)。"""

    def test_secret_in_record_redacted_on_disk(self):
        with tempfile.TemporaryDirectory() as t:
            log = Path(t) / "usage.log"
            with unittest.mock.patch.object(report, "USAGE_LOG_PATH", log):
                report.append_usage({"project": "/x", "note": "key sk-abcdef0123456789ABCD"})
            content = log.read_text(encoding="utf-8")
            self.assertIn("[REDACTED]", content)
            self.assertNotIn("sk-abcdef0123456789ABCD", content)


if __name__ == "__main__":
    unittest.main()
