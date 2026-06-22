"""Evolution course: the project's history → a single-file HTML course
teaching 'how it grew + what AI decided' (not 'what the code is').

Static phase (this module): one LLM call splits the full history into
chapters with intros + scenario quizzes; debt-heavy modules rank first;
code↔explanation pairs reuse cached narratives + per-chapter diffs.
Falls back to a naive time-ordered course (no LLM) when no API key.

Like tunnel.py: assembles data and substitutes it into course.html;
the template's JS renders chapters / code-pairs / quizzes.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .debt import debt_board
from .gitlog import collect_commit_files, commit_diff
from .llm import LLMClient, LLMError
from .webserve import inline_json

EXCERPT = 220

COURSE_SCHEMA = {
    "type": "object",
    "properties": {
        "chapters": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string", "description": "章名:这一阶段做了什么(人话)"},
            "intro": {"type": "string", "description": "章导言:当时的决定与被否决的备选(专业)"},
            "plain": {"type": "string", "description": "这一章用最通俗的大白话再讲一遍,"
                      "像跟完全不懂代码的朋友解释,不用任何术语"},
            "commit_shas": {"type": "array", "items": {"type": "string"},
                            "description": "本章涵盖的短 sha(7 位)"},
            "quiz": {"type": "array", "items": {"type": "object", "properties": {
                "q": {"type": "string", "description": "场景应用题"},
                "options": {"type": "array", "items": {"type": "string"}},
                "answer": {"type": "integer", "description": "正确选项索引(从 0)"},
                "hint": {"type": "string", "description": "答错时的提示"},
            }, "required": ["q", "options", "answer", "hint"]}},
        }, "required": ["title", "intro", "plain", "commit_shas", "quiz"]}},
    },
    "required": ["chapters"],
}


def _course_prompt(commits, narr_by_short, debt):
    lines = ["把下面这个项目的完整提交历史,编排成一门『这个项目怎么一步步长成这样的』"
             "演进课程。要求:把相关 commit 聚成 5 章左右(不是一 commit 一章);"
             "每章讲清当时的决定与被否决的备选;每章再用最通俗的大白话(plain,不用术语、"
             "像跟外行解释)把这章重讲一遍;每章出 1-2 道场景应用题(考『要做 X "
             "会改哪些文件/为何这么设计』,而非记忆)。"]
    lines.append("密度纪律:每个讲解块最多 2-3 句、信息要密;隐喻不跨章复用;"
                 "代码原样取 5-10 行不简化;测验考新场景不考记忆。")
    if debt:
        hot = "、".join(r["file"] for r in debt[:3])
        lines.append(f"优先把用户最欠理解的模块({hot})的演进讲透、靠前。")
    lines.append("\n提交历史(旧→新):")
    for c in commits:
        sha = c["sha"][:7]
        n = narr_by_short.get(sha, {})
        lines.append(f"[{sha}] {c['date'].date()} {c.get('subject', '')}")
        if n.get("what"):
            lines.append(f"  改了什么:{n['what'][:EXCERPT]}")
        if n.get("decisions"):
            lines.append("  决定:" + ";".join(n["decisions"][:3]))
    return "\n".join(lines)


def _naive_chapters(commits, narr_by_short):
    """无 LLM 降级:按时间均分若干章,无测验。"""
    n = max(1, round(len(commits) ** 0.5))
    size = max(1, -(-len(commits) // n))  # ceil
    chapters = []
    for i in range(0, len(commits), size):
        group = commits[i:i + size]
        shas = [c["sha"][:7] for c in group]
        intro = next((narr_by_short.get(s, {}).get("why", "") for s in shas
                      if narr_by_short.get(s, {}).get("why")), "(未智能编排)")
        chapters.append({"title": f"第 {len(chapters) + 1} 阶段:{group[0].get('subject', '')[:40]}",
                         "intro": intro, "plain": "", "commit_shas": shas, "quiz": []})
    return chapters


_TYPES = ("feat", "fix", "docs", "refactor", "chore", "test", "style",
          "perf", "build", "ci", "revert")


def _parse_type(subject):
    """从 conventional commit 前缀解析类型徽标(feat/fix/...);无则空。"""
    head = (subject or "").split(":", 1)[0].split("(", 1)[0].strip().lower()
    return head if head in _TYPES else ""


def _chapter_blocks(chapter, project_path, narr_by_short, subj_by_short):
    """每章代码↔讲解:取前 2 个 commit 的 diff 片段 + 叙事 what + 类型徽标。"""
    blocks = []
    for raw_sha in (chapter.get("commit_shas") or [])[:2]:
        sha = raw_sha[:7]  # LLM 可能返回全 sha,归一到短 7 位再查
        n = narr_by_short.get(sha, {})
        subject = subj_by_short.get(sha, "")
        # 隐私红线:原始 diff 可能含 API key/token,写盘进 vault 前必须脱敏
        blocks.append({"sha": sha, "subject": subject, "type": _parse_type(subject),
                       "diff": redact_secrets(commit_diff(project_path, sha)),
                       "what": (n.get("what") or "")[:EXCERPT]})
    return blocks


def build_course(project_path):
    """Build the course HTML; returns (output_path, error_or_None)."""
    cfg = load_config()
    project_path = Path(project_path).resolve()
    project = project_path.name
    commits, err = collect_commit_files(project_path)
    if err:
        return None, err
    if not commits:
        return None, "没有任何 commit,课程无从谈起。"
    cache = Cache(CACHE_DB_PATH)
    narr_by_short = {c["sha"][:7]: (cache.get_narrative(c["sha"]) or {})
                     for c in commits}
    subj_by_short = {c["sha"][:7]: c.get("subject", "") for c in commits}
    today = datetime.now(timezone.utc).astimezone().date()
    debt = debt_board(project_path, cache, today, top=5)

    # v2:schema 加了 plain 大白话字段,旧缓存无此字段 → 换版本前缀自然失效重算
    key = "course:v2:" + hashlib.sha256(
        "".join(c["sha"] for c in commits).encode()).hexdigest()[:40]
    cached = cache.get_narrative(key)
    degraded = False
    llm_stats = {}
    if cached and cached.get("chapters"):
        chapters = cached["chapters"]
    else:
        chapters, degraded, llm_stats = _make_chapters(
            commits, narr_by_short, debt, cfg, cache, key, project)
    cache.close()

    for ch in chapters:
        ch["blocks"] = _chapter_blocks(ch, project_path, narr_by_short,
                                       subj_by_short)
        # 聚合本章 commit 的潜在风险/未闭环(M0 已有数据,enrich 已脱敏)
        risks, loops = [], []
        for raw_sha in (ch.get("commit_shas") or []):
            n = narr_by_short.get(raw_sha[:7], {})
            risks += n.get("risks") or []
            loops += n.get("open_loops") or []
        ch["risks"] = list(dict.fromkeys(risks))[:5]
        ch["open_loops"] = list(dict.fromkeys(loops))[:5]
    data = {"chapters": chapters, "degraded": degraded}
    template = Template((Path(__file__).parent / "course.html")
                        .read_text(encoding="utf-8"))
    html_text = template.substitute(
        project=project,
        data=inline_json(data),
        generated=f"{today:%Y.%m.%d}")
    html_text = redact_secrets(html_text)  # 隐私红线:落盘前对整页脱敏
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / f"{project}-course.html"
    out.write_text(html_text, encoding="utf-8")
    from . import report  # 记一行用量(章数 / 是否降级 / LLM token 省额),写失败不拖垮主流程
    report.append_usage({
        "command": "course", "project": str(project_path),
        "chapters": len(chapters), "degraded": degraded,
        "llm_calls": llm_stats.get("calls", 0),
        "tokens_in": llm_stats.get("input_tokens", 0),
        "tokens_out": llm_stats.get("output_tokens", 0),
        "cache_hit_tokens": llm_stats.get("cache_hit_tokens", 0),
    })
    return out, None


def _make_chapters(commits, narr_by_short, debt, cfg, cache, key, project):
    """Returns (chapters, degraded, llm_stats). LLM 一次出章+测验;无 key/失败则朴素降级。
    llm_stats 透传 token 用量给 self 周报;降级路径无 LLM,返回空 dict。"""
    try:
        llm = LLMClient(cfg)
    except LLMError:
        return _naive_chapters(commits, narr_by_short), True, {}
    try:
        # max_tokens 须覆盖『推理 + 大 JSON 输出』:deepseek-v4-pro 等推理模型先花
        # 数千 reasoning token,默认 3000 会被推理吃光、输出为空(实测 finish=length)
        result = llm.narrate(_course_prompt(commits, narr_by_short, debt),
                             schema=COURSE_SCHEMA, max_tokens=16000)
        chapters = result.get("chapters") if isinstance(result, dict) else None
        if not chapters:
            return _naive_chapters(commits, narr_by_short), True, llm.stats
        # 隐私红线:LLM 生成的章节入缓存前脱敏(避免把原文里的 secret 持久化)
        cache.put_narrative(key, project, llm.model, json.loads(redact_secrets(
            json.dumps({"chapters": chapters}, ensure_ascii=False))))
        return chapters, False, llm.stats
    except LLMError:
        return _naive_chapters(commits, narr_by_short), True, llm.stats
