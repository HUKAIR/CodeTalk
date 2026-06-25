"""FTS5 全文检索辅助:查询安全转义 + 可检索 body 构建 + 历史索引回填(供 cache 调用)。
抽出独立模块:cache.py 守 <300 行,且 FTS 转义/取 body/回填单一职责、可独立测。"""
import json
import logging
import re
import sqlite3

from .config import redact_secrets

log = logging.getLogger("vibetrace")

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


def backfill(conn):
    """回填『FTS 写入逻辑出现前就已缓存』的 commit 叙事索引(一次性自愈,幂等,容错不崩)。
    commit 叙事按 SHA immutable、命中缓存即跳过 enrich(永不重写),旧叙事便不会被
    put_narrative 补进 FTS → search/接地对话召不回。只补真实 commit 叙事(派生键
    graph:/ask:/course:/digest: 都含 ':'、body 本就空,排除);已在 FTS 的由 anti-join
    跳过(首次回填后命中 0 行,每次 Cache 构造仅一次廉价反连接)。落 FTS 前再
    redact_secrets:redact_data 落库前缓存的旧叙事可能未脱敏,与 put_narrative 的 FTS
    写口径完全一致——明文 secret 绝不入索引(M0 隐私红线)。→ 回填条数。"""
    try:
        rows = conn.execute(
            "SELECT sha, narrative_json FROM commit_narratives "
            "WHERE sha NOT LIKE '%:%' "
            "AND sha NOT IN (SELECT sha FROM narrative_fts)").fetchall()
    except sqlite3.Error as exc:
        log.warning("FTS 回填查询失败(%s),全文召回可能不全", exc)
        return 0
    done = 0
    for sha, raw in rows:
        try:
            body = redact_secrets(fts_body(json.loads(raw)))
            conn.execute("INSERT INTO narrative_fts(sha, body) VALUES(?,?)",
                         (sha, body))
            done += 1
        except (ValueError, TypeError, sqlite3.Error) as exc:
            log.warning("FTS 回填 %s 失败(%s),跳过", str(sha)[:7], exc)
    if done:
        conn.commit()
        log.info("FTS 回填 %d 条历史 commit 叙事", done)
    return done


_CJK2 = re.compile(r"(?<![一-鿿])[一-鿿]{2}(?![一-鿿])")


def like_terms(query):
    """抽『独立 2 字中文词』(trigram 无 shingle、MATCH 召不回的那类,如『脱敏』『缓存』)。
    只认前后都非 CJK 的 2 字串:≥3 字 CJK 段已由 build_match 的 trigram 覆盖,不重复 LIKE;
    ASCII 短串(如 'ab')不入,免 LIKE 噪声爆炸。"""
    return _CJK2.findall(query or "")


def like_search(conn, query, limit=8):
    """2 字中文 LIKE 回退(MATCH 召不回时):narrative_fts.body 含该 2 字串即命中。
    空 body 派生键天然不命中;容错降级绝不崩。→ 命中 sha 列表。"""
    terms = like_terms(query)
    if not terms:
        return []
    where = " OR ".join("body LIKE ?" for _ in terms)
    try:
        rows = conn.execute(
            f"SELECT sha FROM narrative_fts WHERE {where} LIMIT ?",
            [f"%{t}%" for t in terms] + [limit]).fetchall()
    except sqlite3.Error as exc:
        log.warning("FTS LIKE 回退失败(%s),返回空", exc)
        return []
    return [r[0] for r in rows]
