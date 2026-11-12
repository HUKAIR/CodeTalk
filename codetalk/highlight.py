"""答案内逐字命中片段切分(零 LLM,纯 stdlib difflib)。

把 LLM 答案按「与被引材料纯原话(citation.verbatim)逐字重叠 ≥MIN_SPAN」切成交替段
[{text, cite_id}](cite_id=None 普通段、带 id 命中段),**段拼接 === answer**,供前端只 esc
拼接、不切片(消灭 Python 码位 vs JS UTF-16 下标错位)。只匹配纯原话(非 render_hit 脚手架)、
只标逐字命中下界——非语义归因/幻觉检测。
"""
import difflib

MIN_SPAN = 6


def segments(answer, citations):
    """answer + citations([{id, verbatim, ...}]) → [{text, cite_id|None}](拼接===answer)。
    无 ≥MIN_SPAN 逐字命中 / answer 空 / None → []。"""
    answer = answer or ""
    spans = []                                       # (start, end, cite_id)
    for cit in citations or []:
        vb = cit.get("verbatim") or ""
        if not vb:
            continue
        sm = difflib.SequenceMatcher(None, answer, vb, autojunk=False)
        for blk in sm.get_matching_blocks():         # 末尾哨兵 size=0 自然被 >=MIN_SPAN 滤掉
            if blk.size >= MIN_SPAN:
                spans.append((blk.a, blk.a + blk.size, cit.get("id")))
    if not spans:
        return []
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0]),
                              s[2] if s[2] is not None else -1))
    chosen, last_end = [], 0
    for st, en, cid in spans:
        if st >= last_end:                           # 贪心:按 start、长者优先、不重叠
            chosen.append((st, en, cid))
            last_end = en
    out, pos = [], 0
    for st, en, cid in chosen:
        if st > pos:
            out.append({"text": answer[pos:st], "cite_id": None})
        out.append({"text": answer[st:en], "cite_id": cid})
        pos = en
    if pos < len(answer):
        out.append({"text": answer[pos:], "cite_id": None})
    return out
