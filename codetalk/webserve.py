"""共享本地 web 服务:127.0.0.1 托管单文件 HTML,页面 POST 回答即时写回 cache.db。

console 与 tunnel 的 --serve 共用,服务器逻辑不在两处重复(渲染可重复,服务器不该)。
绑 127.0.0.1(不 0.0.0.0):数据不出本机。cache.db 是胶囊/回看的单一真相源。
"""
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .cache import Cache
from .config import CACHE_DB_PATH
from .report import _OUTCOMES


def inline_json(data):
    # 把数据嵌进 <script> 块时,序列里出现的 "</" 会让浏览器以为 </script> 提前闭合,
    # 转义成 "<\/" 即可安全内联(对 JSON 解析无影响)。
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def serve_html(html_text, project_path, open_browser=True, builder=None, routes=None):
    """起本地服务托管 html_text;/capsule、/reviewed 即时写回 cache。阻塞到 Ctrl+C,返回 None。
    builder:可选无参回调,给定则每次 GET 都调它重建页面(真·实时刷新),失败回退首帧快照。
    routes:可选,/ 之外的现算路由。dict[path, 无参回调](精确命中)或工厂回调
    path -> 回调|None(调用方自管匹配,支持动态发现的路径);现算失败回 404 不拖垮服务。"""
    pkey = str(Path(project_path).resolve())   # 胶囊/reviewed 回写键:绝对路径

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # 静默,不打 access log

        def _send_page(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/":
                try:                          # 命中 routes → 现算;未命中/失败 → 404
                    fn = (routes.get(self.path) if isinstance(routes, dict)
                          else routes(self.path)) if routes else None
                    body = fn().encode("utf-8") if fn else None
                except Exception:             # noqa: BLE001 — 路由现算失败不拖垮服务
                    body = None
                if body is None:
                    self.send_response(404); self.end_headers(); return
                self._send_page(body); return
            try:                              # builder 给定→每请求重建(实时);失败回退快照
                body = (builder() if builder else html_text).encode("utf-8")
            except Exception:                 # noqa: BLE001 — 重建失败不拖垮服务
                body = html_text.encode("utf-8")
            self._send_page(body)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(n))
            except (ValueError, TypeError):
                self.send_response(400); self.end_headers(); return
            cache = Cache(CACHE_DB_PATH)
            try:
                if self.path == "/capsule":
                    if req.get("outcome") not in _OUTCOMES:  # 防任意串写入缓存
                        self.send_response(400); self.end_headers(); return
                    cache.set_capsule_outcome(req["capsule_id"], req["outcome"], pkey)
                elif self.path == "/reviewed":
                    sha = req.get("sha")
                    if not isinstance(sha, str) or not sha:
                        self.send_response(400); self.end_headers(); return
                    cache.mark_reviewed(pkey, sha)
                else:
                    self.send_response(404); self.end_headers(); return
            except KeyError:
                self.send_response(400); self.end_headers(); return
            finally:
                cache.close()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)  # 只对本机开放
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print(f"本地服务:{url}\n回答即时写回 cache.db。Ctrl+C 停止。")
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()
    return None
