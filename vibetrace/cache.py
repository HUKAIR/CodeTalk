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
    sealed_date TEXT, open_date TEXT, opened_date TEXT, outcome TEXT);
CREATE TABLE IF NOT EXISTS reviewed (
    project TEXT, sha TEXT, reviewed_at TEXT,
    PRIMARY KEY (project, sha));
"""


class Cache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self._migrate()
        self.conn.executescript(SCHEMA)

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
        """(已开启数, 已回填数) —— 设计文档点名的北极星指标『回填率』。"""
        opened = self.conn.execute(
            "SELECT COUNT(*) FROM capsules WHERE project=? AND opened_date "
            "IS NOT NULL", (project,)).fetchone()[0]
        filled = self.conn.execute(
            "SELECT COUNT(*) FROM capsules WHERE project=? AND opened_date "
            "IS NOT NULL AND outcome IS NOT NULL", (project,)).fetchone()[0]
        return opened, filled

    def pending_capsules(self, project):
        """已到期开启、但用户还没回填的胶囊(供开工简报『待验证的预测』)。"""
        rows = self.conn.execute(
            "SELECT sha, risk, sealed_date FROM capsules WHERE project=? "
            "AND opened_date IS NOT NULL AND outcome IS NULL "
            "ORDER BY open_date", (project,)).fetchall()
        return [{"sha": r[0], "risk": r[1], "sealed_date": r[2]} for r in rows]

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

    def close(self):
        self.conn.close()
