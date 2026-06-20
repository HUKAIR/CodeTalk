"""Per-commit narrative enrichment, SHA-keyed and never recomputed."""
import hashlib
import json
import logging
from pathlib import Path

from .config import redact_secrets
from .gitlog import parse_breadcrumbs
from .llm import LLMError

log = logging.getLogger("vibetrace")

# 单天 commit 过多时的兜底:概览输入字符上限,超出截断,概览 token 不爆。
OVERVIEW_LISTING_BUDGET = 6000

OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "string",
            "description": "今日开发概览,第二人称信件体,不超过 3 句"},
        "decision": {
            "type": "string",
            "description": "今日最重要的一个决定,从各 commit 的 decisions 里挑一句或综合一句"},
    },
    "required": ["overview", "decision"], "additionalProperties": False,
}


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


def _commit_prompt(commit, project_context=""):
    parts = []
    if project_context:
        parts.append("### 项目背景(节选,据此判断改动是否违背项目约束)\n"
                     + project_context)
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
        if session["prompts"]:
            parts.append("用户原话:\n"
                         + "\n".join("- " + p for p in session["prompts"][:6]))
        if session["excerpts"]:
            parts.append("AI 关键陈述:\n"
                         + "\n".join("- " + e for e in session["excerpts"][:6]))
    if not commit.get("matches"):
        parts.append("### 无关联会话数据 —— why 字段只能基于 commit 本身,请注明属于推测")
    return "\n\n".join(parts)


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


def enrich_commits(commits, llm, cache, project):
    stats = {"cache_hits": 0, "llm_calls": 0, "failures": 0}
    ctx = _project_context(project)   # 项目背景读一次,供本次所有 commit 叙事接地
    for commit in commits:
        cached = cache.get_narrative(commit["sha"])
        if cached:
            commit["narrative"] = cached
            stats["cache_hits"] += 1
            continue
        try:
            raw = llm.narrate(redact_secrets(_commit_prompt(commit, ctx)))
            normalized = _normalize(raw)
            decisions, watches = parse_breadcrumbs(commit.get("body", ""))
            if decisions:  # 人原话并入决策,去重,保留 LLM 既有决策
                normalized["decisions"] = list(dict.fromkeys(
                    normalized["decisions"] + decisions))
            if watches:    # Vibe-Watch 进 risks → 复用现有 risks→seal_capsule 环
                normalized["risks"] = normalized["risks"] + watches
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
                "decisions": [], "risks": [], "open_loops": [], "degraded": True}
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
        raw = llm.narrate(
            "为以下一天的 commit 写概览:用第二人称『你』、像结对同事帮你回忆"
            "今天写了什么,不超过 3 句;再挑出今天最重要的一个决定。\n" + listing,
            schema=OVERVIEW_SCHEMA)
        overview = redact_secrets(str(raw.get("overview", "")).strip() or fallback)
        decision = redact_secrets(str(raw.get("decision", "")).strip() or fb_decision)
        cache.put_narrative(key, project, llm.model,
                            {"overview": overview, "decision": decision})
        return overview, decision, 1
    except LLMError as exc:
        log.warning("概览生成失败,使用降级文本:%s", exc)
        return fallback, fb_decision, 0
