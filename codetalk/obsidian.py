"""Track A v1:Obsidian 自动反链(写侧)。为每个带决策的 commit 自动产出一张决策笔记
vault/codetalk/<slug>/<sha7>.md,链回当天日报 [[{date}-{project}]];Obsidian 据此在日报侧
自动生成反链,让自动挖出的接地决策在你既有图谱里成为可反链节点。

机器自动产出、非用户手写(守护城河第③支柱「自动挖掘」);零 LLM、纯 stdlib、数据不出本机、
落盘前脱敏;子目录名由绝对路径派生防同名串库;同 SHA 覆写幂等;任何失败降级返回 0、绝不崩。
opt-in:仅 config.backlinks=true 时由 digest 调用(默认关)。
"""
import hashlib
import logging
from pathlib import Path

from .config import redact_secrets

log = logging.getLogger("codetalk")


def _slug(project, pkey):
    """子目录名:可读 basename + 绝对路径哈希前缀,防同名 basename 两项目物理串写。"""
    h = hashlib.sha256(str(pkey).encode("utf-8")).hexdigest()[:8]
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in str(project))
    return f"{safe}-{h}"


def _note(sha, date_str, project, subject, decisions):
    """单张决策笔记的 markdown(落盘前脱敏;链回当天日报供 Obsidian 反链)。"""
    lines = [f"# 决策 · `{sha}`  {redact_secrets(subject or '')}".rstrip(),
             "", f"来源日报:[[{date_str}-{project}]]", ""]
    for d in decisions:
        lines.append(f"- {redact_secrets(str(d))}")
    lines.append("")
    lines.append("<!-- codetalk 自动产出(零 LLM,从真实 commit 决策挖);勿手改,会被覆写 -->")
    return "\n".join(lines) + "\n"


def emit_decision_notes(commits, project, vault_path, pkey):
    """为每个带决策的 commit 写一张决策笔记 → 返回写出的笔记数。
    容错红线:vault 无效/写失败 → 记 warning 跳过该条,整体返回已写数,绝不抛。"""
    if not vault_path:
        return 0
    try:
        out_dir = Path(vault_path).expanduser() / "codetalk" / _slug(project, pkey)
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("Obsidian 反链目录创建失败:%s", exc)
        return 0
    count = 0
    for commit in commits:
        decisions = (commit.get("narrative") or {}).get("decisions") or []
        decisions = [d for d in decisions if str(d).strip()]
        if not decisions:
            continue
        try:
            sha = commit["sha"][:7]
            date_str = commit["date"].date().isoformat()
            content = _note(sha, date_str, project, commit.get("subject", ""), decisions)
            (out_dir / f"{sha}.md").write_text(content, encoding="utf-8")
            count += 1
        except (OSError, KeyError, AttributeError, TypeError) as exc:
            log.warning("Obsidian 反链笔记跳过 %s:%s",
                        str(commit.get("sha", "?"))[:7], exc)
    return count
