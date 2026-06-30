"""ask/blame 接地渲染的共享部件:会漂移的中文标题文案、low-confidence 判定、字段口径。

ask 喂 LLM 用扁平格式、blame 喂终端用树状 2/4/6 空格缩进——格式分歧是 intentional,
各自保留;此处只收会两处一起漂的标题文案与置信度阈值,改一次而非两次。
"""

EVIDENCE_TITLE = "原话佐证(可自行核验):"
EVIDENCE_LOW_WARN = "(基于软关联会话,置信较低,请核对原话)"
TEST_REFS_TITLE = "相关测试(从测试场景反推设计):"
PR_REFS_TITLE = "相关 PR 讨论(当初的需求背景):"


def evidence_low_confidence(evidence):
    """支撑全为 low(无任一 high)→ True,调用方据此追加置信度警示。"""
    return not any(ev.get("confidence") == "high" for ev in evidence)
