# 文件树「接地入口」视图 · Phase A(console)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 vibetrace console 单页里加一棵可折叠项目文件树,用 `git status` 确定性高亮工作区新增/修改/未跟踪/删除文件,点变更文件 → 右侧零-LLM 面板列该文件的 commit 决策历史 + 真实 SHA。

**Architecture:** 新 stdlib 模块 `filetree.py`(工作区 `git status` reader + 纯函数树构造)→ `console.py:_assemble()` 注入 `data["tree"]`(nodes + 仅变更文件的 grounding 索引,复用其已建的 commits/narratives,不二次查 DB)→ `console.html` 第 5 视图渲染折叠树(左)+ 接地面板(右)。全程零 LLM、纯本地、注入前 `redact_data` 脱敏。

**Tech Stack:** Python 3.11+ 标准库(`subprocess`/`json`/`string.Template`);零-build 单文件 vanilla-JS;stdlib `unittest`。

## Global Constraints
- 仅标准库(禁第三方);新增/改动 Python 模块各 `wc -l` < 300(`filetree.py`、`console.py`)。
- 数据不出本机;`console.py:_build_html` 经 `inline_json(redact_data(data))` 注入,新增 `data["tree"]` 必须落在该脱敏管线内。
- 容错降级绝不崩:`filetree.status()` git 失败/非 git 仓 → `[]`;`gitlog.tracked_files()` 失败返 `None` → `_assemble` 用 `or set()` 兜底。
- 零-build 单文件 vanilla-JS;`console.html` 内 JS **禁用 `${}` 模板字面量**(与 `$`-Template 占位冲突);用户文本一律 `esc()`;改动后跑 `python3 -m scripts.check_static_no_external`(扫无外链)。
- 全程零 LLM(本视图 `grep -n LLMClient vibetrace/filetree.py` = 0)。
- Phase B(web 主机)不在本计划。

---

### Task 1: `filetree.status()` + `label()`(工作区 git status reader)

**Files:**
- Create: `vibetrace/filetree.py`
- Test: `tests/test_filetree.py`

**Interfaces:**
- Consumes: `gitlog._git(args, cwd) -> str`(非零退出抛 `RuntimeError`,`timeout=60`)。
- Produces:
  - `status(project_path) -> list[dict]`,元素 `{"path": str, "code": str(2字符), "label": str}`;git 失败/非 git 仓 → `[]`。
  - `label(code: str) -> str`(确定性人话标签)。
  - `STATUS_LABELS`/`_PRIORITY`(内部)。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filetree.py
import subprocess
import unittest
from unittest import mock

from vibetrace import filetree


class TestLabel(unittest.TestCase):
    def test_codes_map_deterministically(self):
        cases = {
            " M": "已修改", "M ": "已暂存·已修改", "??": "未跟踪",
            "A ": "已暂存·新增", " D": "已删除", "D ": "已暂存·已删除",
            "R ": "已暂存·重命名", "C ": "已暂存·复制", "MM": "已暂存·已修改",
            "AM": "已暂存·新增", "MD": "已删除", "UU": "冲突",
        }
        for code, want in cases.items():
            self.assertEqual(filetree.label(code), want, code)

    def test_unknown_code_does_not_crash(self):
        self.assertTrue(filetree.label("ZZ"))     # 原样 code,不崩


class TestStatus(unittest.TestCase):
    def _raw(self, s):
        return mock.patch.object(filetree.gitlog, "_git", return_value=s)

    def test_parses_codes_and_paths(self):
        with self._raw(" M a.py\x00?? b.py\x00"):
            out = filetree.status("/x")
        self.assertEqual(out, [
            {"path": "a.py", "code": " M", "label": "已修改"},
            {"path": "b.py", "code": "??", "label": "未跟踪"},
        ])

    def test_rename_consumes_oldpath_segment(self):
        with self._raw("R  new.py\x00old.py\x00"):
            out = filetree.status("/x")
        self.assertEqual([e["path"] for e in out], ["new.py"])  # old.py 被消费,不单独成项
        self.assertEqual(out[0]["code"], "R ")

    def test_skips_empty_and_trailing_slash(self):
        with self._raw("?? keep.py\x00?? folded/\x00\x00"):
            out = filetree.status("/x")
        self.assertEqual([e["path"] for e in out], ["keep.py"])  # 尾斜杠条目 + 空段丢弃

    def test_passes_untracked_all_flag(self):
        with mock.patch.object(filetree.gitlog, "_git", return_value="") as g:
            filetree.status("/x")
        args = g.call_args[0][0]
        self.assertIn("--untracked-files=all", args)
        self.assertIn("-z", args)

    def test_git_failure_returns_empty(self):
        with mock.patch.object(filetree.gitlog, "_git",
                               side_effect=RuntimeError("not a git repo")):
            self.assertEqual(filetree.status("/x"), [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_filetree -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibetrace.filetree'`.

- [ ] **Step 3: Write minimal implementation**

```python
# vibetrace/filetree.py
"""工作区文件树 + git status(零 LLM,纯 stdlib)。

供 console 文件树「接地入口」视图:确定性读工作区状态 + 拼项目结构树。
与 gitlog(历史)分开:这里只关心工作树当下状态。容错降级绝不崩。
"""
import subprocess

from . import gitlog

# 状态码 → 人话标签;列表序即优先级(越靠前越优先):U>D>R>C>A>M>?
STATUS_LABELS = [("U", "冲突"), ("D", "已删除"), ("R", "重命名"),
                 ("C", "复制"), ("A", "新增"), ("M", "已修改"), ("?", "未跟踪")]
_NAME = dict(STATUS_LABELS)
_PRIORITY = {code: i for i, (code, _) in enumerate(STATUS_LABELS)}


def label(code):
    """porcelain 两字符 XY code → 人话标签(确定性)。
    取 XY 两位里优先级更高者定主标签;X(暂存位)非空格且其字母即主标签来源时加「已暂存·」。
    未知字母 → 原样 code(不崩)。"""
    code = (code or "  ")[:2].ljust(2)
    x, y = code[0], code[1]
    letters = [c for c in (x, y) if c not in (" ", "?")]
    if "?" in (x, y):
        letters.append("?")
    if not letters:
        return code.strip() or "?"
    main = min(letters, key=lambda c: _PRIORITY.get(c, 99))
    name = _NAME.get(main)
    if name is None:
        return code.strip()
    staged = x not in (" ", "?") and x == main
    return ("已暂存·" + name) if staged else name


def status(project_path):
    """工作区 git status(零 LLM)。→ [{"path","code","label"}];git 失败/非 git 仓 → []。
    `-uall` 展开未跟踪目录为逐文件(否则新建目录折叠成 `?? dir/`、内部新增文件全不可见)。
    `-z` NUL 分隔有状态迭代:R/C 项的下一段是 old/orig-path,一并消费;跳空段;丢尾斜杠条目。"""
    try:
        raw = gitlog._git(["status", "--porcelain=v1", "-z", "--untracked-files=all"],
                          project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return []
    segs = raw.split("\x00")
    out, i = [], 0
    while i < len(segs):
        seg = segs[i]
        if not seg:
            i += 1
            continue
        code, path = seg[:2], seg[3:]
        i += 2 if code[:1] in ("R", "C") else 1   # R/C:消费紧跟的 old-path 段
        if not path or path.endswith("/"):
            continue
        out.append({"path": path, "code": code, "label": label(code)})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_filetree -v`
Expected: PASS(7 tests)。

- [ ] **Step 5: Commit**

```bash
git add vibetrace/filetree.py tests/test_filetree.py
git commit -m "feat(filetree): 工作区 git status reader + 确定性标签(零 LLM)"
```

---

### Task 2: `filetree.build_tree()`(纯函数树构造)

**Files:**
- Modify: `vibetrace/filetree.py`(追加 `build_tree`)
- Test: `tests/test_filetree.py`(追加 `TestBuildTree`)

**Interfaces:**
- Consumes: 无(纯函数,不碰 git/磁盘)。
- Produces: `build_tree(paths, status_map) -> dict`
  - `paths`: repo 相对路径可迭代;`status_map`: `{path: {"code","label"}}`。
  - 返回 `{"name":"","type":"dir","changed":bool,"children":[...]}`;dir 节点 `{"name","type":"dir","changed","children":[...]}`;file 节点 `{"name","type":"file","path","code"?,"label"?}`。
  - `changed`(目录)= 任一后代有 status(向所有祖先冒泡);children 排序:目录在前、各按名字典序。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_filetree.py —— 追加到文件末尾(import 已在 Task 1 顶部)
class TestBuildTree(unittest.TestCase):
    def test_nests_and_bubbles_changed(self):
        paths = ["a/b.py", "a/c.py", "d.py"]
        sm = {"a/b.py": {"code": " M", "label": "已修改"}}
        root = filetree.build_tree(paths, sm)
        self.assertEqual(root["type"], "dir")
        names = [c["name"] for c in root["children"]]
        self.assertEqual(names, ["a", "d.py"])          # 目录在前、字典序
        a = root["children"][0]
        self.assertTrue(a["changed"])                   # b.py 变更 → 祖先 a changed
        b = next(c for c in a["children"] if c["name"] == "b.py")
        self.assertEqual(b["code"], " M")
        c = next(c for c in a["children"] if c["name"] == "c.py")
        self.assertNotIn("code", c)                     # 未变更文件无 code
        self.assertFalse(root["children"][1].get("changed", False))

    def test_deleted_file_node_present(self):
        root = filetree.build_tree(["x.py"], {"x.py": {"code": " D", "label": "已删除"}})
        self.assertEqual(root["children"][0]["code"], " D")
        self.assertTrue(root["changed"])

    def test_empty_input(self):
        root = filetree.build_tree([], {})
        self.assertEqual(root["children"], [])
        self.assertFalse(root["changed"])

    def test_large_input_no_crash(self):
        paths = ["d%d/f%d.py" % (i // 50, i) for i in range(5000)]
        root = filetree.build_tree(paths, {})
        leaves = []
        stack = [root]
        while stack:
            n = stack.pop()
            if n["type"] == "file":
                leaves.append(n)
            else:
                stack.extend(n["children"])
        self.assertEqual(len(leaves), 5000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_filetree.TestBuildTree -v`
Expected: FAIL — `AttributeError: module 'vibetrace.filetree' has no attribute 'build_tree'`.

- [ ] **Step 3: Write minimal implementation**

```python
# vibetrace/filetree.py —— 追加到文件末尾
def build_tree(paths, status_map):
    """纯函数:repo 相对路径集 + {path:{code,label}} → 嵌套树。不碰 git/磁盘。
    dir 节点 changed=任一后代有 status;目录在前、各按名字典序。"""
    root = {"name": "", "type": "dir", "children": {}}
    for path in paths:
        parts = [p for p in path.split("/") if p]
        if not parts:
            continue
        node = root
        for part in parts[:-1]:
            child = node["children"].get(part)
            if child is None or child["type"] == "file":
                child = {"name": part, "type": "dir", "children": {}}
                node["children"][part] = child
            node = child
        leaf, st = parts[-1], status_map.get(path)
        node["children"][leaf] = {"name": leaf, "type": "file", "path": path,
                                  **({"code": st["code"], "label": st["label"]} if st else {})}

    def finalize(node):
        if node["type"] == "file":
            return node
        kids = [finalize(c) for c in node["children"].values()]
        kids.sort(key=lambda c: (c["type"] != "dir", c["name"]))
        node["children"] = kids
        node["changed"] = any(
            c["changed"] if c["type"] == "dir" else ("code" in c) for c in kids)
        return node
    return finalize(root)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_filetree -v`
Expected: PASS(全部,含 Task 1 的 7 + 本任务 4)。

- [ ] **Step 5: Commit**

```bash
git add vibetrace/filetree.py tests/test_filetree.py
git commit -m "feat(filetree): build_tree 纯函数(嵌套 + changed 冒泡 + 排序)"
```

---

### Task 3: `console._file_grounding()` + `_assemble()` 注入 `data["tree"]`

**Files:**
- Modify: `vibetrace/console.py:13`(import)、`vibetrace/console.py:33-51`(`_assemble`)
- Test: `tests/test_console.py:44`(改既有 `test_assemble_has_four_views`)+ 追加 `TestFiletreeAssemble`

**Interfaces:**
- Consumes: `filetree.status`、`filetree.build_tree`、`gitlog.tracked_files(pp) -> set|None`;`_assemble` 已建的 `commits`(每项含 `sha`/`subject`/`date`(datetime)/`files`)与 `narratives`(`{sha: narrative|None}`)。
- Produces:
  - `_file_grounding(changed_paths, commits, narratives) -> list`,元素 `{"path": str, "commits": [{"sha","subject","date","decisions","sources"}]}`(`sha` 取前 7;`sources=[{"type":"commit","sha":前7}]` 确定性合成,非 narrative 字段;仅为 `changed_paths` 构建)。
  - `_assemble` 返回的 `data` 增 `data["tree"] = {"nodes": <build_tree>, "grounding": <_file_grounding>}`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_console.py —— 改 line 44 起的既有方法名 + 断言(four → tree)
    def test_assemble_includes_tree(self):
        data, err = console._assemble(self.d, self.cache)
        self.assertIsNone(err)
        self.assertEqual(set(data),
                         {"overview", "timeline", "graph", "debt", "tree"})
        self.assertIn("nodes", data["tree"])
        self.assertIn("grounding", data["tree"])
        self.assertEqual(data["tree"]["nodes"]["type"], "dir")
```

```python
# tests/test_console.py —— 顶部 import 处补:from datetime import datetime
# 追加新测试类
class TestFiletreeAssemble(unittest.TestCase):
    def test_file_grounding_bounded_and_synthesizes_sources(self):
        commits = [
            {"sha": "a" * 40, "subject": "改 a", "date": datetime(2026, 6, 1),
             "files": ["a.py"]},
            {"sha": "b" * 40, "subject": "改 b", "date": datetime(2026, 6, 2),
             "files": ["b.py"]},
        ]
        narratives = {"a" * 40: {"decisions": ["选 X"]}, "b" * 40: None}
        out = console._file_grounding(["a.py"], commits, narratives)
        self.assertEqual([e["path"] for e in out], ["a.py"])     # 仅变更文件,有界
        row = out[0]["commits"][0]
        self.assertEqual(row["sha"], "a" * 7)
        self.assertEqual(row["decisions"], ["选 X"])
        self.assertEqual(row["sources"], [{"type": "commit", "sha": "a" * 7}])

    def test_assemble_tracked_files_none_no_crash(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        _git(["init", "-q"], d)
        _git(["config", "user.email", "t@t"], d)
        _git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n"); _git(["add", "."], d)
        _git(["commit", "-q", "-m", "c1"], d)
        with mock.patch.object(console, "tracked_files", return_value=None):
            data, err = console._assemble(d, Cache(":memory:"))
        self.assertIsNone(err)
        self.assertIn("tree", data)                              # None 守卫:不崩
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_console -v`
Expected: FAIL — `AttributeError: module 'vibetrace.console' has no attribute '_file_grounding'`,且 `test_assemble_includes_tree` 因缺 `tree` 键失败。

- [ ] **Step 3: Write minimal implementation**

改 `vibetrace/console.py:15` 的 import 行:

```python
from .gitlog import collect_commit_files, tracked_files
```

并在 import 区(line 11 同段)加:

```python
from . import brief, filetree, graph, tunnel
```

(即把现有 `from . import brief, graph, tunnel` 改为含 `filetree`。)

在 `_assemble` 内 `data = {...}` 字典字面量**之后、`return data, None` 之前**插入:

```python
    tracked = tracked_files(pp) or set()            # 失败返 None → 兜底空集(绝不崩)
    st = filetree.status(pp)
    status_map = {s["path"]: s for s in st}
    data["tree"] = {
        "nodes": filetree.build_tree(tracked | set(status_map), status_map),
        "grounding": _file_grounding([s["path"] for s in st], commits, narratives),
    }
```

在 `_assemble` 函数**之前**(或 `_build_html` 之前)加纯函数:

```python
def _file_grounding(changed_paths, commits, narratives):
    """零 LLM:为每个变更文件列其历史 commit + 决策 + SHA 引用(供右面板核验)。
    只为 changed_paths 构建(有界);吃已建 commits/narratives 不二次查 DB。
    sources 据 SHA 确定性合成(非 narrative 字段)。→ [{"path","commits":[...]}]。"""
    out = []
    for path in changed_paths:
        rows = []
        for c in commits:
            if path not in (c.get("files") or []):
                continue
            n = narratives.get(c["sha"]) if isinstance(narratives.get(c["sha"]), dict) else {}
            rows.append({
                "sha": c["sha"][:7],
                "subject": c.get("subject", ""),
                "date": c["date"].date().isoformat() if c.get("date") else "",
                "decisions": (n or {}).get("decisions") or [],
                "sources": [{"type": "commit", "sha": c["sha"][:7]}],
            })
        rows.reverse()                               # 最新在前
        out.append({"path": path, "commits": rows})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_console -v`
Expected: PASS(含改名后的 `test_assemble_includes_tree` 与新 `TestFiletreeAssemble`)。
检查行数:`wc -l vibetrace/console.py`(应 <300)。

- [ ] **Step 5: Commit**

```bash
git add vibetrace/console.py tests/test_console.py
git commit -m "feat(console): _assemble 注入文件树 + 变更文件零-LLM 接地索引"
```

---

### Task 4: `console.html` 第 5 视图「文件树」(折叠树左 / 接地面板右)

**Files:**
- Modify: `vibetrace/console.html`(line 243 后加 section;line 260 VIEWS;CSS 区加样式;render 区加 `renderFiletree`;line 653 init 链)
- Test: `tests/test_console.py`(追加 `TestFiletreeView`,读 HTML 文本断言标记)

**Interfaces:**
- Consumes: 注入的 `DATA.tree = {nodes, grounding}`(Task 3);全局 `esc()`、`VIEWS`、`show()`/`buildNav()`(由 VIEWS 数组驱动,自动覆盖导航)。
- Produces: 第 5 视图 DOM(`#v-filetree`、`.fttree`、`#ftpanel`)+ `renderFiletree()`。

- [ ] **Step 1: Write the failing test**

```python
# tests/test_console.py —— 追加新测试类
class TestFiletreeView(unittest.TestCase):
    def setUp(self):
        self.html = (Path(console.__file__).parent / "console.html").read_text(
            encoding="utf-8")

    def test_view_registered_in_nav_and_sections(self):
        self.assertIn('["filetree","文件树"]', self.html)        # VIEWS 项
        self.assertIn('id="v-filetree"', self.html)               # section
        self.assertIn("renderFiletree()", self.html)              # init 链调用

    def test_tree_and_panel_and_blame_hint(self):
        self.assertIn("fttree", self.html)                        # 左树容器
        self.assertIn('id="ftpanel"', self.html)                  # 右接地面板
        self.assertIn("vibetrace blame", self.html)               # 无叙事降级指引

    def test_file_nodes_keyboard_accessible_and_collapsible(self):
        self.assertIn("function renderFiletree", self.html)
        self.assertIn("<details", self.html)                      # 原生可折叠
        self.assertIn('"Enter"', self.html)                       # 键盘激活
        self.assertNotIn("${", self.html)                         # 禁模板字面量(全局守恒)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_console.TestFiletreeView -v`
Expected: FAIL — `'["filetree","文件树"]'` 等标记不存在。

- [ ] **Step 3: Write minimal implementation**

(a) `console.html:243` 后新增 section:

```html
  <section class="view" id="v-filetree" role="tabpanel" tabindex="0"></section>
```

(b) `console.html:260` VIEWS 数组末加项:

```javascript
var VIEWS = [["overview","开工概览"],["timeline","时光轴"],["graph","决策图"],["debt","理解债"],["filetree","文件树"]];
```

(c) CSS 区(如紧接 `renderDebt` 用到的 `.debt` 样式同块,或 `<style>` 内任意位置)加:

```css
.ftwrap{display:flex;gap:16px;align-items:flex-start}
.fttree{flex:0 0 46%;max-height:70vh;overflow:auto;font:13px/1.7 ui-monospace,monospace}
.ftpanel{flex:1;min-width:0}
.ftf{cursor:pointer;border-radius:4px}
.ftf:hover,.ftf:focus{background:rgba(255,255,255,.06);outline:none}
.ftf.del{opacity:.5;text-decoration:line-through}
.stb{font-size:11px;opacity:.7;margin-left:6px}
.st-M{color:#e3b341}.st-A{color:#3fb950}.st-D{color:#f85149}
.st-R{color:#a371f7}.st-C{color:#a371f7}.st-U{color:#f85149}
.ftf[class*="st-"]:not([class]){}
.ftc{margin:8px 0;padding:6px 0;border-top:1px solid rgba(255,255,255,.08)}
.ftc .dec{opacity:.85;margin-left:8px}
.ftpanel .hint{opacity:.6;font-size:12px}
```

(d) render 区(如 `renderDebt` 之后)加 `renderFiletree`:

```javascript
function renderFiletree(){
  var T = (DATA.tree && DATA.tree.nodes) || null;
  var G = (DATA.tree && DATA.tree.grounding) || [];
  var sec = document.getElementById("v-filetree");
  var head = '<h2 class="vh">文件树 — 工作区变更 + 点开看「当初为什么」</h2>';
  if (!T || !T.children || !T.children.length){
    sec.innerHTML = head + '<p class="empty">无文件或非 git 仓。</p>'; return; }
  var gmap = {}; G.forEach(function(e){ gmap[e.path] = e.commits || []; });
  function mark(code){ return code ? code.replace(/ /g,"").charAt(0) : ""; }
  function nodeHtml(node, depth){
    var pad = ' style="padding-left:'+(depth*14)+'px"';
    if (node.type === "file"){
      var m = mark(node.code);
      var cls = "ftf" + (m ? " st-"+m : "")
        + (node.code && node.code.indexOf("D")>=0 ? " del" : "");
      var badge = node.label ? ' <span class="stb">'+esc(node.label)+'</span>' : "";
      return '<div class="'+cls+'" data-path="'+esc(node.path)+'" role="button"'
        + ' tabindex="0"'+(node.label?' title="'+esc(node.label)+'"':"")+pad+'>'
        + esc(node.name)+badge+'</div>';
    }
    var kids = node.children.map(function(c){ return nodeHtml(c, depth+1); }).join("");
    return '<details class="ftd"'+(node.changed?" open":"")+'><summary'+pad+'>'
      + esc(node.name)+'</summary>'+kids+'</details>';
  }
  sec.innerHTML = head + '<div class="ftwrap"><div class="fttree">'
    + T.children.map(function(c){ return nodeHtml(c, 0); }).join("")
    + '</div><div class="ftpanel" id="ftpanel">'
    + '<p class="empty">点左侧文件看它的决策历史(零 LLM)。</p></div></div>';
  function showPanel(path){
    var rows = gmap[path], p = document.getElementById("ftpanel");
    if (!rows || !rows.length){
      p.innerHTML = '<h3>'+esc(path)+'</h3>'
        + '<p class="empty">暂无叙事(尚未提交或无历史)。</p>'
        + '<p class="hint">更深:<code>vibetrace blame '+esc(path)+'</code></p>'; return; }
    var h = '<h3>'+esc(path)+'</h3>';
    rows.forEach(function(r){
      h += '<div class="ftc"><span class="sha">'+esc(r.sha)+'</span> '+esc(r.subject)
        + ' <span class="meta">'+esc(r.date)+'</span>';
      (r.decisions||[]).forEach(function(d){ h += '<div class="dec">· '+esc(d)+'</div>'; });
      h += '</div>';
    });
    p.innerHTML = h;
  }
  sec.querySelectorAll(".ftf").forEach(function(el){
    function act(){ showPanel(el.getAttribute("data-path")); }
    el.addEventListener("click", act);
    el.addEventListener("keydown", function(e){
      if (e.key==="Enter" || e.key===" "){ e.preventDefault(); act(); } });
  });
}
```

(e) `console.html:653` init 链加 `renderFiletree();`(在 `renderDebt();` 与 `renderFoot();` 之间):

```javascript
buildNav(); initTheme(); renderOverview(); renderTimeline(); renderGraph(); renderDebt();
renderFiletree(); renderFoot(); initChat(); show("overview");
```

- [ ] **Step 4: Run tests + 静态扫描 to verify it passes**

Run: `python3 -m unittest tests.test_console -v`
Expected: PASS(含 `TestFiletreeView`)。
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3`
Expected: 全量 `OK`。
Run: `python3 -m scripts.check_static_no_external`
Expected: 无外链报错(退出 0)。

- [ ] **Step 5: Commit**

```bash
git add vibetrace/console.html tests/test_console.py
git commit -m "feat(console): 第5视图『文件树』—— 折叠树 + 右侧零-LLM 接地面板"
```

---

## Self-Review(对 spec Phase A 逐条核对)
- **spec 覆盖**:`filetree.status`(-uall + 有状态 NUL 解析 + git 失败 [])= Task 1;`label` 优先级总序 = Task 1;`build_tree`(嵌套/changed 冒泡/排序/删除节点/大输入)= Task 2;`console._file_grounding`(有界/不二次查 DB/sources 合成)+ `data["tree"]` + `tracked_files or set()` = Task 3;第 5 视图(VIEWS/section/折叠树/右面板/三重状态/删除置灰/blame 指引/键盘)= Task 4;改既有 `test_assemble_has_four_views` = Task 3。
- **占位符扫描**:无 TBD/TODO;每步含完整代码与确切命令。
- **类型一致**:`status() → [{path,code,label}]` 在 Task 1 产、Task 3 消费(`status_map`/`changed_paths`)一致;`build_tree(paths, status_map)` 签名跨 Task 2/3 一致;`_file_grounding(changed_paths, commits, narratives) → [{path,commits}]` 跨 Task 3/Task 4(`gmap[e.path]=e.commits`)一致;`DATA.tree={nodes,grounding}` 跨 Task 3/4 一致。
- **红线**:各 Python 模块预估 `filetree.py ~76`、`console.py ~127`(<300);零第三方;脱敏走 `redact_data`(Task 3 注入在 `_build_html` 既有管线内);两条降级(status []、tracked_files or set())有测试;`check_static_no_external` 在 Task 4 跑。
