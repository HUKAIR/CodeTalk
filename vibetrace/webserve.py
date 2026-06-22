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


def serve_html(html_text, project_path, open_browser=True):
    """起本地服务托管 html_text;/capsule、/reviewed 即时写回 cache。阻塞到 Ctrl+C,返回 None。"""
    pkey = str(Path(project_path).resolve())   # 胶囊/reviewed 回写键:绝对路径

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # 静默,不打 access log

        def do_GET(self):
            if self.path != "/":
                self.send_response(404); self.end_headers(); return
            body = html_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
