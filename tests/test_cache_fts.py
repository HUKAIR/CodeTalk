"""FTS5 内容召回测试:put_narrative 同步进 narrative_fts、search_narratives 召回。

覆盖中文 trigram 召回(必须真通过)、MATCH 转义崩溃用例、fts_ok 降级、
<3 字符有效 term 走空、脱敏继承。纯内存、纯 stdlib(sqlite3)。
"""
import os
import shutil
import tempfile
import unittest
from unittest import mock

from codetalk.cache import Cache


class TestFtsProbe(unittest.TestCase):
    def test_fts_ok_true_on_this_machine(self):
        # 本机已核实 ENABLE_FTS5 + trigram;自检应通过
        self.assertTrue(Cache(":memory:").fts_ok)

    def test_fts_ok_false_degrades_search_to_empty(self):
        c = Cache(":memory:")
        c.fts_ok = False
        c.put_narrative("s1", "P", "m", {"why": "用乐观锁避免超时"})
        self.assertEqual(c.search_narratives("乐观锁"), [])


class TestChineseRecall(unittest.TestCase):
    def test_chinese_keyword_recalls_its_sha(self):
        c = Cache(":memory:")
        c.put_narrative("sha_lock", "P", "m", {"why": "用乐观锁避免超时"})
        c.put_narrative("sha_other", "P", "m", {"why": "改用批量写入降低开销"})
        hits = c.search_narratives("乐观锁")
        self.assertIn("sha_lock", hits)
        self.assertNotIn("sha_other", hits)

    def test_chinese_term_inside_a_sentence_query(self):
        # 用户输入整句问题,内含中文关键词 → 切 term 后仍召回
        c = Cache(":memory:")
        c.put_narrative("sha_lock", "P", "m", {"why": "用乐观锁避免超时"})
        self.assertIn("sha_lock", c.search_narratives("当初为什么用乐观锁"))

    def test_recall_from_decisions_field(self):
        c = Cache(":memory:")
        c.put_narrative("sha_d", "P", "m",
                        {"why": "无关", "decisions": ["选用幂等去重策略"]})
        self.assertIn("sha_d", c.search_narratives("幂等去重"))

    def test_english_keyword_recall(self):
        c = Cache(":memory:")
        c.put_narrative("sha_e", "P", "m", {"why": "use optimistic locking"})
        self.assertIn("sha_e", c.search_narratives("optimistic"))


class TestMatchEscapingNoCrash(unittest.TestCase):
    def setUp(self):
        self.c = Cache(":memory:")
        self.c.put_narrative("s1", "P", "m", {"why": "用乐观锁避免超时"})

    def test_question_mark_no_crash(self):
        self.assertIsInstance(self.c.search_narratives("乐观锁?"), list)

    def test_bare_quote_no_crash(self):
        self.assertIsInstance(self.c.search_narratives('乐观锁"注入'), list)

    def test_parens_and_colon_no_crash(self):
        self.assertIsInstance(self.c.search_narratives("(乐观锁):x"), list)

    def test_minus_and_caret_no_crash(self):
        self.assertIsInstance(self.c.search_narratives("-乐观锁 ^x"), list)

    def test_pure_punctuation_returns_empty(self):
        self.assertEqual(self.c.search_narratives("?!()-:\"*^"), [])

    def test_bare_or_keyword_no_crash(self):
        # 裸 OR/AND/NOT/NEAR 应被剥离,不作 FTS5 布尔算子
        self.assertIsInstance(self.c.search_narratives("OR AND NOT"), list)

    def test_star_wildcard_stripped_no_crash(self):
        self.assertIsInstance(self.c.search_narratives("乐观锁*"), list)


class TestShortTerms(unittest.TestCase):
    def test_sub3_char_term_returns_empty(self):
        c = Cache(":memory:")
        c.put_narrative("s1", "P", "m", {"why": "用乐观锁避免超时"})
        self.assertEqual(c.search_narratives("ab"), [])   # <3 有效 term → 空

    def test_two_char_cjk_recalled_via_like_fallback(self):
        # 2 字中文 trigram 无 shingle、MATCH 召不回 → LIKE 回退召回(脱敏/缓存 等高频词)
        c = Cache(":memory:")
        c.put_narrative("s1", "P", "m", {"why": "用乐观锁避免超时"})
        self.assertEqual(c.search_narratives("乐观"), ["s1"])

    def test_two_char_cjk_absent_returns_empty(self):
        c = Cache(":memory:")
        c.put_narrative("s1", "P", "m", {"why": "用乐观锁避免超时"})
        self.assertEqual(c.search_narratives("幂等"), [])  # body 无『幂等』→ LIKE 不命中


class TestRedactionInherited(unittest.TestCase):
    def test_fts_body_inherits_redaction(self):
        c = Cache(":memory:")
        c.put_narrative("s_secret", "P", "m",
                        {"why": "key 是 sk-abcdefghijklmnop1234 用于鉴权"})
        # FTS body 取自已脱敏 narrative_json:明文 secret 不应被召回
        self.assertEqual(c.search_narratives("sk-abcdefghijklmnop1234"), [])
        row = c.conn.execute(
            "SELECT body FROM narrative_fts WHERE sha=?", ("s_secret",)).fetchone()
        self.assertIsNotNone(row)
        self.assertNotIn("sk-abcdefghijklmnop1234", row[0])
        self.assertIn("[REDACTED]", row[0])


class TestFtsWriteFaultTolerant(unittest.TestCase):
    def test_fts_write_failure_does_not_break_main_write(self):
        from codetalk import cache as cache_mod
        c = Cache(":memory:")
        # 让 FTS body 拼接崩,主表写仍须成功(派生索引绝不拖垮主写)
        with mock.patch.object(cache_mod, "fts_body",
                               side_effect=RuntimeError("boom")):
            c.put_narrative("s_main", "P", "m", {"why": "正常意图"})
        self.assertIsNotNone(c.get_narrative("s_main"))   # 主写未回滚

    def test_reput_body_failure_keeps_existing_fts_row(self):
        # 已索引 SHA 再 put 时 body 构建失败,不得丢掉原 FTS 行(body 先建 + 回滚保护)
        from codetalk import cache as cache_mod
        c = Cache(":memory:")
        c.put_narrative("s_keep", "P", "m", {"why": "用乐观锁避免超时"})
        self.assertIn("s_keep", c.search_narratives("乐观锁"))   # 原本可召回
        with mock.patch.object(cache_mod, "fts_body",
                               side_effect=RuntimeError("boom")):
            c.put_narrative("s_keep", "P", "m", {"why": "改写"})  # body 崩
        c.put_narrative("s_other", "P", "m", {"why": "幂等去重"})  # 触发后续 commit
        self.assertIn("s_keep", c.search_narratives("乐观锁"))   # 原 FTS 行仍在


class TestFtsUpsert(unittest.TestCase):
    def test_reput_same_sha_no_duplicate_rows(self):
        c = Cache(":memory:")
        c.put_narrative("s1", "P", "m", {"why": "用乐观锁避免超时"})
        c.put_narrative("s1", "P", "m", {"why": "改用悲观锁"})  # 覆盖
        cnt = c.conn.execute(
            "SELECT COUNT(*) FROM narrative_fts WHERE sha=?", ("s1",)).fetchone()[0]
        self.assertEqual(cnt, 1)
        self.assertEqual(c.search_narratives("悲观锁"), ["s1"])
        self.assertEqual(c.search_narratives("乐观锁"), [])    # 旧 body 已删


class TestFtsBackfill(unittest.TestCase):
    """建 FTS 写入逻辑前就已缓存的 commit 叙事(SHA 键 immutable、永不重写)
    不会被补索引,导致 search/接地对话召不回。重开 Cache 应一次性自愈回填。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "cache.db")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _legacy(self, sha, narrative_json):
        # 模拟「只在主表、不在 FTS」的旧叙事:直写主表 + 从 FTS 抹掉
        c = Cache(self.db)
        if not c.fts_ok:
            self.skipTest("FTS5 trigram 不可用")
        c.conn.execute("INSERT INTO commit_narratives VALUES (?,?,?,?,?)",
                       (sha, "/p", "m", narrative_json, "t"))
        c.conn.execute("DELETE FROM narrative_fts WHERE sha=?", (sha,))
        c.conn.commit()
        c.close()

    def test_preexisting_narrative_backfilled_on_reopen(self):
        sha = "a" * 40
        self._legacy(sha, '{"why": "为什么要做时光轴线性时间线", '
                          '"decisions": ["脱敏在编码前"]}')
        c2 = Cache(self.db)                        # 重开 → _init_fts 自愈回填
        self.assertIn(sha, c2.search_narratives("时光轴"))
        c2.close()

    def test_backfill_excludes_derived_keys(self):
        c = Cache(self.db)
        if not c.fts_ok:
            self.skipTest("FTS5 不可用")
        c.conn.execute("INSERT INTO commit_narratives VALUES (?,?,?,?,?)",
                       ("graph:" + "b" * 40, "/p", "graph", '{"nodes": []}', "t"))
        c.conn.commit()
        c.close()
        c2 = Cache(self.db)                        # 回填只认真实 SHA,派生键(含 ':')跳过
        n = c2.conn.execute(
            "SELECT COUNT(*) FROM narrative_fts WHERE sha LIKE 'graph:%'").fetchone()[0]
        c2.close()
        self.assertEqual(n, 0)

    def test_backfill_idempotent_no_duplicates(self):
        sha = "c" * 40
        self._legacy(sha, '{"why": "用幂等去重保证一致"}')
        Cache(self.db).close()                    # 第一次回填
        c3 = Cache(self.db)                        # 第二次:anti-join 命中 0,不重复插
        cnt = c3.conn.execute(
            "SELECT COUNT(*) FROM narrative_fts WHERE sha=?", (sha,)).fetchone()[0]
        c3.close()
        self.assertEqual(cnt, 1)

    def test_backfill_redacts_legacy_unredacted_narrative(self):
        # 红线:redact_data 落库前缓存的旧叙事可能未脱敏;回填进 FTS 前必须再脱敏
        sha = "d" * 40
        self._legacy(sha, '{"why": "旧 key sk-abcdefghijklmnop1234 未脱敏入库"}')
        c2 = Cache(self.db)
        row = c2.conn.execute(
            "SELECT body FROM narrative_fts WHERE sha=?", (sha,)).fetchone()
        c2.close()
        self.assertIsNotNone(row)                              # 已回填
        self.assertNotIn("sk-abcdefghijklmnop1234", row[0])    # 明文 secret 不入 FTS


if __name__ == "__main__":
    unittest.main()
