"""Explicit authorization and inspectable privacy plan for enrichment."""
import contextlib
import copy
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codetalk import cli
from codetalk.cache import Cache
from codetalk.config import DEFAULTS
from codetalk.enrich_plan import endpoint_details
from codetalk.llm import LLMError


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class RecordingLLM:
    model = "recording-model"

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def narrate(self, prompt, cache_prefix=""):
        self.calls.append({"prompt": prompt, "cache_prefix": cache_prefix})
        if self.fail:
            raise LLMError("recorded failure")
        return {"what": "recorded", "why": "generated interpretation",
                "decisions": [], "risks": [], "open_loops": []}


def _cfg(base_url="https://api.example.test:8443/v1", local_label=False):
    cfg = copy.deepcopy(DEFAULTS)
    cfg.update(provider="test-provider", model="test-model")
    cfg["providers"]["test-provider"] = {
        "base_url": base_url, "api_key": "configured-key",
        "local": local_label,
    }
    return cfg


class TestEnrichAuthorization(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)
        _git(["init", "-q"], self.project)
        _git(["config", "user.email", "private@author.example"], self.project)
        _git(["config", "user.name", "Private Author"], self.project)
        Path(self.project, "client.py").write_text(
            'api_key="Abcd1234Efgh5678"\n', encoding="utf-8")
        _git(["add", "."], self.project)
        _git(["commit", "-q", "-m", "private business rule"], self.project)
        self.sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.project, check=True,
            capture_output=True, text=True).stdout.strip()
        self.db = str(Path(self.project) / "cache.db")

    def _run(self, cfg, *args, llm=None, constructor=None):
        llm = llm or RecordingLLM()
        factory = constructor if constructor is not None else mock.Mock(return_value=llm)
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(cli, "CACHE_DB_PATH", self.db), \
             mock.patch("codetalk.commands.load_config", return_value=cfg), \
             mock.patch("codetalk.commands._scan_sessions", return_value=[]), \
             mock.patch("codetalk.llm.LLMClient", factory), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = cli.main(["enrich", "--project", self.project, *args])
        return rc, stdout.getvalue(), stderr.getvalue(), llm, factory

    def _narrative(self):
        with Cache(self.db) as cache:
            return cache.get_narrative(self.sha)

    def test_configured_remote_key_does_not_authorize_or_construct_client(self):
        forbidden = mock.Mock(side_effect=AssertionError("client constructed"))
        rc, out, _err, _llm, factory = self._run(
            _cfg(local_label=True), constructor=forbidden)

        self.assertEqual(rc, 0)
        factory.assert_not_called()
        self.assertIsNone(self._narrative())
        self.assertIn('"execution": "remote_blocked_no_authorization"', out)
        self.assertIn('"destination_origin": "https://api.example.test:8443"', out)
        self.assertIn('"configured_key_authorizes_remote": false', out)

    def test_payload_preview_is_redacted_local_and_makes_no_model_call(self):
        forbidden = mock.Mock(side_effect=AssertionError("client constructed"))
        rc, out, _err, _llm, factory = self._run(
            _cfg(), "--payload-preview", constructor=forbidden)

        self.assertEqual(rc, 0)
        factory.assert_not_called()
        self.assertIsNone(self._narrative())
        self.assertIn('"outbound_request_preview"', out)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("Abcd1234Efgh5678", out)
        self.assertIn('"named_secret": 1', out)
        self.assertIn('"model_request": false', out)

    def test_explicit_remote_authorization_calls_and_caches(self):
        rc, out, _err, llm, factory = self._run(_cfg(), "--allow-remote")

        self.assertEqual(rc, 0)
        factory.assert_called_once()
        self.assertEqual(len(llm.calls), 1)
        self.assertIsNotNone(self._narrative())
        self.assertIn('"execution": "remote_execution_authorized"', out)
        self.assertNotIn("Abcd1234Efgh5678", json.dumps(llm.calls))

    def test_exact_loopback_runs_without_remote_authorization(self):
        rc, out, _err, llm, factory = self._run(
            _cfg("http://127.0.0.1:11434/v1"))

        self.assertEqual(rc, 0)
        factory.assert_called_once()
        self.assertEqual(len(llm.calls), 1)
        self.assertIn('"execution": "loopback_execution"', out)
        self.assertIn('"network_egress": false', out)

    def test_authorized_failure_does_not_write_generated_narrative(self):
        rc, out, _err, llm, _factory = self._run(
            _cfg(), "--allow-remote", llm=RecordingLLM(fail=True))

        self.assertEqual(rc, 0)
        self.assertEqual(len(llm.calls), 1)
        self.assertIsNone(self._narrative())
        self.assertIn("失败 1", out)

    def test_reenrich_without_authorization_preserves_immutable_cache(self):
        with Cache(self.db) as cache:
            cache.put_narrative(
                self.sha, str(Path(self.project).resolve()), "old-model",
                {"what": "old", "why": "must remain", "decisions": []})
        forbidden = mock.Mock(side_effect=AssertionError("client constructed"))
        rc, out, _err, _llm, factory = self._run(
            _cfg(), "--reenrich", constructor=forbidden)

        self.assertEqual(rc, 0)
        factory.assert_not_called()
        self.assertEqual(self._narrative()["why"], "must remain")
        self.assertIn('"reenrich": true', out)

    def test_plan_discloses_inputs_cache_and_provider_retention(self):
        rc, out, _err, _llm, _factory = self._run(_cfg())

        self.assertEqual(rc, 0)
        for phrase in (
                '"provider": "test-provider"', '"model": "test-model"',
                '"uncached_commits": 1', '"local_sources"',
                '"bounded_input_categories"', '"cache_effects"',
                "ordinary_code", "business_logic", "filenames", "author_data",
                "non_secret_conversation_text", "outside CodeTalk guarantees"):
            self.assertIn(phrase, out)

    def test_endpoint_classification_uses_exact_parsed_hostname(self):
        for url in ("http://localhost:11434/v1",
                    "http://127.0.0.1:11434/v1",
                    "http://[::1]:11434/v1"):
            with self.subTest(url=url):
                details = endpoint_details(_cfg(url))
                self.assertTrue(details["loopback"])
                self.assertIsNone(details["error"])
        for url in ("https://localhost.evil.test/v1",
                    "https://127.0.0.1.evil.test/v1"):
            with self.subTest(url=url):
                self.assertFalse(endpoint_details(_cfg(url))["loopback"])

    def test_endpoint_preview_rejects_embedded_credentials(self):
        details = endpoint_details(_cfg("https://user:secret@api.example.test/v1"))
        self.assertIsNotNone(details["error"])
        self.assertNotIn("secret", json.dumps(details))
        for url in ("https://api.example.test/v1?route=other",
                    "https://api.example.test/v1#fragment"):
            with self.subTest(url=url):
                self.assertIsNotNone(endpoint_details(_cfg(url))["error"])


if __name__ == "__main__":
    unittest.main()
