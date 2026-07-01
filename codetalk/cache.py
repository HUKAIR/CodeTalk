"""SQLite cache: commit narratives are immutable by SHA; session summaries
update incrementally by (session_id, last_msg_ts)."""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import redact_data, redact_secrets
from .fts import backfill, fts_body, search

log = logging.getLogger("codetalk")

SCHEMA = """
CREATE TABLE IF NOT EXISTS commit_narratives (
    sha TEXT PRIMARY KEY, project TEXT, model TEXT,
    narrative_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS session_enrichments (
    session_id TEXT PRIMARY KEY, last_msg_ts TEXT,
    file_mtime REAL, file_size INTEGER,
    summary_json TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS daily_digests (
    project TEXT, date TEXT, overview TEXT, decision TEXT, created_at TEXT,
    PRIMARY KEY (project, date));
CREATE TABLE IF NOT EXISTS capsules (
    capsule_id TEXT PRIMARY KEY, project TEXT, sha TEXT, risk TEXT,
    sealed_date TEXT, open_date TEXT, opened_date TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS reviewed (
    project TEXT, sha TEXT, reviewed_at TEXT,
    PRIMARY KEY (project, sha));
CREATE TABLE IF NOT EXISTS web_conversations (
    turn_id TEXT PRIMARY KEY, conv_id TEXT, project TEXT, ts TEXT,
    role TEXT, text TEXT, cited_shas TEXT);
"""


class Cache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        # WAL + 等锁:webserve 每请求新连接回写胶囊/reviewed,与并行 digest 写同库
        # 不再 database is locked(读写并发、写者排队等锁而非立即报错)。:memory: 无害降级。
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self._migrate()
        self.conn.executescript(SCHEMA)
        self.fts_ok = self._init_fts()

    def _init_fts(self):
        """建 trigram FTS5 表 + 最小 MATCH 自检(防 fts5 编进但 trigram 未编);失败禁用。"""
        try:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS narrative_fts USING "
                "fts5(sha UNINDEXED, body, tokenize='trigram')")
            self.conn.execute(                          # 自检:trigram 真能查
                "SELECT sha FROM narrative_fts WHERE narrative_fts MATCH ? "
                "LIMIT 1", ('"aaa"',)).fetchone()
            backfill(self.conn)                         # 自愈:补建 FTS 前已缓存的历史叙事
            return True
        except sqlite3.OperationalError as exc:
            log.warning("FTS5 不可用(%s),全文召回禁用", exc)
            return False

    def _migrate(self):
        # 旧版 capsules 缺 opened_date / outcome 列。CREATE IF NOT EXISTS 不
        # 改已存在的表 → 旧库缺列会在 digest 时崩溃。胶囊是可由 risks 重新密封的
        # 反思数据,直接丢弃旧表让 SCHEMA 重建;seal-guard(只密封未来到期的)保证
        # open_date≤today 的陈年 commit 不被补密封,旧胶囊不会复活成洪流。
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(capsules)")]
        if cols and ("opened_date" not in cols or "outcome" not in cols):
            self.conn.execute("DROP TABLE capsules")
            self.conn.commit()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def get_narrative(self, sha):
        row = self.conn.execute(
            "SELECT narrative_json FROM commit_narratives WHERE sha=?",
            (sha,)).fetchone()
        return json.loads(row[0]) if row else None

    def put_narrative(self, sha, project, model, narrative):
        # 落盘前统一脱敏:无论叙事来自哪条路径(LLM/trivial stub/digest/course),
        # secret 都不进 cache.db —— M0 隐私红线对缓存存储这一面的单点收口。
        # 脱敏在 json.dumps 之前(对原始字符串叶子):dumps 会把 " 转义成 \\",
        # 若先 dumps 后 redact,key="value" 形式的 secret 会因引号被转义而漏网。
        payload = json.dumps(redact_data(narrative), ensure_ascii=False)
        self.conn.execute(
            "INSERT OR REPLACE INTO commit_narratives VALUES (?,?,?,?,?)",
            (sha, project, model, payload, self._now()))
        self.conn.commit()
        # 主表 commit 后同步 FTS 派生索引(DELETE+INSERT 幂等);写失败只 warning 不回滚主
        # 写(M0 容错红线);body 取原始 dict 此处再脱敏(主表存的 JSON 才已脱敏)。
        if self.fts_ok:
            try:
                body = redact_secrets(fts_body(narrative))  # 先构建:失败则根本不动 FTS 表
                self.conn.execute("DELETE FROM narrative_fts WHERE sha=?", (sha,))
                self.conn.execute("INSERT INTO narrative_fts(sha, body) VALUES(?,?)",
                                  (sha, body))
                self.conn.commit()
            except Exception as exc:
                self.conn.rollback()  # 撤销挂起的 DELETE,免被下次 put 的 commit 误刷丢索引
                log.warning("FTS 写入 %s 失败(%s),已跳过全文索引", sha[:7], exc)

    def set_narrative_evidence(self, sha, evidence):
        """零-LLM 给已存叙事补 evidence 原话锚点(不动 LLM 的 why/decisions,守 immutable;落库前脱敏)。"""
        row = self.conn.execute(
            "SELECT narrative_json FROM commit_narratives WHERE sha=?", (sha,)).fetchone()
        if not row:
            return
        n = json.loads(row[0]); n["evidence"] = redact_data(evidence)
        self.conn.execute("UPDATE commit_narratives SET narrative_json=? WHERE sha=?",
                          (json.dumps(n, ensure_ascii=False), sha))
        self.conn.commit()

    def search_narratives(self, query, project=None, limit=8):
        """主题级内容召回(委托 fts.search;project 非空→按项目隔离,多仓共享 cache 不跨仓泄漏)。"""
        return search(self.conn, self.fts_ok, query, project, limit)

    def get_session(self, session_id):
        row = self.conn.execute(
            "SELECT file_mtime, file_size, summary_json "
            "FROM session_enrichments WHERE session_id=?",
            (session_id,)).fetchone()
        if not row:
            return None
        return {"mtime": row[0], "size": row[1], "summary": json.loads(row[2])}

    def put_session(self, session_id, last_msg_ts, mtime, size, summary):
        self.conn.execute(
            "INSERT OR REPLACE INTO session_enrichments VALUES (?,?,?,?,?,?)",
            (session_id, last_msg_ts, mtime, size,
             json.dumps(summary, ensure_ascii=False), self._now()))
        self.conn.commit()

    # ---- daily digest index: On This Day 回流的检索底座 ----
    def get_daily(self, project, date):
        row = self.conn.execute(
            "SELECT overview, decision FROM daily_digests "
            "WHERE project=? AND date=?", (project, date)).fetchone()
        return {"overview": row[0], "decision": row[1]} if row else None

    def put_daily(self, project, date, overview, decision):
        self.conn.execute(
            "INSERT OR REPLACE INTO daily_digests VALUES (?,?,?,?,?)",
            (project, date, overview, decision, self._now()))
        self.conn.commit()

    # ---- time capsules: risk 密封 → 到期开启,闭合预测-验证环 ----
    def seal_capsule(self, project, sha, risk_idx, risk, sealed_date, open_date):
        # INSERT OR IGNORE: 同日重跑不重置已有胶囊(opened_date 保持),不复制
        self.conn.execute(
            "INSERT OR IGNORE INTO capsules VALUES (?,?,?,?,?,?,?,?)",
            (f"{sha}:{risk_idx}", project, sha, risk, sealed_date, open_date,
             None, None))
        self.conn.commit()

    def open_due_capsules(self, project, today, limit=None):
        """当天开启的胶囊盖 opened_date=today,该日报告稳定复现同一组。
        limit=None:把当日所有到期(open_date<=today)的胶囊一次全开——多日回放
        用此,避免 3 枚硬上限把溢出胶囊错算到下一个『有 commit 的』历史日;
        limit=N:实时单日削峰,溢出留次日,不丢不洪流。"""
        if limit is None:
            ids = [r[0] for r in self.conn.execute(
                "SELECT capsule_id FROM capsules WHERE project=? "
                "AND opened_date IS NULL AND open_date<=? ORDER BY open_date",
                (project, today))]
        else:
            already = self.conn.execute(
                "SELECT COUNT(*) FROM capsules WHERE project=? AND opened_date=?",
                (project, today)).fetchone()[0]
            budget = max(0, limit - already)
            ids = [r[0] for r in self.conn.execute(
                "SELECT capsule_id FROM capsules WHERE project=? "
                "AND opened_date IS NULL AND open_date<=? "
                "ORDER BY open_date LIMIT ?",
                (project, today, budget))] if budget else []
        if ids:
            self.conn.executemany(
                "UPDATE capsules SET opened_date=? WHERE capsule_id=?",
                [(today, i) for i in ids])
            self.conn.commit()
        rows = self.conn.execute(
            "SELECT capsule_id, sha, risk, sealed_date, outcome FROM capsules "
            "WHERE project=? AND opened_date=? ORDER BY open_date",
            (project, today)).fetchall()
        return [{"capsule_id": r[0], "sha": r[1], "risk": r[2],
                 "sealed_date": r[3], "outcome": r[4]} for r in rows]

    def set_capsule_outcome(self, capsule_id, outcome, project):
        """把用户在日报里勾选的回填答案写回缓存,闭合预测-验证环。
        加 project 条件:capsule_id=sha:idx 是全表主键,无项目过滤会跨项目串写。"""
        self.conn.execute(
            "UPDATE capsules SET outcome=? WHERE capsule_id=? AND project=?",
            (outcome, capsule_id, project))
        self.conn.commit()

    def capsule_fill_stats(self, project):
        """(已开启数, 已回填数)。回填率=护栏指标(非北极星;北极星=回面后实际处理率)。"""
        opened = self.conn.execute(
            "SELECT COUNT(*) FROM capsules WHERE project=? AND opened_date "
            "IS NOT NULL", (project,)).fetchone()[0]
        filled = self.conn.execute(
            "SELECT COUNT(*) FROM capsules WHERE project=? AND opened_date "
            "IS NOT NULL AND outcome IS NOT NULL", (project,)).fetchone()[0]
        return opened, filled

    def pending_capsules(self, project):
        """已到期开启、但用户还没回填的胶囊(供开工简报/控制台『待验证的预测』)。
        必带 capsule_id:console 回写要按它精确寻址,缺则多风险胶囊只能写到第 0 枚。"""
        rows = self.conn.execute(
            "SELECT capsule_id, sha, risk, sealed_date FROM capsules WHERE project=? "
            "AND opened_date IS NOT NULL AND outcome IS NULL "
            "ORDER BY open_date", (project,)).fetchall()
        return [{"capsule_id": r[0], "sha": r[1], "risk": r[2], "sealed_date": r[3]}
                for r in rows]

    def all_capsules(self, project):
        """项目全部已密封胶囊(供时光隧道注入已答状态、即时回写)。"""
        rows = self.conn.execute(
            "SELECT capsule_id, sha, risk, outcome, opened_date FROM capsules "
            "WHERE project=?", (project,)).fetchall()
        return [{"capsule_id": r[0], "sha": r[1], "risk": r[2],
                 "outcome": r[3], "opened": bool(r[4])} for r in rows]

    def recent_open_loops(self, project, limit=10):
        """最近若干条 commit 叙事里的未闭环项,去重(供开工简报『悬而未决』)。
        排除 digest:/ask:/course:/graph: 派生行——它们与 commit 叙事同表却无 open_loops,会挤占名额。"""
        rows = self.conn.execute(
            "SELECT narrative_json FROM commit_narratives WHERE project=? "
            "AND sha NOT LIKE 'digest:%' AND sha NOT LIKE 'ask:%' "
            "AND sha NOT LIKE 'course:%' AND sha NOT LIKE 'graph:%' "
            "ORDER BY created_at DESC LIMIT ?", (project, limit)).fetchall()
        loops = []
        for (raw,) in rows:
            try:
                loops += json.loads(raw).get("open_loops", []) or []
            except (ValueError, AttributeError):
                continue
        # 滤掉 LLM 的「材料不足」填充与空白项,简报不堆噪声墙
        return [l for l in dict.fromkeys(loops)
                if str(l).strip() and not str(l).strip().startswith("材料不足")]

    def latest_daily(self, project):
        """最近一天的概览+决定(供开工简报『你上次停在哪』)。"""
        row = self.conn.execute(
            "SELECT date, overview, decision FROM daily_digests WHERE "
            "project=? ORDER BY date DESC LIMIT 1", (project,)).fetchone()
        return ({"date": row[0], "overview": row[1], "decision": row[2]}
                if row else None)

    # ---- reviewed: 你回看了哪些 commit(理解债的『还债』信号)----
    def mark_reviewed(self, project, sha):
        """隧道 serve 模式点开某 commit 叙事时回写。全新表,无旧库迁移问题。"""
        self.conn.execute("INSERT OR REPLACE INTO reviewed VALUES (?,?,?)",
                          (project, sha, self._now()))
        self.conn.commit()

    def reviewed_shas(self, project):
        """{sha: reviewed_at} —— 供理解债算『回看行为』与时间衰减。"""
        return {r[0]: r[1] for r in self.conn.execute(
            "SELECT sha, reviewed_at FROM reviewed WHERE project=?", (project,))}

    def rekey_project(self, old, new):
        """把胶囊/日报/reviewed 三表的 project 键从 old 迁到 new(同名项目串键修复
        的一次性迁移;commit_narratives 本就用全路径,无需迁)。idempotent。"""
        if old == new:
            return
        for tbl in ("capsules", "daily_digests", "reviewed"):
            self.conn.execute("UPDATE " + tbl + " SET project=? WHERE project=?",
                              (new, old))
        self.conn.commit()

    def distinct_projects(self):
        """所有项目绝对路径(供 brief --all 跨项目发现),去重升序。
        LIKE '/%' 只取绝对路径键:graph/ask/course 把 basename 写进了
        commit_narratives.project(幻影),必须滤掉(见 spec F2)。"""
        rows = self.conn.execute(
            "SELECT project FROM commit_narratives WHERE project LIKE '/%' "
            "UNION SELECT project FROM daily_digests WHERE project LIKE '/%' "
            "UNION SELECT project FROM capsules WHERE project LIKE '/%'"
        ).fetchall()
        return sorted(r[0] for r in rows)

    def __enter__(self): return self
    def __exit__(self, *_exc): self.close()
    def __del__(self):
        try: self.close()
        except Exception: pass

    def close(self):
        conn = getattr(self, "conn", None)
        if conn is not None:
            conn.close()
            self.conn = None
