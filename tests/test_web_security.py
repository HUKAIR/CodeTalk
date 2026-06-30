import unittest
import warnings
from unittest import mock

from fastapi.testclient import TestClient

from vibetrace import web


def _client():
    return TestClient(web.app, base_url="http://127.0.0.1")


class _FakeCache:
    def __init__(self, projects=None):
        self.projects = projects or []

    def distinct_projects(self):
        return self.projects

    def close(self):
        pass


class TestWebLocalRequestGuard(unittest.TestCase):
    def test_cross_origin_post_rejected_before_chat_runs(self):
        with mock.patch.object(web.chat, "answer", side_effect=AssertionError("called")), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = _client().post(
                "/api/chat",
                headers={"Origin": "https://evil.example"},
                json={"question": "why"},
            )
        self.assertEqual(r.status_code, 403)
        self.assertIn("bad origin", r.text)

    def test_bad_host_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = _client().get("/", headers={"Host": "evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_same_origin_post_allowed(self):
        out = {"answer": "ok", "citations": [], "highlights": [], "conv_id": "c1"}
        with mock.patch.object(web.chat, "answer", return_value=out), \
             mock.patch.object(web, "_llm", return_value=None), \
             mock.patch.object(web, "Cache", lambda *_a, **_k: _FakeCache()), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = _client().post(
                "/api/chat",
                headers={"Origin": "http://127.0.0.1"},
                json={"question": "why"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["answer"], "ok")


class TestWebApiRedaction(unittest.TestCase):
    def test_projects_endpoint_redacts_secret_shaped_paths(self):
        raw = '/tmp/project-password="hunter2secretvalue"'
        with mock.patch.object(web, "Cache", lambda *_a, **_k: _FakeCache([raw])), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = _client().get("/api/projects")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("hunter2secretvalue", r.text)
        self.assertIn("[REDACTED]", r.text)

    def test_graph_endpoint_redacts_json_before_serializing(self):
        raw = '{"nodes":[{"text":"password=\\"hunter2secretvalue\\""}],"edges":[]}'
        with mock.patch.object(web, "build_graph_json", return_value=(raw, None)), \
             mock.patch.object(web, "Cache", lambda *_a, **_k: _FakeCache()), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = _client().get("/api/graph")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("hunter2secretvalue", r.text)
        self.assertIn("[REDACTED]", r.text)

    def test_graph_endpoint_does_not_echo_malformed_json(self):
        raw = 'not json password="hunter2secretvalue"'
        with mock.patch.object(web, "build_graph_json", return_value=(raw, None)), \
             mock.patch.object(web, "Cache", lambda *_a, **_k: _FakeCache()), \
             warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = _client().get("/api/graph")
        self.assertEqual(r.status_code, 500)
        self.assertNotIn("hunter2secretvalue", r.text)
        self.assertIn("graph unavailable", r.text)


if __name__ == "__main__":
    unittest.main()
