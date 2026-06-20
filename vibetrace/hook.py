"""安装 prepare-commit-msg git 钩子:人手写 commit 时提示留决策面包屑。
补「自动留痕」对人类提交者的覆盖缺口——纯本地、零依赖。"""
import subprocess
from pathlib import Path

# 只在交互编辑器场景($2 为空)提示;-m / merge / squash / amend 跳过。
# 注释行(#)默认被 git 剥除——不填就不污染;grep 守幂等,不重复追加。
HOOK = """#!/bin/sh
# vibetrace prepare-commit-msg:手写 commit 时提示留决策面包屑
msg="$1"; src="$2"
[ -n "$src" ] && exit 0
grep -q "Vibe-Decision:" "$msg" && exit 0
cat >> "$msg" <<'HINT'

# vibetrace:关键技术取舍?去掉 # 并填一行(让 ask / graph 更准):
# Vibe-Decision:
# Vibe-Watch:
HINT
"""


def install_hook(project_path, force=False):
    """装 prepare-commit-msg 钩子。→ (hook_path, error_or_None)。容错不崩。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(project_path), "rev-parse", "--git-path", "hooks"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"git 调用失败:{exc}"
    if out.returncode != 0:
        return None, "不是 git 仓库:" + (out.stderr.strip()[:120] or "rev-parse 失败")
    hooks = (Path(project_path) / out.stdout.strip()).resolve()
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "prepare-commit-msg"
    if hook.exists() and not force:
        return None, f"钩子已存在:{hook}(加 --force 覆盖)"
    hook.write_text(HOOK, encoding="utf-8")
    hook.chmod(0o755)
    return hook, None


SEED_MARKER = "<!-- vibetrace-agent-seed -->"
AGENT_SEED = """
<!-- vibetrace-agent-seed -->
## vibetrace 决策捕获(AI coding agent 必读)

每次 `git commit`,在 commit message 正文按下面格式留下这次改动的**关键决策与推导**,
供 vibetrace 长期分析(ask / graph / digest 据此接地,免得日后从 diff 反推)。保持精炼:
每条一行、总共几行即可,别写长文。**行首精确、区分大小写**。

- `Vibe-Decision: <做了什么决定;为什么这么选;否决了什么备选>` —— 一个关键决策一行,可多条
- `Vibe-Watch: <没把握、需日后验证的点>` —— 风险 / 待验证,可多条

例:

    Vibe-Decision: 用 --no-merges 跳合并而非 --first-parent —— 后者保留合并气泡、丢功能提交,叙事更差
    Vibe-Watch: 空提交尾部 NUL subject 未处理,罕见暂不管
"""


def install_agent_seed(project_path):
    """把决策捕获约定幂等植入项目 CLAUDE.md(无则建),让 AI agent 提交时留推导面包屑。
    → (claude_md_path, error_or_None)。只追加、绝不覆盖已有内容;容错不崩。"""
    claude = Path(project_path) / "CLAUDE.md"
    try:
        existing = claude.read_text(encoding="utf-8") if claude.exists() else ""
    except (OSError, UnicodeError) as exc:
        return None, f"读取 CLAUDE.md 失败:{exc}"
    if SEED_MARKER in existing:
        return claude, None   # 幂等:已植入,不重复追加
    sep = "" if (not existing or existing.endswith("\n")) else "\n"
    try:
        with open(claude, "a", encoding="utf-8") as fh:
            fh.write(sep + AGENT_SEED)
    except OSError as exc:
        return None, f"写入 CLAUDE.md 失败:{exc}"
    return claude, None
