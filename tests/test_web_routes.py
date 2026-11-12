"""web /graph 与 /course 路由:富交互页在浏览器内可达(与 CLI 同渲染),降级不崩。"""
import unittest
import warnings
from unittest import mock

from fastapi.testclient import TestClient

from codetalk import web


def _client():
    return TestClient(web.app, base_url="http://127.0.0.1")


def _get(path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _client().get(path)


class TestGraphCourseRoutes(unittest.TestCase):
    def test_graph_route_renders(self):
        with mock.patch.object(web, "render_graph_html",
                               return_value=("<html>DAG $ok</html>", None)):
            r = _get("/graph?project=.")
        self.assertEqual(r.status_code, 200)
        self.assertIn("DAG", r.text)

    def test_graph_route_error_degrades(self):
        with mock.patch.object(web, "render_graph_html",
                               return_value=(None, "no git")):
            r = _get("/graph?project=.")
        self.assertEqual(r.status_code, 400)
        self.assertIn("决策图", r.text)

    def test_course_route_renders(self):
        with mock.patch.object(web.course, "render_course_html",
                               return_value=("<html>COURSE</html>", None)):
            r = _get("/course?project=.")
        self.assertEqual(r.status_code, 200)
        self.assertIn("COURSE", r.text)

    def test_course_route_error_degrades(self):
        with mock.patch.object(web.course, "render_course_html",
                               return_value=(None, "no commits")):
            r = _get("/course?project=.")
        self.assertEqual(r.status_code, 400)
        self.assertIn("演进课程", r.text)

    def test_graph_route_redacts(self):
        with mock.patch.object(web, "render_graph_html",
                               return_value=("key sk-abcdef0123456789ABCDEF x", None)):
            r = _get("/graph?project=.")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", r.text)
        self.assertIn("[REDACTED]", r.text)


if __name__ == "__main__":
    unittest.main()
