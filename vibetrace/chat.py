"""接地对话编排(护城河核心)。

每轮:retrieve(零-LLM 真实记录)→ inject(材料喂 LLM)→ 综合 → cite(检索层确定的引用)。
红线:
- C-1 出网收口:发给 LLM 的最终 user message(question + 历史 + 材料)整体过 redact_data。
- 材料空 / llm 不可用(no_llm 时 web 层构造 LLMClient 抛 LLMError → 传 None)→ 不调 LLM,
  降级为零-LLM 材料罗列(护城河:绝不让 LLM 凭空答)。
- 引用由检索层确定(retrieval.citations),非模型自报。
- 每轮落库(脱敏在 conversation.save_turn 内部),反哺接地。
LLM 作注入依赖(对象需有 .chat(messages)->str);真流式/provider 调用在 Phase 2。
"""
from . import conversation, retrieval
from .config import redact_data
from .prompts import CHAT_SYSTEM_PROMPT

_NO_MATERIAL = ("没有在项目记忆里找到相关记录;换个关键词,"
                "或先跑 vibetrace digest 富集叙事。")
_HISTORY_TURNS = 6


def _history(cache, conv_id):
    """从已落库的前几轮重建对话历史(供理解追问意图,非事实依据;见 CHAT_SYSTEM_PROMPT)。"""
    turns = conversation.list_conversation(cache, conv_id)[-_HISTORY_TURNS:]
    return "\n".join(f"{t['role']}:{t['text']}" for t in turns)


def _grounding(hits, degraded):
    """确定性接地覆盖徽标(零-LLM,按检索命中种类算):真实 commit / 讨论 各几条。
    落 SO/Uber「引用来源 + 暴露置信度」处方;degraded=True 表示未调模型(零-LLM 罗列)。"""
    return {"commits": sum(1 for h in hits if h.get("kind") == "commit"),
            "conversations": sum(1 for h in hits if h.get("kind") == "conversation"),
            "degraded": degraded}


def build_user_message(question, history, material):
    """组装发给 LLM 的 user message,并在出网前整体脱敏(C-1 单点收口,不依赖上游)。"""
    parts = []
    if history:
        parts.append("对话历史(仅供理解追问意图,不得作事实依据):\n" + history)
    parts.append("材料(真实记录,旧→新;只据此回答):\n" + (material or "(无相关记录)"))
    parts.append(f"问题:{question}")
    return redact_data("\n\n".join(parts))


def answer(cache, llm, project_path, question, *, target=None, conv_id="c1",
           history="", now="", turn_seq=0):
    """一轮接地对话 → {answer, citations, conv_id, degraded}。
    llm=None(无 key / no_llm)或材料空 → degraded=True,LLM 不被调用。"""
    ev = retrieval.assemble(cache, project_path, question, target=target)
    history = history or _history(cache, conv_id)   # 多轮:前几轮作上下文(非事实依据)
    conversation.save_turn(cache, f"{conv_id}:{turn_seq:03d}:0", conv_id,
                           str(project_path), now, "user", question)
    if llm is None or not ev["hits"]:           # no_llm / 材料空 → 零-LLM 降级,不调 LLM
        answer_text = ev["material"] or _NO_MATERIAL
        degraded = True
    else:
        messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT},
                    {"role": "user",
                     "content": build_user_message(question, history, ev["material"])}]
        answer_text = llm.chat(messages)
        degraded = False
    conversation.save_turn(cache, f"{conv_id}:{turn_seq:03d}:1", conv_id,
                           str(project_path), now, "assistant", answer_text,
                           cited_shas=[h["sha"] for h in ev["hits"]])
    return {"answer": answer_text, "citations": ev["citations"],
            "conv_id": conv_id, "degraded": degraded,
            "grounding": _grounding(ev["hits"], degraded)}


def answer_stream(cache, llm, project_path, question, *, target=None, conv_id="c1",
                  history="", now="", turn_seq=0):
    """流式接地对话 generator → 逐块 yield {type:"token",text} … 末尾 {type:"done",...}。
    与 answer 同接地/脱敏/降级口径;落库的是拼齐的完整答案。
    no_llm/材料空 → 单块零-LLM 罗列 + done,绝不调 LLM(I-2)。"""
    ev = retrieval.assemble(cache, project_path, question, target=target)
    history = history or _history(cache, conv_id)   # 多轮:前几轮作上下文(非事实依据)
    conversation.save_turn(cache, f"{conv_id}:{turn_seq:03d}:0", conv_id,
                           str(project_path), now, "user", question)
    pieces = []
    if llm is None or not ev["hits"]:           # 降级:单块,不开流到 LLM
        text = ev["material"] or _NO_MATERIAL
        pieces.append(text)
        yield {"type": "token", "text": text}
        degraded = True
    else:
        messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT},
                    {"role": "user",
                     "content": build_user_message(question, history, ev["material"])}]
        for delta in llm.chat_stream(messages):
            pieces.append(delta)
            yield {"type": "token", "text": delta}
        degraded = False
    answer_text = "".join(pieces)
    conversation.save_turn(cache, f"{conv_id}:{turn_seq:03d}:1", conv_id,
                           str(project_path), now, "assistant", answer_text,
                           cited_shas=[h["sha"] for h in ev["hits"]])
    yield {"type": "done", "citations": ev["citations"],
           "conv_id": conv_id, "degraded": degraded,
           "grounding": _grounding(ev["hits"], degraded)}
