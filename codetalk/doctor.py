"""First-run diagnostics for CodeTalk (zero LLM, no cache writes)."""
import os
import shlex
import sys
from pathlib import Path

from . import gitlog, sessions
from .config import CONFIG_PATH, DEFAULTS, load_config, resolve_api_key


def _quote(value):
    return shlex.quote(str(value))


def _breadcrumb_stats(commits):
    total = len(commits)
    rich = 0
    decisions = watches = rejected = 0
    for commit in commits:
        dec, wat = gitlog.parse_breadcrumbs(commit.get("body", ""))
        rej = gitlog.parse_rejected(commit.get("body", ""))
        if dec or wat or rej:
            rich += 1
        decisions += len(dec)
        watches += len(wat)
        rejected += len(rej)
    pct = round((rich / total) * 100) if total else 0
    return {"total": total, "rich": rich, "pct": pct,
            "decisions": decisions, "watches": watches, "rejected": rejected}


def _best_demo_file(commits, tracked):
    if not tracked:
        return ""
    counts = {}
    signal = {}
    for commit in commits:
        dec, wat = gitlog.parse_breadcrumbs(commit.get("body", ""))
        grounded = bool(dec or wat or gitlog.parse_rejected(commit.get("body", "")))
        for file in commit.get("files", []):
            if file in tracked:
                counts[file] = counts.get(file, 0) + 1
                if grounded:
                    signal[file] = signal.get(file, 0) + 1
    preferred = (".py", ".ts", ".tsx", ".js", ".jsx", ".md")
    def is_test(file):
        return file.startswith("tests/") or "/test" in file or file.startswith("test_")

    # 冷启动第一印象:同类文件里优先落在带零-LLM 可接地信号(Vibe-* 面包屑)的那个,
    # 而非单纯改动最多——改得最多却全是光秃标题的文件会让首个 blame 看着像空的。
    ranked = sorted(counts.items(),
                    key=lambda item: (is_test(item[0]), -signal.get(item[0], 0),
                                      -item[1], item[0]))
    for ext in preferred:
        for file, _count in ranked:
            if file.endswith(ext):
                return file
    return ranked[0][0] if ranked else sorted(tracked)[0]


def _session_summary(project):
    session_dir = sessions.CLAUDE_PROJECTS / sessions.project_slug(project)
    if not session_dir.is_dir():
        return f"未找到 Claude 会话目录:{session_dir}"
    files = list(session_dir.glob("*.jsonl"))
    subagents = list(session_dir.glob("*/subagents/**/agent-*.jsonl"))
    return f"找到 Claude 会话:{len(files)} 主会话 + {len(subagents)} subagent"


def _llm_summary():
    cfg = load_config() if CONFIG_PATH.exists() else DEFAULTS
    provider = cfg.get("provider", DEFAULTS["provider"])
    no_llm = bool(cfg.get("no_llm")) or bool(os.environ.get("CODETALK_NO_LLM"))
    if no_llm:
        return "LLM 已硬关闭; blame/search/graph/drift/doctor 仍可零出网使用"
    if resolve_api_key(cfg, provider):
        return f"{provider} key 已配置; enrich/digest 可补全叙事"
    return f"未配置 {provider} key; 先用零 LLM 命令,需要全量叙事时再跑 codetalk init"


def build_doctor_report(project):
    pp = Path(project).resolve()
    commits, err = gitlog.collect_commit_files(pp)
    if err:
        return None, f"git 仓库读取失败:{err}"
    tracked = gitlog.tracked_files(pp) or set()
    stats = _breadcrumb_stats(commits)
    demo = _best_demo_file(commits, tracked)
    evidence = "rich" if stats["pct"] >= 25 else ("partial" if stats["rich"] else "cold-start")
    project_q = _quote(pp)
    lines = [
        f"# CodeTalk Doctor · {pp.name}",
        "",
        f"- Git: {stats['total']} non-merge commits, {len(tracked)} tracked files",
        f"- Evidence: {evidence} ({stats['rich']}/{stats['total']} non-merge commits with decision notes, "
        f"{stats['decisions']} decisions, {stats['watches']} watches, "
        f"{stats['rejected']} rejected)",
        f"- Sessions: {_session_summary(pp)}",
        f"- LLM: {_llm_summary()}",
        "",
        "## 下一步",
    ]
    if demo:
        lines.append(f"1. 看真实效果: codetalk blame {_quote(demo)} --project {project_q}")
    else:
        lines.append(f"1. 先让未来提交留痕: codetalk install-agent-seed --project {project_q}")
    if stats["rich"]:
        lines.append(f"2. 查是否有 AI 写了但没提交: codetalk drift --project {project_q}")
        lines.append(f"3. 让后续提交自动带决策记录: codetalk install-agent-seed --project {project_q}")
    else:
        lines.append(f"2. 让后续提交自动带决策记录: codetalk install-agent-seed --project {project_q}")
        lines.append(f"3. 需要历史全量叙事时: codetalk enrich --project {project_q}")
    return "\n".join(lines), None


def doctor_cmd(args):
    report, err = build_doctor_report(args.project)
    if err:
        print(f"错误:{err}", file=sys.stderr)
        return 2
    print(report)
    return 0
