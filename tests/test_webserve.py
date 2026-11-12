"""webserve routes 参数:命中路由现算、未命中 404、回调异常不拖垮服务、
不传 routes 时既有 console/tunnel 语义(/ 之外一律 404)逐字不变。
真起 127.0.0.1 服务实测(patch ThreadingHTTPServer 捕获实例以拿端口/关停)。"""
import contextlib
import io
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from codetalk import webserve


class WebServeRoutesCase(unittest.TestCase):
    def setUp(self):
        self.project = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.project, ignore_errors=True)

    def _serve(self, html_text="<html>snap</html>", **kwargs):
        ready = threading.Event()
        box = {}

        class Srv(webserve.ThreadingHTTPServer):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                box["srv"] = self
                ready.set()

        def run():
            with contextlib.redirect_stdout(io.StringIO()), \
                 mock.patch.object(webserve, "ThreadingHTTPServer", Srv):
                webserve.serve_html(html_text, self.project,
                                    open_browser=False, **kwargs)

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self.assertTrue(ready.wait(timeout=5))

        def stop():
            box["srv"].shutdown()
            t.join(timeout=2)

        self.addCleanup(stop)
        return f"http://127.0.0.1:{box['srv'].server_address[1]}"

    def _get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, ""

    def test_route_hit_recomputes_every_get(self):
        hits = []
        origin = self._serve(routes={"/live": lambda: (hits.append(1) or
                                                       f"<html>n={len(hits)}</html>")})
        self.assertEqual(self._get(origin + "/live"), (200, "<html>n=1</html>"))
        self.assertEqual(self._get(origin + "/live"), (200, "<html>n=2</html>"))

    def test_route_miss_404_and_root_keeps_snapshot(self):
        origin = self._serve(routes={"/live": lambda: "<html>live</html>"})
        self.assertEqual(self._get(origin + "/nope")[0], 404)
        self.assertEqual(self._get(origin + "/"), (200, "<html>snap</html>"))

    def test_route_exception_returns_404_and_server_survives(self):
        def boom():
            raise RuntimeError("现算失败")
        origin = self._serve(routes={"/boom": boom,
                                     "/ok": lambda: "<html>ok</html>"})
        self.assertEqual(self._get(origin + "/boom")[0], 404)
        self.assertEqual(self._get(origin + "/ok"), (200, "<html>ok</html>"))

    def test_route_factory_callable_discovers_dynamic_paths(self):
        # recap 形态:routes 传工厂回调,path 动态发现(新会话无需重启)
        def factory(path):
            if path.startswith("/s/"):
                return lambda: f"<html>detail {path[3:]}</html>"
            return None
        origin = self._serve(routes=factory)
        self.assertEqual(self._get(origin + "/s/abcd1234"),
                         (200, "<html>detail abcd1234</html>"))
        self.assertEqual(self._get(origin + "/x")[0], 404)

    def test_no_routes_legacy_semantics_unchanged(self):
        # console/tunnel 不传 routes:/ 之外一律 404,/ 走 builder/快照
        origin = self._serve(builder=lambda: "<html>rebuilt</html>")
        self.assertEqual(self._get(origin + "/anything")[0], 404)
        self.assertEqual(self._get(origin + "/s/abcd1234")[0], 404)
        self.assertEqual(self._get(origin + "/"), (200, "<html>rebuilt</html>"))


if __name__ == "__main__":
    unittest.main()
