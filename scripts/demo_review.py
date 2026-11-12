"""Serve the real review UI with a synthetic Git repository and isolated cache."""
import subprocess
import tempfile
from pathlib import Path

from codetalk import review
from codetalk.review_web import create_review_server


def main():
    root = Path(tempfile.mkdtemp(prefix="codetalk-review-demo-"))
    project = root / "synthetic-cache-demo"
    project.mkdir()

    def git(*args):
        return subprocess.run(["git", "-C", str(project), *args], check=True,
                              capture_output=True, text=True)

    git("init", "-q")
    git("config", "user.name", "Synthetic Demo")
    git("config", "user.email", "demo@example.invalid")
    source = project / "cache.py"
    source.write_text("def invalidate(cache, key):\n    cache.pop(key, None)\n")
    git("add", "--", "cache.py")
    git("commit", "-q", "-m", "Keep invalidation scoped to one key\n\n"
        "Vibe-Decision: Invalidate only the changed key; preserve warm entries.\n"
        "Vibe-Rejected: Clear the entire cache; it discards unrelated entries.",
        "--", "cache.py")
    source.write_text("def invalidate(cache, key):\n    cache.clear()\n")
    # This demonstration never reads or writes the user's normal CodeTalk cache.
    review.CACHE_DB_PATH = root / "cache.db"
    cards, error, _ = review.build_review_cards(project)
    assert error is None and len(cards) == 1, error
    assert cards[0]["kind"] == "potential_conflict"
    server = create_review_server(project, cards, cache_path=root / "cache.db")
    print(f"Synthetic data, real UI: http://127.0.0.1:{server.server_port}/",
          flush=True)
    print(f"Demo files retained at {root}; Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
