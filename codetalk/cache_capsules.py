"""时间胶囊读写(从 cache.py 抽出,给主模块留 <300 行余量)。

CapsuleMixin 混入 Cache,依赖 self.conn(sqlite 连接)。risk 密封 → 到期开启,
闭合预测-验证环。从 cache.py 抽出以给主模块留 <300 行余量。
"""
from .config import redact_secrets


class CapsuleMixin:
    def seal_capsule(self, project, sha, risk_idx, risk, sealed_date, open_date):
        # INSERT OR IGNORE: 同日重跑不重置已有胶囊(opened_date 保持),不复制
        self.conn.execute(
            "INSERT OR IGNORE INTO capsules VALUES (?,?,?,?,?,?,?,?)",
            (f"{sha}:{risk_idx}", project, sha, redact_secrets(risk), sealed_date, open_date,
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
        """(已开启数, 已回填数)。回填率=护栏指标(仪式,非价值;北极星=防事故拦截)。"""
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
