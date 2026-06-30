"""codetalk review —— 零-LLM 的 review 现场入口。

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

# 逐块 blame 是 O(hunks)(每块一次 git log -L);大仓大 diff(实测某深历史仓 276 块约 33s)会过慢,
# 上限内接地、超出截断并指引单点 blame——防 review 在中大仓上拖死。
MAX_REVIEW_HUNKS = 60

_PRECISION = {"line": "行级精确",
              "file": "文件级降级(可能含本块外历史)",
              "none": "无行历史"}

# 接地强度三档徽标:每块前置、一眼可读,把「这条 why 的逐字溯源粒度」的诚实信号顶到眼前
# (护城河)。三档统一用「溯源粒度」措辞(行级/文件级/无),纯 provenance 轴——即便徽标
# 被单独拎出展示也读不成语义判断,**绝不**打对错/可信。R6 钉死:零-LLM 不判
# grounded/inferred/unsupported。
_BADGE = {"line": "[行级溯源]",
          "file": "[文件级溯源]",
          "none": "[无逐字溯源]"}


def _precision_label(precision, segs):
    """每块『溯源精度』标注:前置三档徽标 + 确定性准度细节(行级/文件级/无据)+ 有据/仅提交记录。
    **非**判断这条 why 对不对(语义需模型,零-LLM 不判)。"""
    base = _PRECISION.get(precision, precision)
    detail = ("有据" if any(segment_has_why(s) for s in segs)
              else "仅提交记录(无叙事/面包屑,可先 codetalk enrich)")
    return f"{_BADGE.get(precision, _BADGE['none'])} 溯源精度:{base} · {detail}"


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


def _intercept_section(intercepts):
    """改动块触及『曾被否决的方案』(Vibe-Rejected)→ 顶部拦截清单。确定性把命中的否决项
    提到眼前;**不**自动判定『同概念重引入』(散文 vs 代码需语义,R6 钉死不做)——由你人判。
    无命中返回空串(不污染常规 review)。intercepts=[(file,start,end,[rej...])]。"""
    if not intercepts:
        return ""
    lines = ["## ⚠ 拦截检查:改动触及曾否决的方案,逐条确认你不是在重引入", ""]
    for file, start, end, rejs in intercepts:
        for r in rejs:
            lines.append(f"- `{file}:{start}-{end}` 曾放弃:{r}")
    lines.append("\n确认无误即噪声;若真在重引入,按 docs/discovery/interceptions.md "
                 "记一条——这就是『真拦下一次理由丢失型踩坑』的硬证据。\n")
    return "\n".join(lines) + "\n\n"


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
    total_hunks = len(hunks)
    hunks = hunks[:MAX_REVIEW_HUNKS]          # 上限:大仓大 diff 逐块 blame O(hunks) 会过慢
    cache = Cache(CACHE_DB_PATH)
    blocks = []
    intercepts = []          # 改动块触及曾否决方案 → 顶部拦截清单(人判防重引入)
    for file, start, end in hunks:
        try:
            segs, precision = collect_graded(cache, pp, file, start, end)
        except Exception:                        # noqa: BLE001 行级 git/解析失败 → 该块降级
            segs, precision = [], "none"
        if segs:
            body = _format(file, start, end, segs).rstrip()  # 复用 blame 的确定性渲染
            blocks.append(f"{body}\n  {_precision_label(precision, segs)}")
            rejs = [r for s in segs for r in (s.get("rejected") or [])]
            if rejs:
                intercepts.append((file, start, end, rejs))
        else:
            blocks.append(f"# {file}:{start}-{end}  {_BADGE['none']} 无据:"
                          "零-LLM 无从溯源,可先 codetalk enrich")
    cache.close()
    header = ("# review 接地(零 LLM,逐块历史决策 + 溯源精度)\n"
              "> 溯源精度=确定性信号(行级精确 vs 文件级降级 vs 无据),"
              "**非**判断这条 why 对不对(语义需模型,零-LLM 不判)。\n\n")
    if total_hunks > MAX_REVIEW_HUNKS:        # 截断提示:余下用单点 blame 查
        header += (f"> 注:diff 含 {total_hunks} 个改动块,只接地前 {MAX_REVIEW_HUNKS}"
                   f"(避免大仓逐块 blame 过慢);其余请用 `codetalk blame <文件:行>` 单点查。\n\n")
    return redact_secrets(
        header + _intercept_section(intercepts) + "\n\n".join(blocks)), None
