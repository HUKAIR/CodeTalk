"""blame:零-LLM 行级决策溯源 —— ask 的确定性孪生。

给定文件(可选行范围),用 git 行历史(line_log,行级失败降级文件级)找出触达这些
行的 commit,映射到已缓存叙事 + Vibe-Decision 面包屑,确定性打印每段决策史
(SHA·日期·subject·decisions)。ask 用 LLM 综合,blame 只如实罗列;无 key 也能用。
"""
import re
import sys
from pathlib import Path

from .cache import Cache
from .config import CACHE_DB_PATH
from .gitlog import (commit_body, commit_meta, file_log, line_log,
                     parse_breadcrumbs)

_RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def _parse_target(target):
    """与 ask 同口径:'f.py'→(f.py,None,None);'f.py:2-4'→(f.py,2,4);'f.py:5'→(f.py,5,5)。
    冒号右侧不是行号则整串当文件(路径含冒号罕见)。"""
    if ":" in target:
        file, _, tail = target.rpartition(":")
        match = _RANGE_RE.match(tail)
        if file and match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            return file, start, end
    return target, None, None


def collect_segments(cache, project_path, file, start, end):
    """→ 触达这些行的每个 commit 一段(旧→新),含 sha/date/subject/decisions/risks。
    行级失败降级文件级;每段 decisions = 缓存叙事决策 ∪ 面包屑(去重,缓存已折入不重复)。"""
    if start is not None:
        shas, err = line_log(project_path, file, start, end)
        if err:                            # 行级失败 → 文件级降级
            shas, _ = file_log(project_path, file)
    else:
        shas, _ = file_log(project_path, file)
    segments = []
    for sha in shas:
        narrative = cache.get_narrative(sha) or {}
        decisions, watches = parse_breadcrumbs(commit_body(project_path, sha))
        decs = list(dict.fromkeys((narrative.get("decisions") or []) + decisions))
        risks = list(dict.fromkeys((narrative.get("risks") or []) + watches))
        date_iso, subject = commit_meta(project_path, sha)
        segments.append({
            "sha": sha, "date": date_iso, "subject": subject,
            "why": narrative.get("why") or "",
            "decisions": decs, "risks": risks,
        })
    return segments


def _format(file, start, end, segments):
    span = f"{file}:{start}-{end}" if start is not None else file
    lines = [f"# blame {span}(旧→新,共 {len(segments)} 个 commit 触达)\n"]
    for seg in segments:
        date = (seg["date"] or "")[:10]    # 仅日期部分
        lines.append(f"[{seg['sha'][:7]}] {date} {seg['subject']}")
        if seg["why"]:
            lines.append(f"  意图:{seg['why']}")
        for dec in seg["decisions"]:
            lines.append(f"  决策:{dec}")
        for risk in seg["risks"]:
            lines.append(f"  待验证:{risk}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def blame(project_path, target):
    """CLI 入口:解析→收集→确定性打印,返回退出码。零 LLM,无 key 也能用。"""
    file, start, end = _parse_target(target)
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    segments = collect_segments(cache, pp, file, start, end)
    cache.close()
    if not segments:
        print(f"错误:{file} 没有可用的提交历史,无从溯源。", file=sys.stderr)
        return 2
    print(_format(file, start, end, segments), end="")
    return 0
