"""recap(会话摘要)测试:全部用合成 jsonl 夹具,绝不引用真实会话数据(公开仓红线)。

覆盖:轮切分(真实用户 vs 系统伪装标记)、结论行启发式与截断、isSidechain 过滤、
每轮起始时间戳(单调不减)、流式索引元信息(scan_meta,含合成大文件)、
索引页(日期分组/链接态/命令提示)+ 详情页(锚点=轮数/筛选 chips/迷你日程图)、
植入假 API key 双页脱敏断言、会话挑选、容错解析、CLI 注册。
"""
import json
import os
import shutil
import tempfile
import unittest

from codetalk.ui_template import read_template
from pathlib import Path
from unittest import mock

from codetalk import recap, recap_render
from codetalk.sessions import project_slug

TS = "2026-07-27T10:00:00Z"
TS_D1 = "2026-07-26T04:00:00Z"     # 相邻几天同一时刻:任何固定时区下都是不同本地日期
TS_D2 = "2026-07-27T04:00:00Z"
TS_D3 = "2026-07-28T04:00:00Z"


def _local_day(ts):
    """页面按本机时区分日;测试期望值同源计算,不写死日期字面量。"""
    from datetime import datetime
    return f"{datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone():%Y-%m-%d}"


def _user(text, **extra):
    return {"type": "user", "timestamp": TS, "sessionId": "sess-1",
            "message": {"role": "user", "content": text}, **extra}


def _asst(blocks, **extra):
    return {"type": "assistant", "timestamp": TS,
            "message": {"content": blocks}, **extra}


def _text(t):
    return {"type": "text", "text": t}


def _tool(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
                    encoding="utf-8")


class RecapBase(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def _session_file(self, rows, name="sess-1"):
        p = self.d / f"{name}.jsonl"
        _write(p, rows)
        return p


class TestTurnSplit(RecapBase):
    def test_system_disguised_user_rows_do_not_open_turns(self):
        # 4 种文本标记 + isMeta 旗标,全都不得开新轮
        rows = [
            _user("修复解析 bug"),
            _asst([_text("已修复。")]),
            _user("<system-reminder>注入的上下文</system-reminder>"),
            _user("[Request interrupted by user]"),
            _user("Stop hook feedback: 某钩子输出"),
            _user("前置文字 <local-command-stdout>命令回显</local-command-stdout>"),
            _user("isMeta 行", isMeta=True),
            _user("第二个真问题"),
        ]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual([t["kind"] for t in s["turns"]], ["real", "real"])
        self.assertIn("修复解析 bug", s["turns"][0]["ask"])
        self.assertIn("第二个真问题", s["turns"][1]["ask"])

    def test_command_row_opens_command_turn(self):
        rows = [_user("<command-name>/review</command-name>"
                      "<command-args>--fast</command-args>")]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(s["turns"][0]["kind"], "command")
        self.assertEqual(s["turns"][0]["ask"], "/review --fast")

    def test_tool_result_row_does_not_open_turn(self):
        rows = [_user("真问题"),
                _user([{"type": "tool_result", "tool_use_id": "t1",
                        "content": "工具输出"}])]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(len(s["turns"]), 1)

    def test_block_list_user_content_supported(self):
        rows = [_user([_text("块列表形式的问题")])]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(len(s["turns"]), 1)
        self.assertIn("块列表形式的问题", s["turns"][0]["ask"])


class TestConclusion(RecapBase):
    def test_conclusion_from_last_text_block_first_valid_line(self):
        rows = [_user("问"),
                _asst([_text("中途汇报一下。")]),
                _asst([_text("---\n\n### \n结论 A。结论 B。")])]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(s["turns"][0]["concl"], "结论 A。")

    def test_ascii_period_cut(self):
        rows = [_user("q"), _asst([_text("Fixed the parser. More detail here.")])]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(s["turns"][0]["concl"], "Fixed the parser.")

    def test_120_char_cut_when_no_period(self):
        line = "结" * 200
        rows = [_user("q"), _asst([_text(line)])]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(s["turns"][0]["concl"], line[:120] + "…")

    def test_thinking_blocks_ignored(self):
        rows = [_user("q"),
                _asst([{"type": "thinking", "thinking": "内心独白勿入"},
                       _text("对外结论。")])]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(s["turns"][0]["concl"], "对外结论。")
        self.assertNotIn("内心独白勿入", s["turns"][0]["full"])


class TestSidechainAndTools(RecapBase):
    def test_sidechain_rows_filtered(self):
        rows = [_user("主线问题"),
                _asst([_text("主线结论。")]),
                _asst([_text("侧链噪音。")], isSidechain=True),
                _user("侧链用户行", isSidechain=True)]
        s = recap.parse_session(self._session_file(rows))
        self.assertEqual(len(s["turns"]), 1)
        self.assertEqual(s["turns"][0]["concl"], "主线结论。")
        self.assertNotIn("侧链噪音", s["turns"][0]["full"])

    def test_tools_and_files_counted(self):
        rows = [_user("改文件"),
                _asst([_tool("Edit", file_path="/p/codetalk/a.py"),
                       _tool("Edit", file_path="/p/codetalk/a.py"),
                       _tool("Bash", command="ls"),
                       _text("改完了。")])]
        s = recap.parse_session(self._session_file(rows))
        t = s["turns"][0]
        self.assertEqual(t["tools"]["Edit"], 2)
        self.assertEqual(t["tools"]["Bash"], 1)
        self.assertEqual(t["files"], {"a.py": "/p/codetalk/a.py"})

    def test_garbage_lines_never_crash(self):
        p = self.d / "sess-1.jsonl"
        p.write_text('不是 json\n"裸字符串"\n'
                     + json.dumps(_user("好问题")) + "\n"
                     + json.dumps({"type": "没见过的类型"}) + "\n",
                     encoding="utf-8")
        s = recap.parse_session(p)
        self.assertEqual(len(s["turns"]), 1)
        self.assertEqual(s["parse_failures"], 2)


class TestTurnTimestamps(RecapBase):
    def test_turn_ts_monotonic_and_fallback(self):
        rows = [_user("第一问", timestamp=TS_D1),
                _asst([_text("答一。")], timestamp="2026-07-26T05:00:00Z"),
                _user("无时间戳的第二问", timestamp=None),   # 回落到上一条已见时间
                _asst([_text("答二。")], timestamp=TS_D2),
                _user("第三问", timestamp=TS_D2)]
        s = recap.parse_session(self._session_file(rows))
        tss = [t["ts"] for t in s["turns"]]
        self.assertEqual(len(tss), 3)
        self.assertTrue(all(t is not None for t in tss))
        for a, b in zip(tss, tss[1:]):                        # 单调不减
            self.assertLessEqual(a, b)


class TestScanMeta(RecapBase):
    def test_meta_span_turns_previews_size(self):
        rows = [_user("真实提问一", timestamp=TS_D1),
                _asst([_text("答。")], timestamp="2026-07-26T05:00:00Z"),
                _user("<command-name>/review</command-name>", timestamp=TS_D2),
                _user("<system-reminder>注入</system-reminder>", timestamp=TS_D2),
                _user("真实提问二", timestamp=TS_D2),
                _user("真实提问三(不入预览)", timestamp=TS_D2)]
        p = self._session_file(rows)
        m = recap.scan_meta(p)
        self.assertEqual(m["sid"], "sess-1")
        self.assertEqual(m["turns"], 4)                       # 命令轮计数,注入不计
        self.assertEqual(len(m["previews"]), 2)               # 前 2 条真实提问
        self.assertIn("真实提问一", m["previews"][0])
        self.assertIn("真实提问二", m["previews"][1])
        self.assertEqual(m["start"].isoformat(), "2026-07-26T04:00:00+00:00")
        self.assertEqual(m["end"].isoformat(), "2026-07-27T04:00:00+00:00")
        self.assertEqual(m["size"], p.stat().st_size)

    def test_large_file_streamed_counts_stay_exact(self):
        # 合成多行大文件:元信息单遍流式取,轮数/预览仍精确
        rows = []
        pad = "x" * 4000
        for i in range(3000):
            rows.append(_user(f"批量问题 {i} {pad}"))
            rows.append(_asst([_text(f"批量回答 {i}。")]))
        p = self._session_file(rows)
        self.assertGreater(p.stat().st_size, 10 * 1024 * 1024)
        m = recap.scan_meta(p)
        self.assertEqual(m["turns"], 3000)
        self.assertIn("批量问题 0", m["previews"][0])
        self.assertIn("批量问题 1", m["previews"][1])

    def test_planted_key_redacted_in_previews(self):
        rows = [_user("我的 key 是 sk-test1234567890abcdef 帮我查")]
        m = recap.scan_meta(self._session_file(rows))
        self.assertNotIn("sk-test1234567890abcdef", m["previews"][0])


class RenderBase(RecapBase):
    """双页渲染环境:CLAUDE_PROJECTS 与 vault 全指临时目录,绝不碰真实数据。"""

    def _make_env(self, sessions):
        proj = self.d / "proj"
        proj.mkdir(exist_ok=True)
        root = self.d / "claude-projects"
        sess_dir = root / project_slug(proj)
        sess_dir.mkdir(parents=True, exist_ok=True)
        for i, (name, rows) in enumerate(sessions):
            p = sess_dir / f"{name}.jsonl"
            _write(p, rows)
            os.utime(p, (1000 + i, 1000 + i))                 # 依次变新
        return proj, root, self.d / "vault"

    def _render(self, proj, root, vault, session=None):
        with mock.patch.object(recap, "CLAUDE_PROJECTS", root), \
             mock.patch.object(recap_render, "load_config",
                               return_value={"vault_path": str(vault)}):
            return recap_render.render_recap(proj, session=session)

    def _two_sessions(self):
        old = [_user("旧会话的问题", timestamp=TS_D1),
               _asst([_text("旧结论。")], timestamp=TS_D1)]
        new = [_user("新会话问一", timestamp=TS_D2),
               _asst([_text("答一。"), _tool("Edit", file_path="/p/a.py")],
                     timestamp=TS_D2),
               _user("<command-name>/x</command-name>", timestamp=TS_D3),
               _user("新会话问三", timestamp=TS_D3),
               _asst([_text("答三。")], timestamp=TS_D3)]
        return self._make_env([("aaaa1111", old), ("bbbb2222", new)])


class TestIndexPage(RenderBase):
    def test_default_writes_index_and_latest_detail(self):
        proj, root, vault = self._two_sessions()
        paths, err = self._render(proj, root, vault)
        self.assertIsNone(err)
        index, detail = paths
        self.assertEqual(index.name, "proj-recap.html")
        self.assertEqual(detail.name, "proj-recap-bbbb2222.html")
        page = index.read_text(encoding="utf-8")
        self.assertEqual(page.count('class="sess'), 2)        # 两张会话卡
        self.assertIn('href="proj-recap-bbbb2222.html"', page)  # 已生成 → 可点
        self.assertIn("codetalk recap --session aaaa1111", page)  # 未生成 → 命令提示
        self.assertNotIn('href="proj-recap-aaaa1111.html"', page)
        # 日期分组,新在前
        self.assertLess(page.index(_local_day(TS_D2)), page.index(_local_day(TS_D1)))
        self.assertIn("新会话问一", page)                      # 真实提问预览
        self.assertIn("新会话问三", page)

    def test_session_flag_generates_named_detail_and_refreshes_index(self):
        proj, root, vault = self._two_sessions()
        paths, err = self._render(proj, root, vault, session="aaaa")
        self.assertIsNone(err)
        self.assertEqual(paths[1].name, "proj-recap-aaaa1111.html")
        page = paths[0].read_text(encoding="utf-8")
        self.assertIn('href="proj-recap-aaaa1111.html"', page)
        self.assertIn("codetalk recap --session bbbb2222", page)
        paths2, _ = self._render(proj, root, vault)           # 再默认跑 → 双卡都可点
        page2 = paths2[0].read_text(encoding="utf-8")
        self.assertIn('href="proj-recap-aaaa1111.html"', page2)
        self.assertIn('href="proj-recap-bbbb2222.html"', page2)

    def test_session_miss_reports_error(self):
        proj, root, vault = self._two_sessions()
        paths, err = self._render(proj, root, vault, session="zzz")
        self.assertIsNone(paths)
        self.assertTrue(err)

    def test_missing_session_dir_reports_error(self):
        proj = self.d / "empty-proj"
        proj.mkdir()
        with mock.patch.object(recap, "CLAUDE_PROJECTS", self.d / "nowhere"), \
             mock.patch.object(recap_render, "load_config",
                               return_value={"vault_path": str(self.d / "v")}):
            paths, err = recap_render.render_recap(proj)
        self.assertIsNone(paths)
        self.assertTrue(err)


class TestDetailPage(RenderBase):
    def _detail(self):
        proj, root, vault = self._two_sessions()
        paths, err = self._render(proj, root, vault)
        assert err is None, err
        return paths[1].read_text(encoding="utf-8")

    def test_anchor_count_equals_turn_count(self):
        page = self._detail()
        self.assertIn('id="back-index" href="proj-recap.html"', page)
        self.assertIn('id="back-index-rail" href="proj-recap.html"', page)
        self.assertEqual(page.count('id="turn-'), 3)          # 锚点数 = 轮数
        self.assertEqual(page.count('href="#turn-'), 3)       # 目录行一一对应

    def test_filter_chips_and_card_facets(self):
        page = self._detail()
        for f in ("all", "ask", "cmd", "edit"):
            self.assertIn(f'data-f="{f}"', page)              # 顶栏筛选 chips
        self.assertIn('data-kind="real"', page)
        self.assertIn('data-kind="command"', page)
        self.assertIn('data-edit="1"', page)                  # 有改动轮可被筛选

    def test_minimap_segments_equal_days_and_jump_targets_exist(self):
        page = self._detail()
        self.assertEqual(page.count('class="seg"'), 2)        # 日程图段数 = 天数
        self.assertEqual(page.count('class="daybar"'), 2)     # 跨日分割条
        for day in (_local_day(TS_D2), _local_day(TS_D3)):
            self.assertIn(f'href="#d-{day}"', page)           # 段点击 → 该日锚点
            self.assertIn(f'id="d-{day}"', page)

    def test_planted_api_key_never_reaches_either_page(self):
        rows = [_user("我的 key 是 sk-test1234567890abcdef 帮我查", timestamp=TS_D1),
                _asst([_text("你的 sk-test1234567890abcdef 已经泄漏。")],
                      timestamp=TS_D1)]
        proj, root, vault = self._make_env([("cccc3333", rows)])
        paths, err = self._render(proj, root, vault)
        self.assertIsNone(err)
        for p in paths:                                       # 索引页 + 详情页都不含
            page = p.read_text(encoding="utf-8")
            self.assertNotIn("sk-test1234567890abcdef", page)
        self.assertIn("[REDACTED]", paths[1].read_text(encoding="utf-8"))


class TestServeRecap(RenderBase):
    """--serve:每次 GET 现算最新内容,纯读零 vault 写入,链接走 /s/<sid8> 路由。"""

    def _serve(self, proj, root, vault):
        with mock.patch.object(recap, "CLAUDE_PROJECTS", root), \
             mock.patch.object(recap_render, "load_config",
                               return_value={"vault_path": str(vault)}), \
             mock.patch("codetalk.webserve.serve_html", return_value=None) as srv:
            err = recap_render.serve_recap(proj, open_browser=False)
        self.assertIsNone(err)
        srv.assert_called_once()
        _, kwargs = srv.call_args
        self.assertFalse(kwargs.get("open_browser", True))
        return kwargs["builder"], kwargs["routes"]

    def _add_third_session(self, proj, root):
        sess_dir = root / project_slug(proj)
        _write(sess_dir / "cccc3333.jsonl",
               [_user("第三个会话的新问题", timestamp=TS_D3),
                _asst([_text("第三结论。")], timestamp=TS_D3)])

    def test_index_builder_recomputes_and_links_are_routes(self):
        proj, root, vault = self._two_sessions()
        builder, _ = self._serve(proj, root, vault)
        page = builder()
        self.assertEqual(page.count('class="sess'), 2)
        self.assertIn('href="/s/aaaa1111"', page)     # serve 模式全部可点
        self.assertIn('href="/s/bbbb2222"', page)
        self.assertNotIn("codetalk recap --session", page)  # 没有「未生成」占位
        self._add_third_session(proj, root)           # 新会话出现 → 刷新即见
        page2 = builder()
        self.assertEqual(page2.count('class="sess'), 3)
        self.assertIn('href="/s/cccc3333"', page2)
        self.assertIn("第三个会话的新问题", page2)

    def test_detail_route_computes_on_demand_even_for_new_sessions(self):
        proj, root, vault = self._two_sessions()
        _, routes = self._serve(proj, root, vault)
        page = routes("/s/bbbb2222")()
        self.assertIn('id="back-index" href="/"', page)
        self.assertIn('id="back-index-rail" href="/"', page)
        self.assertEqual(page.count('id="turn-'), 3)  # 锚点数 = 轮数
        self.assertIn("新会话问一", page)
        self._add_third_session(proj, root)           # 无需重启,点击即算
        fn = routes("/s/cccc3333")
        self.assertIsNotNone(fn)
        self.assertIn("第三结论。", fn())
        self.assertIsNone(routes("/s/zzzz9999"))      # 未知会话 → 未命中
        self.assertIsNone(routes("/favicon.ico"))     # 非 /s/ 路径 → 未命中

    def test_serve_never_writes_vault(self):
        proj, root, vault = self._two_sessions()
        builder, routes = self._serve(proj, root, vault)
        builder()
        routes("/s/bbbb2222")()
        self.assertFalse(vault.exists())              # 纯读:不写 vault、不建目录

    def test_planted_key_redacted_in_both_served_pages(self):
        rows = [_user("我的 key 是 sk-test1234567890abcdef 帮我查", timestamp=TS_D1),
                _asst([_text("你的 sk-test1234567890abcdef 已经泄漏。")],
                      timestamp=TS_D1)]
        proj, root, vault = self._make_env([("dddd4444", rows)])
        builder, routes = self._serve(proj, root, vault)
        self.assertNotIn("sk-test1234567890abcdef", builder())
        self.assertNotIn("sk-test1234567890abcdef", routes("/s/dddd4444")())

    def test_missing_session_dir_reports_error_not_raise(self):
        proj = self.d / "empty-proj"
        proj.mkdir()
        with mock.patch.object(recap, "CLAUDE_PROJECTS", self.d / "nowhere"):
            err = recap_render.serve_recap(proj)
        self.assertTrue(err)


class TestSessionPick(RecapBase):
    def _root_with(self, proj, names_rows):
        root = self.d / "claude-projects"
        sess_dir = root / project_slug(proj)
        sess_dir.mkdir(parents=True)
        for i, (name, rows) in enumerate(names_rows):
            p = sess_dir / f"{name}.jsonl"
            _write(p, rows)
            os.utime(p, (1000 + i, 1000 + i))    # 依次变新
        return root

    def test_default_picks_latest_mtime(self):
        proj = self.d / "proj"
        proj.mkdir()
        root = self._root_with(proj, [("old", [_user("旧会话")]),
                                      ("new", [_user("新会话")])])
        with mock.patch.object(recap, "CLAUDE_PROJECTS", root):
            path, err = recap._pick_session(proj)
        self.assertIsNone(err)
        self.assertEqual(path.stem, "new")

    def test_session_prefix_match_and_miss(self):
        proj = self.d / "proj"
        proj.mkdir()
        root = self._root_with(proj, [("abc123", [_user("目标")])])
        with mock.patch.object(recap, "CLAUDE_PROJECTS", root):
            path, err = recap._pick_session(proj, session="abc")
            self.assertIsNone(err)
            self.assertEqual(path.stem, "abc123")
            _, err2 = recap._pick_session(proj, session="zzz")
        self.assertTrue(err2)


class TestConsolePayload(RecapBase):
    def test_payload_bounded_no_fulltext_and_none_on_missing(self):
        proj = self.d / "proj"
        proj.mkdir()
        root = self.d / "claude-projects"
        sess_dir = root / project_slug(proj)
        sess_dir.mkdir(parents=True)
        _write(sess_dir / "s.jsonl", [_user("问"), _asst([_text("答。")])])
        with mock.patch.object(recap, "CLAUDE_PROJECTS", root):
            data = recap.console_payload(proj)
        self.assertEqual(len(data["turns"]), 1)
        self.assertNotIn("full", data["turns"][0])            # 控制台不带全文,守载荷有界
        with mock.patch.object(recap, "CLAUDE_PROJECTS", self.d / "nowhere"):
            self.assertIsNone(recap.console_payload(proj))    # 缺目录降级,不拖垮控制台


class TestConsoleView(unittest.TestCase):
    """console 第 7 视图挂载:VIEWS 导航项 + 渲染函数 + 双语 i18n key 都在位。"""

    def setUp(self):
        self.html = read_template("console.html")

    def test_recap_view_wired_into_console(self):
        self.assertIn('id="v-recap"', self.html)
        self.assertIn('["recap","会话摘要"]', self.html)
        self.assertIn("function renderRecap()", self.html)
        self.assertEqual(self.html.count("renderRecap()"), 3)  # 定义 + 首渲 + 语言切换重渲

    def test_console_assemble_wires_payload(self):
        import inspect
        from codetalk import console
        self.assertIn('data["recap"] = recap.console_payload(pp)',
                      inspect.getsource(console._assemble))


class TestCliWiring(unittest.TestCase):
    def test_recap_registered_in_dispatch_and_parser(self):
        from codetalk import cli
        self.assertIn("recap", cli._DISPATCH)
        args = cli._build_parser().parse_args(["recap", "--session", "abc"])
        self.assertEqual(args.command, "recap")
        self.assertEqual(args.session, "abc")

    def test_recap_serve_flags_parse_and_dispatch(self):
        from codetalk import cli, commands_view
        args = cli._build_parser().parse_args(["recap", "--serve", "--no-open"])
        self.assertTrue(args.serve)
        self.assertTrue(args.no_open)
        args.project = "."
        with mock.patch("codetalk.recap_render.serve_recap",
                        return_value=None) as srv:
            self.assertEqual(commands_view.recap_cmd(args), 0)
        srv.assert_called_once_with(".", open_browser=False)


if __name__ == "__main__":
    unittest.main()
