"""Render the daily digest markdown, write it to the vault, log the run."""
import json
import logging
import re
from datetime import date, datetime, timezone
from pathlib import Path

from .config import USAGE_LOG_PATH, redact_secrets

log = logging.getLogger("vibetrace")


def _section(title, items):
    if not items:
        return ""
    return f"\n**{title}**\n" + "\n".join("- " + i for i in items) + "\n"


def _on_this_day_block(entries):
    """头部回流:把过去同一天的概览首句端到面前。两条都无则整块省略。"""
    rows = []
    for label, (date, overview) in entries.items():
        first = (overview or "").split("。")[0].strip("。 \n")
        if not first:  # 跨时间读到旧行 overview 为空/NULL → 跳过,不崩
            continue
        rows.append(f"> 📮 **{label}** · {date}:「{first}。」")
    return ("\n".join(rows) + "\n") if rows else ""


def _capsule_block(capsules, today):
    """今日开启的时间胶囊:旧 risk 到期,作为反思 checkbox 端回面前。
    每枚胶囊前埋稳定锚(HTML 注释,Obsidian 不渲染),供下次运行回读勾选。"""
    if not capsules:
        return ""
    lines = ["## 🕰 今日开启的时间胶囊", ""]
    for cap in capsules:
        sealed = date.fromisoformat(cap["sealed_date"])
        n = (today - sealed).days
        lines.append(f"<!-- vt-capsule:{cap['capsule_id']} -->")
        lines.append(f"- **{n} 天前**(`{cap['sha'][:7]}`)你担心:"
                     f"「{cap['risk']}」")
        # 已回填的胶囊预勾选 [x],不擦回空框、不重复催问(回填环不被自身擦除)
        answered = cap.get("outcome")
        boxes = "　".join(f"[{'x' if o == answered else ' '}] {o}"
                          for o in _OUTCOMES)
        lines.append("  - " + boxes)
    return "\n".join(lines) + "\n"


def render(project, date_str, overview, commits, sessions, session_error,
           run_stats, decision="", on_this_day=None, capsules=None, today=None):
    today = today or date.today()
    lines = [f"# {date_str} {project} 开发日报", ""]
    otd = _on_this_day_block(on_this_day or {})
    if otd:
        lines += [otd]
    if session_error:
        lines += [f"> ⚠️ 会话数据不可用,本日报为纯 git 模式({session_error})", ""]
    lines += ["## 今日概览", "", overview, ""]
    if decision:
        lines += [f"> **今日决定** — {decision}", ""]
    cap = _capsule_block(capsules or [], today)
    if cap:
        lines += [cap]
    lines += ["## 变更叙事", ""]
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
    footer = (
        f"commits {run_stats['commits']} | 会话 {run_stats['sessions']} | "
        f"缓存命中 {run_stats['cache_hits']}/{run_stats['commits']} | "
        f"LLM 调用 {run_stats['llm_calls']}"
        f"(tokens in {run_stats['tokens_in']} / out {run_stats['tokens_out']}) | "
        f"model {run_stats['model']} | 用时 {run_stats['elapsed_s']}s")
    if run_stats.get("capsule_opened"):
        footer += (f" | 胶囊回填 {run_stats['capsule_filled']}"
                   f"/{run_stats['capsule_opened']}")
    lines += ["", "---", footer]
    return redact_secrets("\n".join(lines))


def write_report(vault_path, project, date_str, content):
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    path = vault / f"{date_str}-{project}.md"
    path.write_text(content, encoding="utf-8")
    return path


_CAPSULE_MARKER = "<!-- vt-capsule:"
_OUTCOMES = ("想多了", "已解决", "还在担心")


def read_capsule_answers(vault_path, project_path, cache):
    """回读:扫 vault 里本项目的旧日报,把用户勾选的 [x] 答案写回缓存,闭合预测-验证环。
    project_path=项目绝对路径:文件名按 basename 匹配,胶囊键用绝对路径(同名项目不串)。
    任何解析失败记 warning 跳过,绝不崩溃(容错红线)。"""
    vault = Path(vault_path).expanduser()
    if not vault.is_dir():
        return
    name = Path(project_path).name
    # 严格匹配 <ISO 日期>-<name>.md:glob 的 *-api.md 会误吞 …-legacy-api.md
    name_re = re.compile(r"\d{4}-\d{2}-\d{2}-" + re.escape(name) + r"\.md$")
    for md in vault.glob(f"*-{name}.md"):
        if not name_re.fullmatch(md.name):
            continue
        try:
            lines = md.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            log.warning("回读胶囊跳过 %s:%s", md.name, exc)
            continue
        pending_id = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(_CAPSULE_MARKER):
                pending_id = stripped[len(_CAPSULE_MARKER):].rstrip(" ->")
            elif pending_id and ("[x]" in stripped or "[X]" in stripped):
                checked = stripped.replace("[X]", "[x]")
                ticked = next((o for o in _OUTCOMES if f"[x] {o}" in checked),
                              None)
                if ticked:
                    cache.set_capsule_outcome(pending_id, ticked, project_path)
                pending_id = None


def append_usage(record):
    """Append run parameters to ~/.vibetrace/usage.log (data flywheel seed)."""
    try:
        record["ts"] = datetime.now(timezone.utc).isoformat()
        with open(USAGE_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        log.warning("usage.log 写入失败:%s", exc)
