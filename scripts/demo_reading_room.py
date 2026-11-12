"""Run the real reading room against synthetic Git records and an isolated cache."""
import argparse
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from codetalk import console, recap, report, sessions
from codetalk.cache import Cache
from codetalk.reading_server import create_reading_server


def build_fixture(root):
    root = Path(root).resolve()
    project = root / "cache-lab"
    project.mkdir(parents=True)
    db = root / "cache.db"

    def git(*args):
        return subprocess.run(["git", "-C", str(project), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    git("config", "user.name", "Synthetic Demo")
    git("config", "user.email", "demo@example.invalid")
    records = [
        ("cache.py", "def invalidate(cache, key):\n    cache.pop(key, None)\n",
         "保留按 key 失效，保护无关缓存", "只失效发生变化的 key，保留已经验证的其他结果。",
         "清空整个缓存；它会丢弃无关条目并重复计算。"),
        ("test_cache.py", "from cache import invalidate\n\ndef test_other_keys_survive():\n"
         "    cache = {'a': 1, 'b': 2}\n    invalidate(cache, 'a')\n    assert cache == {'b': 2}\n",
         "用回归测试留下缓存边界", "将未失效条目仍然存在作为可重复检查的约束。",
         "只检查缓存是否变空；它会把错误的全量清空当作成功。"),
        ("cache.py", "def invalidate(cache, key):\n    # Keep unrelated cached results.\n    cache.pop(key, None)\n",
         "让缓存边界在实现处可回读", "保留按 key 失效，并把理由留在实现旁边。",
         "用全量清空简化实现；它会破坏其他 key 的复用。"),
    ]
    shas = []
    for name, content, title, chosen, rejected in records:
        (project / name).write_text(content, encoding="utf-8")
        git("add", "--", name)
        git("commit", "-qm", title + "\n\nVibe-Decision: " + chosen
            + "\nVibe-Rejected: " + rejected + "\nVibe-Watch: 验证空缓存和缺失 key 的行为。", "--", name)
        shas.append(git("rev-parse", "HEAD"))
    # An actual uncommitted change gives the review page an actual diff to inspect.
    (project / "cache.py").write_text("def invalidate(cache, key):\n    cache.clear()\n", encoding="utf-8")
    today = datetime.now(timezone.utc).astimezone().date().isoformat()
    with Cache(db) as cache:
        cache.seal_capsule(str(project), shas[-1], 0, "空缓存和缺失 key 是否安全返回？", today, today)
        cache.open_due_capsules(str(project), today)
        cache.put_daily(str(project), today, "合成演示：缓存边界已有原始记录，当前改动需要核对。", "保留按 key 失效。")
    # Point all session and usage reads/writes at this demo's directory.
    sessions.CLAUDE_PROJECTS = recap.CLAUDE_PROJECTS = root / "sessions"
    report.USAGE_LOG_PATH = console.USAGE_LOG_PATH = root / "usage.log"
    folder = root / "sessions" / sessions.project_slug(project)
    folder.mkdir(parents=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    messages = [
        {"type": "user", "timestamp": timestamp, "sessionId": "synthetic-reading",
         "message": {"role": "user", "content": "为什么不能直接清空整个缓存？请保留按 key 失效。"}},
        {"type": "assistant", "timestamp": timestamp, "sessionId": "synthetic-reading",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "合成会话：全量清空会丢弃无关条目。约束已写入提交说明。"}]}},
    ]
    (folder / "synthetic-reading.jsonl").write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in messages), encoding="utf-8")
    return project, db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.output or Path(tempfile.mkdtemp(prefix="codetalk-reading-demo-"))
    project, db = build_fixture(root)
    page, _, error = console._build_html(project, False, cache_path=db)
    assert error is None, error
    (root / "reading-room.html").write_text(page, encoding="utf-8")
    server = create_reading_server(project, cache_path=db)
    print(f"Synthetic data, real backend: http://127.0.0.1:{server.server_port}/#timeline", flush=True)
    print(f"Files retained at {root}; Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
