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
