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
from vibetrace.cache import Cache                       # noqa: E402
from vibetrace.config import CACHE_DB_PATH              # noqa: E402
from vibetrace.gitlog import commit_body, parse_breadcrumbs  # noqa: E402


def main(confirm=False):
    cache = Cache(CACHE_DB_PATH)
    rows = cache.conn.execute(
        "SELECT capsule_id, project, sha, risk FROM capsules").fetchall()
    to_delete = []
    keep = 0
    errors = 0
    for cap_id, project, sha, risk in rows:
        try:
            body = commit_body(project, sha)
        except Exception:
            errors += 1
            continue       # commit 不可达 → 保守保留,不删
        _decs, watches = parse_breadcrumbs(body)
        if risk in watches:
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
