"""codetalk demo:一条命令让陌生人在碰自己空仓之前先体感护城河。

现造一个小仓(带纪律面包屑的 3 个 commit)→ 跑真实 blame 引擎 → 打印零-LLM、
逐字接地的决策史。无 key、无配置、无 enrich——把「首个价值」和「首次富集」解耦。
纯 stdlib(subprocess/tempfile),自造 fixture(绝不用真实第三方仓派生物)。
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# 自造 fixture:一个订单积分场景(对位 ICP 的「决策一错就出钱」),面包屑齐全。
_COMMITS = [
    ("points.py",
     "def award(order):\n    return int(order.total // 10)\n",
     "feat(points): award points on order total\n\n"
     "Vibe-Decision: 用 //10 整除向下取整,宁可少给不可多给——超发比少发难追回\n"
     "Vibe-Rejected: round(total/10) 四舍五入——0.5 边界会超发,财务不可逆"),
    ("points.py",
     "def award(order):\n    if order.refunded:\n        return 0\n"
     "    return int(order.total // 10)\n",
     "fix(points): no points on refunded orders\n\n"
     "Vibe-Decision: 退款单直接 0 分,不走取整——防「下单得分→退款留分」薅羊毛\n"
     "Vibe-Watch: 部分退款(refund_amount<total)仍全额给分,待接部分退款后重算"),
    ("points.py",
     "def award(order):\n    if order.refunded:\n        return 0\n"
     "    pts = int(order.total // 10)\n    return min(pts, DAILY_CAP)\n",
     "feat(points): cap daily points to curb abuse\n\n"
     "Vibe-Decision: 单日封顶 DAILY_CAP,挡刷单;封顶在最后一步,不影响退款判定\n"
     "Vibe-Watch: DAILY_CAP 硬编码,跨等级用户可能需分档——先扛,有反馈再配"),
]


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _build_fixture(d):
    """在 d 里造一个带面包屑的真 git 仓(3 个 commit 演绎一个积分决策故事)。"""
    _git(["init", "-q"], d)
    _git(["config", "user.email", "demo@codetalk"], d)
    _git(["config", "user.name", "codetalk-demo"], d)
    for fname, content, msg in _COMMITS:
        (Path(d) / fname).write_text(content, encoding="utf-8")
        _git(["add", fname], d)
        _git(["commit", "-q", "-m", msg], d)


def run_demo():
    """CLI 入口:造 fixture → 真 blame → 打印。零 LLM、零配置、跑完即弃。→ 退出码。"""
    if not shutil.which("git"):
        print("错误:demo 需要 git。", file=sys.stderr)
        return 2
    d = tempfile.mkdtemp(prefix="codetalk-demo-")
    try:
        _build_fixture(d)
        print("# codetalk demo —— 零-LLM 逐字接地(现造的小仓,跑完即弃)\n")
        print("场景:订单积分,一个「决策一错就出钱」的真实痛点。")
        print("下面是 codetalk 对 points.py 的 blame——每条 why/决策/否决备选都逐字")
        print("引自真实 commit,没有一个字是 LLM 事后编的:\n")
        from .blame import blame
        blame(d, "points.py")
        print("\n" + "─" * 60)
        print("这就是护城河:对手(Cursor/Copilot)只能从当前 diff 反推「为什么」,")
        print("而这些 why-NOT(为何没用 round、为何退款给 0 分)diff 里根本不存在。")
        print("\n下一步:在你自己的仓跑 `codetalk blame <文件>`;")
        print("没有面包屑?`codetalk install-agent-seed .` 让 AI 提交时自动留 why。")
        return 0
    finally:
        shutil.rmtree(d, ignore_errors=True)
