"""扫描 web 静态产物有无外链(http(s),排除 127.0.0.1/localhost)——守『不走 CDN / 不
phone home』红线。vibetrace web 页面必须全内联、只 fetch 同源 /api。CI/发布前对
web_chat.html(及未来 SPA dist)跑:`python3 -m scripts.check_static_no_external <file...>`。
"""
import re
import sys
from pathlib import Path

_EXTERNAL = re.compile(r"https?://(?!127\.0\.0\.1|localhost)[^\s\"')<>]+", re.I)


def scan(text):
    """→ 外链列表(同源相对路径、127.0.0.1/localhost 不算)。"""
    return _EXTERNAL.findall(text or "")


def check_file(path):
    return scan(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    bad = [(p, hits) for p in sys.argv[1:] if (hits := check_file(p))]
    for p, hits in bad:
        print(f"外链泄漏 {p}: {hits[:5]}", file=sys.stderr)
    sys.exit(1 if bad else 0)
