"""全局叙事核验(零 LLM):审计所有缓存 commit 叙事的保真度。

fact-discipline 明禁『材料中不存在的文件名/函数名』。本审计确定性地抓**最可检的一类**:叙事提到
的文件路径,其 basename 若在全仓历史(任何 commit 改过的文件)里**根本不存在** → ghost(疑似编造
文件名)。另统计降级叙事(材料不足/富集失败 —— 诚实降级,非编造,但要计)。纯本地、零 LLM、不触网。
注:只查「文件名保真」这一确定性子集;语义保真(why 是否反推编造)由盲测实验另证,非本脚本范畴。
用法:python3 scripts/narrative_audit.py [project_path]
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codetalk.cache import Cache                              # noqa: E402
from codetalk.config import CACHE_DB_PATH                     # noqa: E402
from codetalk.gitlog import collect_commit_files              # noqa: E402

# 带已知代码/文档扩展名的文件路径 token(避免 e.g./i.e. 等假阳性)。
# 路径体限 ASCII:`\w` 会匹配 CJK,把中文叙述粘到尾随扩展名上(如「Canvas 2D替代Three.js」
# 错切成一个 token),真实路径不含 CJK,故显式列 ASCII 字符类而非 `\w`。
_PATH = re.compile(
    r"[A-Za-z0-9_][A-Za-z0-9_./\-]*\."
    r"(?:py|js|ts|jsx|tsx|json|md|html|css|sh|yml|yaml|toml|txt|cfg|ini|lock|db)\b")


def audit(narratives, all_bases):
    """narratives: {sha: dict}; all_bases: 全仓历史文件 basename 集。→ 审计 dict(零 LLM)。
    ghost = 叙事提到的文件 basename 不在 all_bases(疑似编造的文件名)。"""
    out = {"total": 0, "degraded": 0, "ghost_narr": 0, "clean": 0, "flags": []}
    for sha, n in narratives.items():
        if not isinstance(n, dict):
            continue
        out["total"] += 1
        text = " ".join([n.get("why") or ""]
                        + [str(x) for x in (n.get("decisions") or [])]
                        + [str(x) for x in (n.get("risks") or [])])
        if n.get("degraded") or "材料不足" in text or "富集失败" in text:
            out["degraded"] += 1
        ghosts = sorted({p for p in _PATH.findall(text)
                         if os.path.basename(p) not in all_bases})
        if ghosts:
            out["ghost_narr"] += 1
            out["flags"].append({"sha": sha[:7], "ghosts": ghosts[:6]})
        else:
            out["clean"] += 1
    return out


def main(project="."):
    pp = Path(project).resolve()
    commits, err = collect_commit_files(pp)
    if err:
        print(f"git 错误:{err}", file=sys.stderr)
        return 1
    all_bases = {os.path.basename(f) for c in commits for f in (c.get("files") or [])}
    cache = Cache(CACHE_DB_PATH)
    narratives = {c["sha"]: n for c in commits if (n := cache.get_narrative(c["sha"]))}
    cache.close()
    r = audit(narratives, all_bases)
    print(f"# 全局叙事核验 · {pp.name}(零 LLM,文件名保真)\n")
    print(f"有叙事的 commit:          {r['total']}")
    print(f"降级(材料不足/富集失败):  {r['degraded']}")
    print(f"提到不存在文件名(ghost):  {r['ghost_narr']}")
    print(f"\n**文件名保真干净:          {r['clean']}/{r['total']}**")
    for f in r["flags"]:
        print(f"  ⚠ [{f['sha']}] ghost: {f['ghosts']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
