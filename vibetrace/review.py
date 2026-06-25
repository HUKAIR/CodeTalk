"""vibetrace review —— 零-LLM 的 review 现场入口。

把工具从「手输 file:line 的事后考古」变「review/commit 现场粘 diff 即得」:解析统一 diff →
对每个改动块调既有 blame.collect_segments 罗列真实历史决策 + 原话 + 置信(N commit 触达);
无叙事覆盖的块**显式标「无据」而非编造**(诚实暴露接地命中率上限,对抗 AI 反推噪声)。
唯一新代码是 diff 解析;检索/渲染全复用 blame。零 LLM、不出网、出口脱敏、解析失败降级绝不崩。
"""
import re
import subprocess
from pathlib import Path

from .blame import _format, collect_segments
from .cache import Cache
from .config import CACHE_DB_PATH, redact_secrets

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff(text):
    """统一 diff → [(file, start, end)] 每 hunk 一条(post-image 行范围)。
    跟 `+++ b/<file>` 定位文件,`@@ … +start,count @@` 取范围;无法解析/纯删除块跳过,绝不崩。"""
    hunks, cur = [], None
    for line in (text or "").splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            cur = None if path == "/dev/null" else re.sub(r"^b/", "", path)
        elif line.startswith("@@") and cur:
            m = _HUNK.match(line)
            if not m:
                continue
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) else 1
            if count <= 0:                       # 纯删除块:post-image 无行,跳过
                continue
            hunks.append((cur, start, start + count - 1))
    return hunks


def _git_diff(pp):
    """工作树相对 HEAD 的 diff(本地 git,不出网)→ (text, error)。"""
    try:
        out = subprocess.run(["git", "-C", str(pp), "diff", "HEAD"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"git diff 失败:{exc}"
    if out.returncode != 0:
        return None, f"git diff 失败:{out.stderr.strip()[:200]}"
    return out.stdout, None


def review(project_path, diff_text=None):
    """→ (report_text, error)。diff_text=None → 用 git diff HEAD。零 LLM、不出网、落地前脱敏。"""
    pp = Path(project_path).resolve()
    if diff_text is None:
        diff_text, err = _git_diff(pp)
        if err:
            return None, err
    hunks = parse_unified_diff(diff_text)
    if not hunks:
        return "没有可分析的改动块(diff 为空或无法解析)。", None
    cache = Cache(CACHE_DB_PATH)
    blocks = []
    for file, start, end in hunks:
        try:
            segs = collect_segments(cache, pp, file, start, end)
        except Exception:                        # noqa: BLE001 行级 git/解析失败 → 该块降级
            segs = []
        if segs:
            blocks.append(_format(file, start, end, segs))   # 复用 blame 的确定性渲染
        else:
            blocks.append(f"# {file}:{start}-{end}  [无据:零-LLM 无从溯源,可先 vibetrace enrich]")
    cache.close()
    return redact_secrets("# review 接地(零 LLM,逐块历史决策)\n\n" + "\n\n".join(blocks)), None
