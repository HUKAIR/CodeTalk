"""vibetrace review —— 零-LLM 的 review 现场入口。

把工具从「手输 file:line 的事后考古」变「review/commit 现场粘 diff 即得」:解析统一 diff →
对每个改动块调既有 blame.collect_graded 罗列真实历史决策 + 原话 + 溯源精度(行级/文件级/无据);
无叙事覆盖的块**显式标「无据」而非编造**(诚实暴露接地命中率上限,对抗 AI 反推噪声)。
唯一新代码是 diff 解析;检索/渲染全复用 blame。零 LLM、不出网、出口脱敏、解析失败降级绝不崩。
"""
import re
import subprocess
from pathlib import Path

from .blame import _format, collect_graded, segment_has_why
from .cache import Cache
from .config import CACHE_DB_PATH, redact_secrets

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

_PRECISION = {"line": "行级精确",
              "file": "文件级降级(可能含本块外历史)",
              "none": "无行历史"}


def _precision_label(precision, segs):
    """每块『溯源精度』标注:确定性准度信号(行级/文件级/无据)+ 有据/仅提交记录。
    **非**判断这条 why 对不对(语义需模型,零-LLM 不判)。"""
    base = _PRECISION.get(precision, precision)
    detail = ("有据" if any(segment_has_why(s) for s in segs)
              else "仅提交记录(无叙事/面包屑,可先 vibetrace enrich)")
    return f"溯源精度:{base} · {detail}"


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
            segs, precision = collect_graded(cache, pp, file, start, end)
        except Exception:                        # noqa: BLE001 行级 git/解析失败 → 该块降级
            segs, precision = [], "none"
        if segs:
            body = _format(file, start, end, segs).rstrip()  # 复用 blame 的确定性渲染
            blocks.append(f"{body}\n  {_precision_label(precision, segs)}")
        else:
            blocks.append(f"# {file}:{start}-{end}  [无据:零-LLM 无从溯源,可先 vibetrace enrich]")
    cache.close()
    header = ("# review 接地(零 LLM,逐块历史决策 + 溯源精度)\n"
              "> 溯源精度=确定性信号(行级精确 vs 文件级降级 vs 无据),"
              "**非**判断这条 why 对不对(语义需模型,零-LLM 不判)。\n\n")
    return redact_secrets(header + "\n\n".join(blocks)), None
