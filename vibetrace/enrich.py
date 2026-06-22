"""Per-commit narrative enrichment, SHA-keyed and never recomputed."""
import fnmatch
import hashlib
import json
import logging
import os
import re
from pathlib import Path

from .config import redact_secrets
from .gitlog import parse_breadcrumbs, pr_discussion, prior_commit
from .llm import LLMError
from .prompts import OVERVIEW_PROMPT, OVERVIEW_SCHEMA
from .sessions import head_tail

log = logging.getLogger("vibetrace")

# 单天 commit 过多时的兜底:概览输入字符上限,超出截断,概览 token 不爆。
OVERVIEW_LISTING_BUDGET = 6000


def _project_context(project_path, limit=4000):
    """项目背景(节选):CLAUDE.md 优先,否则 README.md;无/读失败返回 ''。
    供叙事据项目约束判断风险(如『引入第三方依赖违背 M0』)。limit 兜住 token。"""
    base = Path(project_path)
    for name in ("CLAUDE.md", "README.md"):
        try:
            text = (base / name).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError):
            continue
        if text:
            return text[:limit]
    return ""


def _prior_context(project_path, commit, cache):
    """这些文件上次改动的叙事 what(跨时间接地:让 LLM 知道本次改动建立在什么之上)。
    无前置 commit / 前置未缓存叙事 → 返回 ''。"""
    prior = prior_commit(project_path, commit["sha"], commit.get("files") or [])
    if not prior:
        return ""
    what = (cache.get_narrative(prior) or {}).get("what", "")
    return f"### 这些文件上次的改动({prior[:7]})\n{what[:200]}" if what else ""


def _commit_prompt(commit, prior_context=""):
    # 项目背景已上移到 llm.narrate(cache_prefix=...) 作缓存前缀,不再每 commit 重传
    parts = []
    if prior_context:
        parts.append(prior_context)
    parts += [
        f"## Commit {commit['sha'][:10]}",
        f"时间:{commit['date'].isoformat()} 作者:{commit['author']}",
        f"message:{commit['subject']}\n{commit['body'][:500]}".strip(),
        "### 变更统计\n" + commit["stat"],
        "### diff 节选\n" + commit["diff_excerpt"],
    ]
    for match in commit.get("matches", [])[:2]:
        session = match["session"]
        parts.append(
            f"### 关联会话 {session['session_id'][:8]}"
            f"(置信度 {match['confidence']},文件交集:"
            f"{', '.join(match['overlap']) or '无'})")
        if session["title"]:
            parts.append("会话标题:" + session["title"])
        if session["prompts"]:    # 保留首尾:靠后的话更接近最终决策
            parts.append("用户原话:\n"
                         + "\n".join("- " + p for p in head_tail(session["prompts"], 6)))
        if session["excerpts"]:
            parts.append("AI 关键陈述:\n"
                         + "\n".join("- " + e for e in head_tail(session["excerpts"], 6)))
    if not commit.get("matches"):
        parts.append("### 无关联会话数据 —— why 字段只能基于 commit 本身,请注明属于推测")
    return "\n\n".join(parts)


def _ts(value):
    """会话时间 → ISO 串:datetime 取 isoformat,已是串则透传,缺失返回 ''。"""
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _evidence(commit):
    """从已排序的 matches(high 优先)取前 ≤2,结构化原话锚点供 ask/blame 核验。
    原话来自已脱敏 summary;落盘再走 put_narrative 二次脱敏。无 matches → []。"""
    out = []
    for match in commit.get("matches", [])[:2]:
        session = match["session"]
        out.append({
            "session_id": session.get("session_id", ""),
            "source": session.get("source", "?"),
            "ts": _ts(session.get("end")),
            "confidence": match["confidence"],
            "prompts": list(session.get("prompts", []))[:3],
            "excerpts": list(session.get("excerpts", []))[:2]})
    return out


_TEST_FUNC = re.compile(r"^\s*(?:async\s+)?def (test_\w+)", re.M)


def _test_refs(project, commit):
    """commit 改动文件对应的仓内测试(本地 why 接地源:从测试场景反推设计,对位问卷一 Q3)。
    源→测试按约定映射(X/foo.py→tests/test_foo.py),改动本身是测试也算;取 test_ 函数名。
    纯本地、无 LLM、至多 5 个文件。"""
    base = Path(project)
    paths = set()
    for f in commit.get("files") or []:
        name = os.path.basename(f)
        if name.startswith("test_") and name.endswith(".py"):
            paths.add(f)
        elif name.endswith(".py") and (base / ("tests/test_" + name)).is_file():
            paths.add("tests/test_" + name)
    out = []
    for p in sorted(paths)[:5]:
        try:
            text = (base / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append({"path": p, "names": _TEST_FUNC.findall(text)[:8]})
    return out


PR_SNIPPET = 400


def _pr_refs(commit, project):
    """该 commit 关联 PR 的标题+描述(用户1 最强 why 源:PR 描述讲需求背景,问卷一 Q3)。
    opt-in(数据出本机);无 PR / gh 不可用 → []。落盘前 redact(标题与正文片段)。"""
    pr = pr_discussion(project, commit["sha"])
    if not pr:
        return []
    return [{"number": pr["number"], "url": pr["url"],
             "title": redact_secrets(pr["title"]),
             "snippet": redact_secrets(pr["body"])[:PR_SNIPPET]}]


def _normalize(narrative):
    clean = {"what": str(narrative.get("what", "")),
             "why": str(narrative.get("why", ""))}
    for key in ("decisions", "risks", "open_loops"):
        value = narrative.get(key, [])
        clean[key] = [str(v) for v in value] if isinstance(value, list) else [str(value)]
    # risks/open_loops 是 LLM 推断字段(llm.py:31),risks 还会被封成时间胶囊。
    # 滤掉『材料不足』填充与空白,免得封出噪声胶囊、上简报堆噪声。decisions 是事实字段,不滤。
    for key in ("risks", "open_loops"):
        clean[key] = [x for x in clean[key]
                      if x.strip() and not x.strip().startswith("材料不足")]
    return clean


TRIVIAL_GLOBS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml",
                 "poetry.lock", "Pipfile.lock", "Cargo.lock", "go.sum",
                 "composer.lock", "*.lock", "*.min.js", "*.min.css")


def _is_trivial(commit):
    """机械提交:改动文件非空且全部是 lockfile/生成产物(零-LLM,保守判定)。
    只要有一个真实源码文件就照常叙事——宁可少跳、不错杀有料小改。"""
    files = commit.get("files") or []
    if not files:
        return False
    return all(any(fnmatch.fnmatch(os.path.basename(f), g) for g in TRIVIAL_GLOBS)
               for f in files)


def enrich_commits(commits, llm, cache, project, with_pr=False):
    stats = {"cache_hits": 0, "llm_calls": 0, "failures": 0, "trivial": 0}
    # 项目背景读一次脱敏,作稳定缓存前缀(系统提示+项目上下文),供本次所有 commit 复用
    cache_prefix = redact_secrets(_project_context(project))
    for commit in commits:
        cached = cache.get_narrative(commit["sha"])
        if cached:
            commit["narrative"] = cached
            stats["cache_hits"] += 1
            continue
        if _is_trivial(commit):  # 机械提交:不调 LLM,存稀疏 stub,仍进时间线
            stub = {"what": commit["subject"],
                    "why": "机械改动(lockfile/生成文件),未叙事",
                    "decisions": [], "risks": [], "open_loops": []}
            commit["narrative"] = stub
            cache.put_narrative(commit["sha"], project, llm.model, stub)
            stats["trivial"] += 1
            continue
        try:
            prior = _prior_context(project, commit, cache)  # 这些文件上次改动叙事
            raw = llm.narrate(redact_secrets(_commit_prompt(commit, prior)),
                              cache_prefix=cache_prefix)
            normalized = _normalize(raw)
            decisions, watches = parse_breadcrumbs(commit.get("body", ""))
            if decisions:  # 人原话并入决策,去重,保留 LLM 既有决策
                normalized["decisions"] = list(dict.fromkeys(
                    normalized["decisions"] + decisions))
            if watches:    # Vibe-Watch 进 risks → 复用现有 risks→seal_capsule 环
                normalized["risks"] = normalized["risks"] + watches
            normalized["evidence"] = _evidence(commit)  # 原话接地锚点(可核验)
            normalized["test_refs"] = _test_refs(project, commit)  # 本地测试接地源
            if with_pr:  # PR 讨论作 why 源(opt-in,数据出本机);默认关时省略
                normalized["pr_refs"] = _pr_refs(commit, project)
            narrative = json.loads(redact_secrets(
                json.dumps(normalized, ensure_ascii=False)))
            stats["llm_calls"] += 1
            commit["narrative"] = narrative
            cache.put_narrative(commit["sha"], project, llm.model, narrative)
        except LLMError as exc:
            log.warning("commit %s 富集失败:%s", commit["sha"][:8], exc)
            stats["failures"] += 1
            commit["narrative"] = {
                "what": commit["subject"], "why": f"(LLM 富集失败:{exc})",
                "decisions": [], "risks": [], "open_loops": [],
                "evidence": [], "test_refs": [], "degraded": True}
    return stats


def make_overview(commits, llm, cache, project, date_str):
    """≤3 句信件体概览 + 今日决定;以 (日期+全部 SHA) 哈希为缓存键,重跑零调用。"""
    fallback = f"今日 {len(commits)} 个 commit:" + ";".join(
        c["subject"] for c in commits[:3])
    fb_decision = next(
        (c["narrative"]["decisions"][0] for c in commits
         if c["narrative"].get("decisions")), "")
    key = "digest:" + hashlib.sha256(
        (date_str + "".join(c["sha"] for c in commits)).encode()).hexdigest()[:40]
    cached = cache.get_narrative(key)
    if cached:
        return (cached.get("overview", fallback),
                cached.get("decision", fb_decision), 0)
    rows = [
        f"- {c['sha'][:8]} {c['subject']}|what: {c['narrative']['what'][:150]}"
        f"|decisions: {'; '.join(c['narrative'].get('decisions', []))[:200]}"
        for c in commits]
    listing = "\n".join(rows)
    if len(listing) > OVERVIEW_LISTING_BUDGET:
        kept, used = 0, 0
        for row in rows:
            if used + len(row) > OVERVIEW_LISTING_BUDGET:
                break
            used += len(row) + 1
            kept += 1
        listing = ("\n".join(rows[:kept])
                   + f"\n… [另有 {len(rows) - kept} 个 commit 未计入当日概览]")
    try:
        raw = llm.narrate(OVERVIEW_PROMPT + listing, schema=OVERVIEW_SCHEMA)
        overview = redact_secrets(str(raw.get("overview", "")).strip() or fallback)
        decision = redact_secrets(str(raw.get("decision", "")).strip() or fb_decision)
        cache.put_narrative(key, project, llm.model,
                            {"overview": overview, "decision": decision})
        return overview, decision, 1
    except LLMError as exc:
        log.warning("概览生成失败,使用降级文本:%s", exc)
        return fallback, fb_decision, 0
