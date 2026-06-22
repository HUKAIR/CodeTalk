"""FTS5 全文检索的纯函数:查询安全转义 + 可检索 body 构建(供 cache 调用)。
抽出独立模块:cache.py 守 <300 行,且 FTS 转义/取 body 单一职责、可独立测。"""
import re

_FTS_STRIP = re.compile(r'["*():\-^]')          # FTS5 查询语法元字符,须先剥离
_FTS_KEYWORDS = {"AND", "OR", "NOT", "NEAR"}    # 裸布尔关键字,当普通 term 剥掉


def build_match(query):
    # 安全 FTS5 MATCH(唯一确定方案):strip 元字符 → 切 term → 有效 term(≥3、非
    # AND/OR/NOT/NEAR)切重叠 trigram phrase(无空格 CJK 整句引用召不回,故按 3 字子串
    # 切;=3 字本身即一 trigram。内部 " 已 strip)→ ' OR ' 连(命中任一即召回)。
    phrases = []
    for term in _FTS_STRIP.sub(" ", query or "").split():
        if len(term) < 3 or term.upper() in _FTS_KEYWORDS:
            continue
        phrases += ['"' + term[i:i + 3] + '"' for i in range(max(1, len(term) - 2))]
    return " OR ".join(phrases)


def fts_body(narrative):
    """可全文检索文本(先窄:why + decisions);字段缺/非 list 降空,绝不崩。"""
    n = narrative if isinstance(narrative, dict) else {}
    why = [n["why"]] if isinstance(n.get("why"), str) and n["why"].strip() else []
    decs = n["decisions"] if isinstance(n.get("decisions"), list) else []
    return "\n".join(why + [str(d) for d in decs if str(d).strip()])
