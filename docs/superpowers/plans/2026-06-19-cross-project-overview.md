# 跨项目总览(`brief --all`)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 vibetrace 加 `brief --all`——一个零-LLM 的跨项目"注意力路由",端出所有项目里有到期胶囊的 + 理解债最高的 K 个。

**Architecture:** 发现层 `cache.distinct_projects()`(三表 `LIKE '/%'` UNION,滤 basename 幻影)→ 纯函数 `brief.build_overview(cache, projects, today)`(逐存活项目复用 `cache.pending_capsules` + `debt.debt_board`,取并集、排序、渲染、`redact_secrets`)→ `cli.py` 的 `brief --all` 分支接线。三处改动:`cache.py` / `brief.py` / `cli.py`。

**Tech Stack:** Python 3.11+ 标准库 + sqlite3;stdlib `unittest`;复用 `debt.debt_board` / `cache.pending_capsules` / `config.redact_secrets`。

## Global Constraints

- M0 红线:仅标准库 + anthropic SDK,禁第三方(向量库/Web 框架/agent 框架);出现即违反。
- 单模块 <300 行;超出先停下说明。
- 解析外部数据(git/SQLite)必须容错:失败记警告并降级,绝不崩溃。
- 隐私红线:数据不出本机(LLM 调用除外);**写盘前对 secret 脱敏**。
- 本特性全程**零 LLM**:`grep -n LLMClient vibetrace/brief.py vibetrace/cache.py` 必须为空。
- 测试:stdlib `unittest`;`python3 -m unittest discover -s tests` 全量绿。
- `cache.db` 键约定:commit 叙事以 SHA 为键;`distinct_projects` 只认绝对路径键(`LIKE '/%'`)。
- 关键取舍在 commit message 正文留 `Vibe-Decision:`;需日后验证留 `Vibe-Watch:`(行首、区分大小写)。
- 范围外(不要做):修 graph/ask/course 把 `pp.name` 改 `str(pp)` 的根因——另开 PR。

---

## File Structure

| 文件 | 责任 | 改动 |
|---|---|---|
| `vibetrace/cache.py` | SQLite 缓存读写 | 新增 `distinct_projects()` 纯查询(~10 行) |
| `vibetrace/brief.py` | 开工简报渲染(零 LLM) | 新增 `TOP_DEBT_PROJECTS`、`build_overview`、`_overview_row`、`_shorten`;`build_brief` 返回前补脱敏;补 imports(~55 行) |
| `vibetrace/cli.py` | 子命令分发 | `brief` 加 `--all` 旗标 + `brief_cmd` 的 `--all` 分支(~12 行) |
| `tests/test_overview.py` | 本特性测试 | 新建 |

数据流(全部已存在,只新增装配):
`cli brief --all` → `cache.distinct_projects()` → `brief.build_overview(cache, projects, today)` →(逐项目)`cache.pending_capsules(p)` + `debt.debt_board(p, cache, today, top=1)` → `config.redact_secrets` → 打印 /(`--vault`)`report.write_report`。

---

### Task 1: `cache.distinct_projects()`

发现层:返回 cache 里所有**绝对路径**项目键。`LIKE '/%'` 滤掉 graph/ask/course 写进 `commit_narratives` 的 basename 幻影(spec F2)。

**Files:**
- Modify: `vibetrace/cache.py`(在 `rekey_project` 之后、`close` 之前插入)
- Test: `tests/test_overview.py`(新建)

**Interfaces:**
- Consumes: 现有表 `commit_narratives` / `daily_digests` / `capsules` 的 `project` 列。
- Produces: `Cache.distinct_projects() -> list[str]`(去重、升序的绝对路径列表)。

- [ ] **Step 1: Write the failing test**

新建 `tests/test_overview.py`:

```python
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from vibetrace import brief, cli, config, report
from vibetrace.cache import Cache


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _make_repo(n_commits):
    """临时 git 仓,对 a.py 提交 n 次;返回 resolve 后的绝对路径字符串。"""
    d = tempfile.mkdtemp()
    _git(["init", "-q"], d)
    _git(["config", "user.email", "t@t"], d)
    _git(["config", "user.name", "t"], d)
    f = Path(d) / "a.py"
    for i in range(n_commits):
        f.write_text(f"{i}\n")
        _git(["add", "."], d)
        _git(["commit", "-q", "-m", f"c{i}"], d)
    return str(Path(d).resolve())


class TestDistinctProjects(unittest.TestCase):
    def test_keeps_abspaths_drops_basename_phantoms(self):
        c = Cache(":memory:")
        # 真实路径键(三表各放一种)
        c.put_narrative("sha1", "/abs/proj-a", "m", {"what": "x"})
        c.put_daily("/abs/proj-b", "2026-06-01", "ov", "")
        c.seal_capsule("/abs/proj-c", "shaC", 0, "r", "2026-05-01", "2026-05-22")
        # basename 幻影(graph/ask/course 历史写法)——必须被滤掉
        c.put_narrative("graph:proj-a", "proj-a", "graph", {"nodes": []})
        c.put_narrative("ask:zzz", "proj-a", "ask", {"what": "y"})
        got = c.distinct_projects()
        self.assertEqual(got, ["/abs/proj-a", "/abs/proj-b", "/abs/proj-c"])

    def test_empty_cache_returns_empty_list(self):
        self.assertEqual(Cache(":memory:").distinct_projects(), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_overview.TestDistinctProjects -v`
Expected: FAIL with `AttributeError: 'Cache' object has no attribute 'distinct_projects'`

- [ ] **Step 3: Write minimal implementation**

在 `vibetrace/cache.py` 的 `rekey_project` 方法之后插入:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_overview.TestDistinctProjects -v`
Expected: PASS(2 tests)

- [ ] **Step 5: Commit**

```bash
git add vibetrace/cache.py tests/test_overview.py
git commit -m "feat(cache): distinct_projects 跨项目发现(LIKE '/%' 滤 basename 幻影)

Vibe-Decision: 发现端用 project LIKE '/%' 而非裸 DISTINCT——commit_narratives 里
graph/ask/course 写的是 basename,裸查会出 CodeTalk/绝对路径双份幻影。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `brief.build_overview` + 脱敏闭红线

跨项目渲染纯函数:逐存活项目算 pending + debt,取"有到期胶囊 ∪ 债最高 K 个"并集,按 `(胶囊数, 债峰)` 降序渲染,返回前 `redact_secrets`。顺手给 `build_brief` 返回也补脱敏(同文件、隐私红线)。

**Files:**
- Modify: `vibetrace/brief.py`(补 imports;文件末尾加常量与新函数;改 `build_brief` 末行)
- Test: `tests/test_overview.py`(追加类)

**Interfaces:**
- Consumes: `cache.distinct_projects()`(Task 1,但本函数收 `projects` 形参,不直接调用);`cache.pending_capsules(project) -> list[{sha,risk,sealed_date}]`(按 open_date 升序,最久在前);`debt.debt_board(project_path, cache, today, top=1) -> list[{file,debt,...}]`(空仓/无 git 返回 `[]`);`config.redact_secrets(text) -> str`。
- Produces: `brief.build_overview(cache, projects, today) -> str`(已脱敏 markdown);模块常量 `brief.TOP_DEBT_PROJECTS = 5`;`brief.build_brief` 返回值现已脱敏。

- [ ] **Step 1: Write the failing tests**

在 `tests/test_overview.py` 追加:

```python
class TestBuildOverview(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 6, 9)
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def _tmpdir(self):
        d = tempfile.mkdtemp()
        self.dirs.append(d)
        return str(Path(d).resolve())

    def _open_capsule(self, cache, proj, risk, sealed="2026-05-01"):
        cache.seal_capsule(proj, "sha", 0, risk, sealed, "2026-05-22")
        cache.open_due_capsules(proj, "2026-06-01")  # 盖 opened_date → 进 pending

    def test_empty_projects_list(self):
        out = brief.build_overview(Cache(":memory:"), [], self.today)
        self.assertIn("没有需要注意的项目", out)

    def test_nonexistent_paths_skipped_silently(self):
        out = brief.build_overview(Cache(":memory:"),
                                   ["/no/such/path/xyz"], self.today)
        self.assertIn("没有需要注意的项目", out)
        self.assertNotIn("失效", out)  # 不计数、不报失效

    def test_capsule_only_project_shown(self):
        c = Cache(":memory:")
        p = self._tmpdir()  # 非 git 目录 → debt_board 返回 [],债峰 0
        self._open_capsule(c, p, "serve 模式胶囊回写可能丢失")
        out = brief.build_overview(c, [p], self.today)
        self.assertIn(Path(p).name, out)
        self.assertIn("待验证预测 1 枚", out)
        self.assertIn("serve 模式胶囊回写可能丢失", out)
        self.assertNotIn("理解债 top", out)  # 无 git → 无债行

    def test_days_ago_from_sealed_date(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "r", sealed="2026-05-01")  # 至 6/9 = 39 天
        out = brief.build_overview(c, [p], self.today)
        self.assertIn("最久 39 天前", out)

    def test_redaction_masks_secret_in_risk(self):
        c = Cache(":memory:")
        p = self._tmpdir()
        self._open_capsule(c, p, "key 是 sk-abcdef0123456789ABCDEF 别泄漏")
        out = brief.build_overview(c, [p], self.today)
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", out)

    def test_topk_omits_lowest_debt(self):
        c = Cache(":memory:")
        a, b, cc = self._tmpdir(), self._tmpdir(), self._tmpdir()
        peaks = {a: 30.0, b: 20.0, cc: 10.0}

        def fake_board(path, cache, today, top=None):
            return [{"file": "x.py", "debt": peaks[path]}]

        with mock.patch.object(brief, "TOP_DEBT_PROJECTS", 2), \
             mock.patch("vibetrace.debt.debt_board", side_effect=fake_board):
            out = brief.build_overview(c, [a, b, cc], self.today)
        self.assertIn(Path(a).name, out)
        self.assertIn(Path(b).name, out)
        self.assertNotIn(Path(cc).name, out)        # 债最低被省
        self.assertIn("另有 1 个存活项目未入榜", out)

    def test_capsule_sorts_before_higher_debt(self):
        c = Cache(":memory:")
        hi, lo = self._tmpdir(), self._tmpdir()     # hi 债高无胶囊;lo 债低有胶囊
        self._open_capsule(c, lo, "待验证")
        peaks = {hi: 99.0, lo: 1.0}

        def fake_board(path, cache, today, top=None):
            return [{"file": "x.py", "debt": peaks[path]}]

        with mock.patch("vibetrace.debt.debt_board", side_effect=fake_board):
            out = brief.build_overview(c, [hi, lo], self.today)
        self.assertLess(out.index(Path(lo).name), out.index(Path(hi).name))


class TestBuildBriefRedacts(unittest.TestCase):
    def test_brief_output_is_redacted(self):
        c = Cache(":memory:")
        c.put_daily("/abs/proj", "2026-06-01",
                    "上次提交里写了 sk-abcdef0123456789ABCDEF", "")
        out = brief.build_brief(c, "proj", "/abs/proj")
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_overview.TestBuildOverview tests.test_overview.TestBuildBriefRedacts -v`
Expected: FAIL — `AttributeError: module 'vibetrace.brief' has no attribute 'build_overview'`(及 build_brief 脱敏断言失败)

- [ ] **Step 3a: 补 imports 与 build_brief 脱敏**

把 `vibetrace/brief.py` 顶部的 import 块改为:

```python
"""开工简报(Boot Brief):开工前把『你上次停在哪』端到面前。
读本地 cache + git log(理解债),不调 LLM、不出网——补『日常化』最大短板。"""
from datetime import date, datetime, timezone
from pathlib import Path

from . import debt as debt_mod
from .config import redact_secrets
from .gitlog import collect_commit_files, commit_body, parse_breadcrumbs
```

把 `build_brief` 最后一行(`return "\n".join(lines).rstrip() + "\n"`)改为:

```python
    return redact_secrets("\n".join(lines).rstrip() + "\n")
```

- [ ] **Step 3b: 文件末尾追加常量与新函数**

在 `vibetrace/brief.py` 末尾追加:

```python
TOP_DEBT_PROJECTS = 5


def _shorten(path):
    """~/x 代替 home,终端更短。"""
    home, s = str(Path.home()), str(path)
    return "~" + s[len(home):] if s.startswith(home) else s


def _overview_row(name, path, pending, board, today):
    """单项目紧凑块。pending=pending_capsules(最久在前);board=debt_board(top=1)。"""
    lines = [f"## {name}  {_shorten(path)}"]
    if pending:
        oldest = pending[0]
        try:
            days = (today - date.fromisoformat(oldest["sealed_date"])).days
            since = f"(最久 {days} 天前)"
        except (ValueError, TypeError):
            since = ""  # 容错:坏日期不崩,省掉天数
        lines.append(f"- 待验证预测 {len(pending)} 枚{since}:「{oldest['risk']}」")
    if board:
        r = board[0]
        lines.append(f"- 理解债 top:`{r['file']}`(债 {r['debt']})")
    return lines


def build_overview(cache, projects, today):
    """跨项目注意力路由:有到期胶囊的 + 理解债最高的 K 个,零 LLM。
    projects=绝对路径列表(cache.distinct_projects())。返回已脱敏 markdown。"""
    live = []
    for p in projects:
        if not Path(p).is_dir():
            continue  # 失效路径静默跳过:不计数、不进 footer
        board = debt_mod.debt_board(p, cache, today, top=1)
        live.append({
            "path": p, "name": Path(p).name,
            "pending": cache.pending_capsules(p), "board": board,
            "peak": board[0]["debt"] if board else 0,
        })

    by_debt = sorted(live, key=lambda x: x["peak"], reverse=True)
    debt_in = {x["path"] for x in by_debt[:TOP_DEBT_PROJECTS] if x["peak"] > 0}
    shown = [x for x in live if x["pending"] or x["path"] in debt_in]
    shown.sort(key=lambda x: (len(x["pending"]), x["peak"]), reverse=True)

    if not shown:
        return ("# 跨项目总览\n\n没有需要注意的项目"
                "——先在某个项目跑 `vibetrace digest`。\n")

    lines = [f"# 跨项目总览 · {len(shown)} 个项目待办", ""]
    for x in shown:
        lines += _overview_row(x["name"], x["path"], x["pending"],
                               x["board"], today)
        lines.append("")
    omitted = len(live) - len(shown)
    if omitted:
        lines.append(f"_另有 {omitted} 个存活项目未入榜"
                     "(债较低、无到期胶囊),已省略。_")
    return redact_secrets("\n".join(lines).rstrip() + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_overview.TestBuildOverview tests.test_overview.TestBuildBriefRedacts -v`
Expected: PASS(8 tests)

- [ ] **Step 5: 回归 + 行数检查**

Run: `python3 -m unittest discover -s tests`
Expected: OK(全量绿,含既有 test_brief / test_multiproject)
Run: `wc -l vibetrace/brief.py`
Expected: < 300

- [ ] **Step 6: Commit**

```bash
git add vibetrace/brief.py tests/test_overview.py
git commit -m "feat(brief): build_overview 跨项目注意力路由 + 闭脱敏红线

Vibe-Decision: 入选用债 top-K(TOP_DEBT_PROJECTS=5)有界展示而非阈值;
build_overview/build_brief 返回前 redact_secrets,闭『落盘前脱敏』红线
(write_report 本不脱敏)。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `cli brief --all` 接线

`brief` 加 `--all` 旗标;`brief_cmd` 走 overview 分支:发现 → 渲染 → 打印 →(`--vault`)写已脱敏内容。`--all` 不跑 `read_capsule_answers`、忽略 `--project`。

**Files:**
- Modify: `vibetrace/cli.py`(`brief` parser 加 `--all`;重构 `brief_cmd`)
- Test: `tests/test_overview.py`(追加类)

**Interfaces:**
- Consumes: `cache.distinct_projects()`(Task 1);`brief.build_overview(cache, projects, today)`(Task 2);`report.write_report(vault, project, date_str, content)`。
- Produces: 命令 `vibetrace brief --all [--vault DIR]`。

- [ ] **Step 1: Write the failing test**

在 `tests/test_overview.py` 追加:

```python
class TestBriefAllCLI(unittest.TestCase):
    def setUp(self):
        self.dirs = []

    def tearDown(self):
        for d in self.dirs:
            shutil.rmtree(d, ignore_errors=True)

    def test_brief_all_routes_to_overview_and_skips_sync(self):
        repo = _make_repo(2)                       # 真实 git 仓
        self.dirs.append(repo)
        dbdir = tempfile.mkdtemp()
        self.dirs.append(dbdir)
        dbfile = str(Path(dbdir) / "cache.db")
        c = Cache(dbfile)
        c.put_daily(repo, "2026-06-01", "ov", "")  # 让 repo 可被发现
        c.seal_capsule(repo, "sha", 0, "待验证项", "2026-05-01", "2026-05-22")
        c.open_due_capsules(repo, "2026-06-01")
        c.close()

        synced = {"v": False}
        with mock.patch.object(cli, "CACHE_DB_PATH", dbfile), \
             mock.patch.object(config, "CONFIG_PATH", Path(dbdir) / "none.json"), \
             mock.patch.object(report, "read_capsule_answers",
                               lambda *a, **k: synced.__setitem__("v", True)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cli.main(["brief", "--all"])
        self.assertEqual(rc, 0)
        self.assertIn("跨项目总览", buf.getvalue())
        self.assertIn(Path(repo).name, buf.getvalue())
        self.assertFalse(synced["v"])  # --all 不跑跨项目胶囊同步
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_overview.TestBriefAllCLI -v`
Expected: FAIL — `error: unrecognized arguments: --all`(argparse 还没有该旗标)

- [ ] **Step 3a: parser 加 `--all`**

在 `vibetrace/cli.py` 的 brief 子命令定义处(`bri = sub.add_parser("brief", ...)` 块)追加一行,改为:

```python
    bri = sub.add_parser("brief", help="开工简报:你上次停在哪(纯本地,无 LLM)")
    bri.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    bri.add_argument("--vault", help="同时写入该目录(默认仅打印)")
    bri.add_argument("--all", action="store_true",
                     help="跨项目总览:所有项目里需要注意的(零 LLM,忽略 --project)")
```

- [ ] **Step 3b: 重构 `brief_cmd`**

把 `vibetrace/cli.py` 的 `brief_cmd` 整体替换为:

```python
def brief_cmd(args):
    cfg = load_config()
    if args.vault:
        cfg["vault_path"] = args.vault
    cache = Cache(CACHE_DB_PATH)
    if args.all:
        today = datetime.now(timezone.utc).astimezone().date()
        content = brief.build_overview(cache, cache.distinct_projects(), today)
        cache.close()
        print(content)
        if args.vault:
            path = report.write_report(cfg["vault_path"], "overview",
                                       "brief", content)
            print(f"总览已写入:{path}")
        return 0
    project_path = Path(args.project).resolve()
    project = project_path.name
    pkey = str(project_path)
    cache.rekey_project(project, pkey)   # 迁移旧 basename 键数据(幂等)
    # 与 digest 对齐:先回读 Obsidian 里勾选的答案,否则简报会反复催问已答胶囊
    report.read_capsule_answers(cfg["vault_path"], pkey, cache)
    content = brief.build_brief(cache, project, pkey)
    cache.close()
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], project, "brief", content)
        print(f"简报已写入:{path}")
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_overview.TestBriefAllCLI -v`
Expected: PASS(1 test)

- [ ] **Step 5: 全量回归 + 红线检查**

Run: `python3 -m unittest discover -s tests`
Expected: OK(全量绿)
Run: `grep -n LLMClient vibetrace/brief.py vibetrace/cache.py`
Expected: 无输出(自证零 LLM)
Run: `wc -l vibetrace/cli.py vibetrace/brief.py vibetrace/cache.py`
Expected: 三者均 < 300

- [ ] **Step 6: Commit**

```bash
git add vibetrace/cli.py tests/test_overview.py
git commit -m "feat(cli): brief --all 跨项目总览接线

--all 走 distinct_projects→build_overview→打印/可选写盘(已脱敏),
不跑 read_capsule_answers、忽略 --project。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**
- 发现 `distinct_projects` + `LIKE '/%'` 滤幻影(F2)→ Task 1 ✓
- 信号 pending_capsules + debt_board;open_loops 移出(F7)→ Task 2 `build_overview` 不含 open_loops ✓
- 相关性过滤 = 有胶囊 ∪ 债 top-K;删 DEBT_FLOOR(F4/F6)→ Task 2 `debt_in`/`shown` ✓
- 排序 `(胶囊数, 债峰)` 降序 → Task 2 `shown.sort(...)` ✓
- 失效路径静默跳过(F3)→ Task 2 `if not Path(p).is_dir(): continue` + test ✓
- 脱敏 build_overview + build_brief(F1/F5)→ Task 2 两处 `redact_secrets` + test ✓
- 砍跨项目 read_capsule_answers(YAGNI)→ Task 3 `--all` 分支不调 + test 断言 ✓
- "天前"用 sealed_date、示例 28(F-minor)→ Task 2 `_overview_row` 用 sealed_date;test 用 39 天验证 ✓
- 单一空状态(F-minor)→ Task 2 `if not shown` 单分支 + 两个 test ✓
- `--all` 忽略 --project → Task 3 分支提前 return,不读 `args.project` ✓
- 输出 footer "另有 N 个未入榜" → Task 2 `omitted` + test ✓
- `--vault` 写已脱敏内容 → Task 3 写的是 build_overview 已脱敏的 content ✓

**2. Placeholder scan:** 无 TBD/TODO;每个改代码步骤都给了完整代码块与确切命令/预期。

**3. Type consistency:**
- `build_overview(cache, projects, today)` — Task 2 定义、Task 3 调用,签名一致 ✓
- `distinct_projects() -> list[str]` — Task 1 定义、Task 3 调用 ✓
- `TOP_DEBT_PROJECTS` 模块常量 — Task 2 定义、测试 `mock.patch.object(brief, "TOP_DEBT_PROJECTS", 2)` 引用一致 ✓
- `pending_capsules` 返回含 `sealed_date`(cache.py:156 实测)— `_overview_row` 读 `oldest["sealed_date"]` ✓
- `debt_board(..., top=1)` 返回 `[{file,debt,...}]` 或 `[]` — `board[0]["debt"]`/`board[0]["file"]` ✓
- cli 顶部已 `from datetime import date, datetime, timedelta, timezone`,`brief_cmd` 用 `datetime.now(timezone.utc)` 可用 ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-cross-project-overview.md`.
按 `/goal` 授权,默认走 **Subagent-Driven**(每任务一 subagent + 任务复核 + 终审),A→Task1→Task2→Task3→whole-branch review→dogfood。
