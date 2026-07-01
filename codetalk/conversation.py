"""web 接地对话落库(皇冠明珠,留本机)+ 反哺接地。

对话(你 ↔ LLM 关于「这段当初为什么」)脱敏后落库 web_conversations,并把 text 接进
narrative_fts,使未来 topic_search / ask / search 能召回「你在 X 讨论过,结论 Y」。
落库脱敏在 save_turn 内部单点收口(对齐 cache.put_narrative 纪律),secret 不进库。
"""
import json

from .config import redact_secrets

_SCHEMA = """
CREATE TABLE IF NOT EXISTS web_conversations (
    turn_id TEXT PRIMARY KEY, conv_id TEXT, project TEXT, ts TEXT,
    role TEXT, text TEXT, cited_shas TEXT);
"""
_KEY = "conv:"   # narrative_fts 里对话行的 sha 前缀(与真实 commit sha 区分)


def _ensure(cache):
    cache.conn.executescript(_SCHEMA)


def save_turn(cache, turn_id, conv_id, project, ts, role, text, cited_shas=()):
    """落一轮对话。脱敏单点收口(方法内部,不依赖调用方);project 存绝对路径
    (对齐 distinct_projects 的 LIKE '/%')。FTS 索引失败只 warning,不拖垮主写。"""
    _ensure(cache)
    safe = redact_secrets(str(text or ""))     # 皇冠明珠落库前脱敏
    cache.conn.execute(
        "INSERT OR REPLACE INTO web_conversations VALUES (?,?,?,?,?,?,?)",
        (turn_id, conv_id, project, ts, role, safe,
         json.dumps(list(cited_shas), ensure_ascii=False)))
    cache.conn.commit()
    if getattr(cache, "fts_ok", False) and safe.strip():
        try:                                   # 反哺:对话 text 进 FTS(C-2)
            cache.conn.execute("DELETE FROM narrative_fts WHERE sha=?",
                               (_KEY + turn_id,))
            cache.conn.execute("INSERT INTO narrative_fts(sha, body) VALUES(?,?)",
                               (_KEY + turn_id, safe))
            cache.conn.commit()
        except Exception:                      # noqa: BLE001 容错红线:索引失败不崩
            cache.conn.rollback()


def _row(r):
    try:                                       # 坏 cited_shas JSON 降级为空引用,不崩取 turn
        cited = json.loads(r[6]) if r[6] else []
    except (json.JSONDecodeError, TypeError):
        cited = []
    return {"turn_id": r[0], "conv_id": r[1], "project": r[2], "ts": r[3],
            "role": r[4], "text": r[5], "cited_shas": cited}


def get_turn(cache, turn_id):
    _ensure(cache)
    row = cache.conn.execute(
        "SELECT turn_id,conv_id,project,ts,role,text,cited_shas "
        "FROM web_conversations WHERE turn_id=?", (turn_id,)).fetchone()
    return _row(row) if row else None


def list_conversation(cache, conv_id):
    _ensure(cache)
    rows = cache.conn.execute(
        "SELECT turn_id,conv_id,project,ts,role,text,cited_shas "
        "FROM web_conversations WHERE conv_id=? ORDER BY ts, turn_id",
        (conv_id,)).fetchall()
    return [_row(r) for r in rows]


def is_conv_key(sha):
    return isinstance(sha, str) and sha.startswith(_KEY)


def turn_id_of(key):
    return key[len(_KEY):]
