"""SQLite cache: commit narratives are immutable by SHA; session summaries
update incrementally by (session_id, last_msg_ts)."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
    sealed_date TEXT, open_date TEXT, opened_date TEXT);
"""


class Cache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self._migrate()
        self.conn.executescript(SCHEMA)

    def _migrate(self):
        # 旧版 capsules 用 status 列,本版改 opened_date。CREATE IF NOT EXISTS 不
        # 改已存在的表 → 旧库缺列会在 digest 时崩溃。胶囊是可由 risks 重新密封的
        # 反思数据,直接丢弃旧表让 SCHEMA 重建;seal-guard(只密封未来到期的)保证
        # open_date≤today 的陈年 commit 不被补密封,旧胶囊不会复活成洪流。
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(capsules)")]
        if cols and "opened_date" not in cols:
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
        self.conn.execute(
            "INSERT OR REPLACE INTO commit_narratives VALUES (?,?,?,?,?)",
            (sha, project, model, json.dumps(narrative, ensure_ascii=False),
             self._now()))
        self.conn.commit()

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
            "INSERT OR IGNORE INTO capsules VALUES (?,?,?,?,?,?,?)",
            (f"{sha}:{risk_idx}", project, sha, risk, sealed_date, open_date,
             None))
        self.conn.commit()

    def open_due_capsules(self, project, today, limit=3):
        """同日幂等:当天开启的胶囊盖 opened_date=today,该日报告稳定复现同一组;
        额度 limit 内分页(5 枚到期 → 今日 3、次日 2),不丢不洪流。"""
        already = self.conn.execute(
            "SELECT COUNT(*) FROM capsules WHERE project=? AND opened_date=?",
            (project, today)).fetchone()[0]
        budget = max(0, limit - already)
        if budget:
            ids = [r[0] for r in self.conn.execute(
                "SELECT capsule_id FROM capsules WHERE project=? "
                "AND opened_date IS NULL AND open_date<=? "
                "ORDER BY open_date LIMIT ?", (project, today, budget))]
            if ids:
                self.conn.executemany(
                    "UPDATE capsules SET opened_date=? WHERE capsule_id=?",
                    [(today, i) for i in ids])
                self.conn.commit()
        rows = self.conn.execute(
            "SELECT sha, risk, sealed_date FROM capsules "
            "WHERE project=? AND opened_date=? ORDER BY open_date",
            (project, today)).fetchall()
        return [{"sha": r[0], "risk": r[1], "sealed_date": r[2]} for r in rows]

    def close(self):
        self.conn.close()
