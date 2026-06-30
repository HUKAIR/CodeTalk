"""codetalk drift:AI 工具动作 vs 实际提交的确定性偏差(零 LLM)。

复用 sessions.files_written(AI 用 Write/Edit/NotebookEdit 工具改的文件)+ git 提交文件 +
align 软对齐,报**字面文件级缺口**:本会话工具改了、却没落进其高置信对齐提交的文件
(做了没落地 / 被回滚 / 未提交)。直击「AI 说了去干却没做全」痛点。
**诚实边界**:「声称」=工具动作(非散文计划——后者语义、需模型);只报可数文件缺口,
**不**判「完成度 X%」「设计是否可行」「执行质量」(那需模型,违零-LLM 护城河)。
"""
import json
import subprocess
import sys
from pathlib import Path

from . import gitlog, sessions
from .align import _relative_files, align
from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .digest import _since_to_dt


def _ignored(rel_paths, project_root):
    """git 视角下「本就不该提交」的相对路径:.git/ 内部 + .gitignore 命中。
    零 LLM、确定性;用于滤掉 commit-msg 草稿/sdd/编辑器配置等噪声,只留真有意义的偏差。"""
    drop = {p for p in rel_paths if p == ".git" or p.startswith(".git/")}
    rest = [p for p in rel_paths if p not in drop]
    if rest:
        try:                                     # check-ignore:无命中时退出码 1,故不走 gitlog._git
            out = subprocess.run(["git", "check-ignore", "--", *rest],
                                 cwd=str(project_root), capture_output=True,
                                 text=True, timeout=30)
            drop |= {ln for ln in out.stdout.splitlines() if ln}
        except (OSError, subprocess.TimeoutExpired):
            pass
    return drop


def drift_rows(commits, sessions_list, project_root, exclude=None):
    """对齐后,每会话:工具改的文件(去 exclude)vs 其高置信对齐提交的文件 → 写了未提交。
    → [{session_id, written, committed, missing:[...]}](纯函数,可单测)。"""
    root = Path(project_root).resolve()
    exclude = exclude or set()
    align(commits, sessions_list, root)
    rows = []
    for s in sessions_list:
        fw = _relative_files(s, root) - exclude
        if not fw:
            continue
        committed = set()
        for c in commits:
            for m in c.get("matches", []):
                if m["session"] is s and m["confidence"] == "high":
                    committed |= set(c["files"])
        rows.append({"session_id": s.get("session_id", ""),
                     "written": len(fw), "committed": len(fw & committed),
                     "missing": sorted(fw - committed)})
    return rows


def drift_json(project, since="7 days ago"):
    """MCP-safe JSON output: assemble commits+sessions -> drift_rows -> JSON string.
    Returns {"flagged": [...], "session_count": N, "warning": str|null}."""
    pp = Path(project).resolve()
    commits, err = gitlog.collect_commit_files(pp)
    if err:
        return json.dumps({"error": err, "flagged": []}, ensure_ascii=False)
    cache = Cache(CACHE_DB_PATH)
    try:
        sess, serr = sessions.scan_sessions(pp, _since_to_dt(since), cache)
    finally:
        cache.close()
    all_fw = set()
    for s in sess:
        all_fw |= _relative_files(s, pp)
    exclude = _ignored(all_fw, pp)
    flagged = [r for r in drift_rows(commits, sess, pp, exclude=exclude)
               if r["missing"]]
    return json.dumps({"flagged": flagged, "session_count": len(sess),
                       "warning": serr or None}, ensure_ascii=False)


def drift_cmd(args):
    cfg = load_config()                          # noqa: F841 — 统一入口惯例(后续可读 sources)
    pp = Path(args.project).resolve()
    commits, err = gitlog.collect_commit_files(pp)   # 全史:让会话写入能对上其真实提交,不被 --since 截断误判
    if err:
        print(f"错误:{err}", file=sys.stderr)
        return 2
    cache = Cache(CACHE_DB_PATH)
    sess, serr = sessions.scan_sessions(pp, _since_to_dt(args.since), cache)
    cache.close()
    if serr:
        print(f"会话层降级:{serr}", file=sys.stderr)
    all_fw = set()
    for s in sess:
        all_fw |= _relative_files(s, pp)
    exclude = _ignored(all_fw, pp)               # 滤 .git/ 内部 + gitignore 命中(噪声)
    flagged = [r for r in drift_rows(commits, sess, pp, exclude=exclude) if r["missing"]]
    print(f"# 偏差自检 · {pp.name}(AI 工具动作 vs 实际提交,零 LLM)\n")
    if not flagged:
        print("本窗口无「写了未提交」偏差(工具改动都落进了对齐提交)。")
    for r in flagged:
        print(f"会话 {r['session_id'][:8]}:工具改 {r['written']} 文件、{r['committed']} 已提交、"
              f"{len(r['missing'])} 个写了未提交:")
        for f in r["missing"][:12]:
            print(f"  ✗ {f}")
    print("\n注:「声称」=AI 工具动作(Write/Edit),非散文计划;只报字面文件缺口,"
          "不判完成度%/设计可行性(那需模型)。")
    return 0
