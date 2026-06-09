"""Render the daily digest markdown, write it to the vault, log the run."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .config import USAGE_LOG_PATH, redact_secrets

log = logging.getLogger("vibetrace")


def _section(title, items):
    if not items:
        return ""
    return f"\n**{title}**\n" + "\n".join("- " + i for i in items) + "\n"


def render(project, date_str, overview, commits, sessions, session_error,
           run_stats):
    lines = [f"# {date_str} {project} 开发日报", ""]
    if session_error:
        lines += [f"> ⚠️ 会话数据不可用,本日报为纯 git 模式({session_error})", ""]
    lines += ["## 今日概览", "", overview, "", "## 变更叙事", ""]
    for commit in commits:
        n = commit["narrative"]
        when = commit["date"].strftime("%H:%M")
        lines.append(f"### `{commit['sha'][:8]}` {commit['subject']}({when})")
        if n.get("degraded"):
            lines.append("> ⚠️ 本条为降级叙事(LLM 调用失败)")
        lines.append(f"\n**改了什么** {n['what']}\n")
        lines.append(f"**为什么** {n['why']}")
        lines.append(_section("关键决策", n["decisions"]))
        lines.append(_section("风险(供日后验证)", n["risks"]))
        lines.append(_section("未闭环", n["open_loops"]))
        refs = [f"`{m['session']['session_id'][:8]}`({m['confidence']}"
                f",交集 {len(m['overlap'])} 文件)"
                for m in commit.get("matches", [])]
        lines.append("关联会话:" + ("、".join(refs) if refs else "无"))
        lines.append("")
    loops = [loop for c in commits for loop in c["narrative"]["open_loops"]]
    lines += ["## 未闭环汇总", ""]
    lines += (["- " + l for l in dict.fromkeys(loops)] if loops else ["(无)"])
    lines += ["", "---",
              f"commits {run_stats['commits']} | 会话 {run_stats['sessions']} | "
              f"缓存命中 {run_stats['cache_hits']}/{run_stats['commits']} | "
              f"LLM 调用 {run_stats['llm_calls']}"
              f"(tokens in {run_stats['tokens_in']} / out {run_stats['tokens_out']}) | "
              f"model {run_stats['model']} | 用时 {run_stats['elapsed_s']}s"]
    return redact_secrets("\n".join(lines))


def write_report(vault_path, project, date_str, content):
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    path = vault / f"{date_str}-{project}.md"
    path.write_text(content, encoding="utf-8")
    return path


def append_usage(record):
    """Append run parameters to ~/.vibetrace/usage.log (data flywheel seed)."""
    try:
        record["ts"] = datetime.now(timezone.utc).isoformat()
        with open(USAGE_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("usage.log 写入失败:%s", exc)
