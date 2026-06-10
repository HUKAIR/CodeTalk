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
"""


class Cache:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

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

    def close(self):
        self.conn.close()
