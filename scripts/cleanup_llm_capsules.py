"""一次性清理:删历史 LLM 预测胶囊,留逐字 Vibe-Watch。

背景:digest 已改为只 seal 逐字 Vibe-Watch(commit/167c2d1 之前的行为是
LLM 推断 risks 也进胶囊,产生大量噪声背包,污染北极星处理率分母)。

本脚本删历史 LLM 胶囊,只留用户手写 Vibe-Watch。默认 dry-run(只打印计数);
加 --confirm 才真删。

用法:
  python3 scripts/cleanup_llm_capsules.py            # dry-run 看数字
  python3 scripts/cleanup_llm_capsules.py --confirm  # 真删
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.cache import Cache                       # noqa: E402
import subprocess                                       # noqa: E402
from codetalk.config import CACHE_DB_PATH, redact_secrets  # noqa: E402
from codetalk.gitlog import commit_body, parse_breadcrumbs  # noqa: E402


def _reachable(project, sha):
    """commit 在该仓是否可达。commit_body 失败时只返回 ''(不抛),故须显式探测——
    否则不可达 commit 的 body='' → 无 watches → 误判为 LLM 预测被删(丢用户手写 Watch)。"""
    try:
        r = subprocess.run(["git", "-C", project, "cat-file", "-e", f"{sha}^{{commit}}"],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main(confirm=False):
    cache = Cache(CACHE_DB_PATH)
    rows = cache.conn.execute(
        "SELECT capsule_id, project, sha, risk FROM capsules").fetchall()
    to_delete = []
    keep = 0
    errors = 0
    for cap_id, project, sha, risk in rows:
        if not _reachable(project, sha):
            errors += 1
            continue       # commit 不可达 → 保守保留,绝不删(可能是用户手写 Watch)
        _decs, watches = parse_breadcrumbs(commit_body(project, sha))
        # 两侧同口径脱敏:capsule.risk 是 seal 时 redact_secrets(watch) 存的,watches 来自原始
        # commit body。含 secret 的手写 Watch 否则会因 [REDACTED] 不等被误删(与 _seal 同口径)。
        watches_norm = {redact_secrets(w) for w in watches}
        if redact_secrets(risk) in watches_norm:
            keep += 1
        else:
            to_delete.append(cap_id)

    print(f"扫描完成:共 {len(rows)} 枚胶囊")
    print(f"  🎯 保留(逐字 Vibe-Watch): {keep}")
    print(f"  🤖 待删(LLM 预测):       {len(to_delete)}")
    print(f"  ⚠️  跳过(commit 不可达): {errors}")

    if not confirm:
        print("\n[DRY-RUN] 未执行删除。加 --confirm 真删。")
        cache.close()
        return 0

    cache.conn.executemany(
        "DELETE FROM capsules WHERE capsule_id=?",
        [(cid,) for cid in to_delete])
    cache.conn.commit()
    remaining = cache.conn.execute(
        "SELECT COUNT(*) FROM capsules").fetchone()[0]
    print(f"\n✅ 已删 {len(to_delete)} 枚,剩 {remaining} 枚。")
    cache.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(confirm="--confirm" in sys.argv[1:]))
