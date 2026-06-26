# 文件树「接地入口」· Phase B(web 主机)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `vibetrace web` 对话页(`web_chat.html`)有可折叠工作区文件树:点 `[文件 ▸]` 滑出同一棵树,点变更文件 → 预填「这个文件当初为什么改」进 `#q` 并带 `target` → 走已有 `/api/chat/stream` LLM 接地对话。

**Architecture:** filetree 新增可测装配 `tree_payload`(并被 console._assemble 复用消重)→ web.py `_CHAT_HTML` 改 `Template`、`index()` 按请求注入 `$tree_data`(经 `redact_data`+`inline_json`+出口 `redact_secrets`)→ web_chat.html 加抽屉 + 折叠树渲染 + 点击填 `#q`/带 `target`。

**Tech Stack:** Python stdlib(`string.Template`/`subprocess`)+ FastAPI(可选 `[web]` extra,**惰性 import**)+ 零-build vanilla-JS + stdlib `unittest`(含 `fastapi.testclient.TestClient`)。

## Global Constraints
- `filetree.py` 纯 stdlib、**不 import web/fastapi**、<300 行;web extra 仅 `vibetrace web` 时惰性 import,CLI/MCP 核心仍纯 stdlib。
- 数据不出本机(LLM 唯一例外,受 `no_llm`);web `index` 注入前 `redact_data` + 出口 `redact_secrets`(双层,同 console._build_html)。
- 零-build 单文件 vanilla-JS;`web_chat.html` 现 0 字面 `$`,Template 化后**唯一合法占位 `$tree_data`**;新 JS 一律字符串拼接,**禁 `${}`/反引号/正则 `$1`/`$&`/`$<`**;`grep -c "\$" web_chat.html` 落地后须 == 1。代入值(文件名/标签)的 `$` 不需也不应预转义(Template 只扫模板正文)。
- 前端零外链:改后 `python3 -m scripts.check_static_no_external vibetrace/web_chat.html`;CSP `connect-src 'self'` 不动;只绑 127.0.0.1。
- 容错降级绝不崩:`tree_payload` 内 status []/tracked set();前端空树守卫判 `nodes.children.length`。
- 全程零 LLM(本 feature `grep LLMClient vibetrace/filetree.py` = 0;web 点击只填 `#q`,LLM 仅经既有 `/api/chat/stream`)。

---

### Task 1: `filetree.tree_payload()` + 重构 `console._assemble` 复用(消重)

**Files:**
- Modify: `vibetrace/filetree.py`(追加 `tree_payload`)
- Modify: `vibetrace/console.py:15`(去 orphan import)、`vibetrace/console.py:75-81`(改用 tree_payload)
- Test: `tests/test_filetree.py`(追加 `TestTreePayload`)

**Interfaces:**
- Produces: `tree_payload(project_path) -> {"nodes": <build_tree dict>, "status": [{"path","code","label"}]}`(纯 stdlib;`gitlog.tracked_files(pp) or set()` 守卫;git 失败 → status []/tracked set())。
- Consumes(已存在):`filetree.status`、`filetree.build_tree`、`gitlog.tracked_files`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_filetree.py —— 追加(顶部已有 import subprocess/unittest/mock + from vibetrace import filetree)
import shutil, tempfile
from pathlib import Path


class TestTreePayload(unittest.TestCase):
    def _git(self, a, c):
        subprocess.run(["git", *a], cwd=c, check=True, capture_output=True, text=True)

    def test_payload_nodes_and_status_from_real_repo(self):
        d = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        self._git(["init", "-q"], d)
        self._git(["config", "user.email", "t@t"], d); self._git(["config", "user.name", "t"], d)
        (Path(d) / "a.py").write_text("1\n"); self._git(["add", "."], d)
        self._git(["commit", "-q", "-m", "c1"], d)
        (Path(d) / "a.py").write_text("2\n")              # 工作区改动(未提交)
        (Path(d) / "new.py").write_text("x\n")            # 未跟踪
        tp = filetree.tree_payload(d)
        self.assertEqual(set(tp), {"nodes", "status"})
        self.assertEqual(tp["nodes"]["type"], "dir")
        paths = {s["path"] for s in tp["status"]}
        self.assertIn("a.py", paths)                      # 已修改
        self.assertIn("new.py", paths)                    # 未跟踪(-uall)

    def test_payload_git_failure_no_crash(self):
        # tracked_files 的 ls-files 抛错 → tracked 兜底 set();status 同源失败 → []
        with mock.patch.object(filetree.gitlog, "_git", side_effect=RuntimeError("not a repo")):
            tp = filetree.tree_payload("/x")
        self.assertEqual(tp["status"], [])
        self.assertEqual(tp["nodes"]["children"], [])     # 空根,不崩
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_filetree.TestTreePayload -v`
Expected: FAIL — `AttributeError: module 'vibetrace.filetree' has no attribute 'tree_payload'`.

- [ ] **Step 3: 实现 tree_payload + 重构 console**

`vibetrace/filetree.py` 末尾追加:

```python
def tree_payload(project_path):
    """装配工作区文件树 payload(零 LLM,纯 stdlib)。→ {"nodes": <build_tree>, "status": [...]}。
    供 web.index 与 console._assemble 共用消除同构装配;git 失败 status []/tracked set() 仍产合法树。"""
    tracked = gitlog.tracked_files(project_path) or set()
    st = status(project_path)
    status_map = {s["path"]: s for s in st}
    return {"nodes": build_tree(tracked | set(status_map), status_map), "status": st}
```

`vibetrace/console.py:15` 去掉已不再直接使用的 `tracked_files` import:

```python
from .gitlog import collect_commit_files
```

`vibetrace/console.py:75-81` 改为复用 tree_payload:

```python
    tp = filetree.tree_payload(pp)                   # 复用装配(零 LLM,消除同构双份 + 省 1 次 git 子进程)
    data["tree"] = {
        "nodes": tp["nodes"],
        "grounding": _file_grounding([s["path"] for s in tp["status"]], commits, narratives),
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_filetree -v` → PASS(含 TestTreePayload）。
Run: `python3 -m unittest tests.test_console -v` → PASS(既有 `_assemble`/tree 测试仍绿,验证重构等价)。
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` → OK。
Check: `wc -l vibetrace/filetree.py`(<300);`grep -n "tracked_files" vibetrace/console.py`(应只在注释/无 → 确认 orphan import 已除、无残留直调）。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/filetree.py vibetrace/console.py tests/test_filetree.py
git commit -m "feat(filetree): tree_payload 装配 + console 复用消重(零 LLM)"
```

---

### Task 2: web.py `_CHAT_HTML`→Template + `index()` 按请求渲染(TestClient 集成测)

**Files:**
- Modify: `vibetrace/web.py:25`(import)、`:35`(_CHAT_HTML)、`:49-51`(index)
- Modify: `vibetrace/web_chat.html:55` 后(加 `var TREE = $tree_data;` 数据管线)
- Test: `tests/test_web_index.py`(新建,TestClient)

**Interfaces:**
- Consumes: `filetree.tree_payload`(Task 1)、`inline_json`(webserve)、`redact_data`/`redact_secrets`(config,已 import)。
- Produces: `GET /`(可带 `?project=`)返回注入 `$tree_data` 的对话页 HTML(双层脱敏)。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_index.py(新建)
import unittest
import warnings
from unittest import mock

from fastapi.testclient import TestClient

from vibetrace import web


class TestWebIndex(unittest.TestCase):
    def _client(self):
        with warnings.catch_warnings():                  # 屏蔽 starlette/httpx 依赖弃用噪音,保持输出 pristine
            warnings.simplefilter("ignore")
            return TestClient(web.app)

    def test_index_renders_tree_data(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = TestClient(web.app).get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("var TREE", r.text)                # $tree_data 已替换注入
        self.assertNotIn("$tree_data", r.text)           # 占位已消费

    def test_index_double_redaction(self):
        # 注入含 secret 模式的合成路径 → 出口须 [REDACTED]、原 secret 不漏
        payload = {"nodes": {"name": "", "type": "dir", "changed": True,
                             "children": [{"name": "k.py", "type": "file",
                                           "path": "sk-abcdef0123456789ABCDEF/k.py",
                                           "code": " M", "label": "已修改"}]},
                   "status": [{"path": "sk-abcdef0123456789ABCDEF/k.py", "code": " M", "label": "已修改"}]}
        with mock.patch.object(web.filetree, "tree_payload", return_value=payload):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = TestClient(web.app).get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("[REDACTED]", r.text)
        self.assertNotIn("sk-abcdef0123456789ABCDEF", r.text)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_web_index -v`
Expected: FAIL — `var TREE` 不在输出(index 仍原样吐 _CHAT_HTML,未注入)。

- [ ] **Step 3: 实现 web.py Template 化 + index 渲染 + web_chat 占位**

`vibetrace/web.py:25` import 行加 `filetree`:

```python
from . import chat, console, filetree, tunnel
```

`vibetrace/web.py` 顶部 import 区补两行(`Path` 已 import):

```python
from string import Template
from .webserve import inline_json
```

`vibetrace/web.py:35` `_CHAT_HTML` 改 Template:

```python
_CHAT_HTML = Template((Path(__file__).parent / "web_chat.html").read_text(encoding="utf-8"))
```

`vibetrace/web.py:49-51` index 改按请求渲染:

```python
@app.get("/")
def index(project: Optional[str] = None):
    pp = _project(project)
    html = _CHAT_HTML.substitute(tree_data=inline_json(redact_data(filetree.tree_payload(pp))))
    return HTMLResponse(redact_secrets(html))
```

`vibetrace/web_chat.html:55`(`var turn = 0;` 下一行)加数据管线占位:

```javascript
var TREE = $tree_data;
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_web_index -v` → PASS（含双层脱敏）。
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` → OK。
Check: `grep -c "\$" vibetrace/web_chat.html` → 1（仅 `$tree_data`）。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/web.py vibetrace/web_chat.html tests/test_web_index.py
git commit -m "feat(web): index 按请求注入文件树(Template + 双层脱敏,TestClient 锁)"
```

---

### Task 3: web_chat.html 抽屉 + 折叠树 + 点击填 `#q`/带 `target`

**Files:**
- Modify: `vibetrace/web_chat.html`(抽屉按钮/容器、`var pendingTarget`、`renderFiletree`、绑键循环、fetch body 加 target、CSS)
- Test: `tests/test_web_chat.py`(新建,HTML 文本标记)

**Interfaces:**
- Consumes: 注入的 `var TREE = {nodes, status}`(Task 2)、已有 `esc()`(web_chat.html:74)、`#q`/`#f`(对话框/表单)。
- Produces: 抽屉 UI + `renderFiletree()` + 点击接线 + `target` 入 fetch body。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_chat.py(新建)
import unittest
from pathlib import Path

from vibetrace import web


class TestWebChatFiletree(unittest.TestCase):
    def setUp(self):
        self.html = (Path(web.__file__).parent / "web_chat.html").read_text(encoding="utf-8")

    def test_drawer_and_render_present(self):
        self.assertIn('id="filesbtn"', self.html)
        self.assertIn('id="ftdrawer"', self.html)
        self.assertIn("function renderFiletree", self.html)
        self.assertIn("<details", self.html)             # 原生折叠

    def test_click_wires_q_and_target(self):
        self.assertIn("pendingTarget", self.html)        # 点文件记 target
        self.assertIn('querySelectorAll(".ftf")', self.html)  # 树节点绑键循环
        self.assertIn('"Enter"', self.html)              # 树 keydown(Tab handler 在 :65,Enter 为树独有)
        self.assertIn('" "', self.html)                  # Space + preventDefault
        self.assertIn('target: pendingTarget', self.html)  # fetch body 带 target
        self.assertIn("pendingTarget = null", self.html)   # 发送后清空,防误带

    def test_safety_and_invariants(self):
        self.assertIn('data-path="\'+esc(', self.html)   # 路径经 esc 转义
        self.assertIn(".children.length", self.html)     # 空树守卫判 children
        self.assertNotIn("${", self.html)                # 禁模板字面量
        self.assertEqual(self.html.count("$"), 1)        # 唯一 $ = $tree_data 占位
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_web_chat -v`
Expected: FAIL — `id="filesbtn"` 等标记不存在。

- [ ] **Step 3: 实现抽屉 + 树 + 接线**

(a) `vibetrace/web_chat.html` `<main>` 内(`<form id="f">` 之前,或顶部标题处)加按钮 + 抽屉容器:

```html
  <button id="filesbtn" type="button">文件 ▸</button>
  <aside id="ftdrawer" hidden></aside>
```

(b) CSS(`<style>` 内任意位置):

```css
#ftdrawer{position:fixed;top:0;right:0;width:min(80vw,340px);height:100vh;overflow:auto;
  background:#0f0f12;border-left:1px solid rgba(255,255,255,.12);padding:12px;z-index:30;
  font:13px/1.7 ui-monospace,monospace}
#ftdrawer[hidden]{display:none}
.ftf{cursor:pointer;border-radius:4px}
.ftf:hover,.ftf:focus{background:rgba(255,255,255,.06);outline:none}
.ftf.del{opacity:.5;text-decoration:line-through}
.stb{font-size:11px;opacity:.7;margin-left:6px}
.st-M{color:#e3b341}.st-A{color:#3fb950}.st-D{color:#f85149}
.st-R{color:#a371f7}.st-C{color:#a371f7}.st-U{color:#f85149}
```

(c) `<script>` 内(`var TREE = $tree_data;` 之后)加 `pendingTarget` + 渲染 + 绑键 + 抽屉切换:

```javascript
var pendingTarget = null;
function renderFiletree(){
  var T = TREE && TREE.nodes;
  var dr = document.getElementById("ftdrawer");
  if (!T || !T.children || !T.children.length){
    dr.innerHTML = '<p class="hint">无文件或非 git 仓。</p>'; return; }
  function mark(code){ return code ? code.replace(/ /g,"").charAt(0) : ""; }
  function nodeHtml(node, depth){
    var pad = ' style="padding-left:'+(depth*14)+'px"';
    if (node.type === "file"){
      var m = mark(node.code);
      var cls = "ftf" + (m ? " st-"+esc(m) : "")
        + (node.code && node.code.indexOf("D")>=0 ? " del" : "");
      var badge = node.label ? ' <span class="stb">'+esc(node.label)+'</span>' : "";
      return '<div class="'+cls+'" data-path="'+esc(node.path)+'" role="button"'
        + ' tabindex="0"'+(node.label?' title="'+esc(node.label)+'"':"")+pad+'>'
        + esc(node.name)+badge+'</div>';
    }
    var kids = node.children.map(function(c){ return nodeHtml(c, depth+1); }).join("");
    return '<details'+(node.changed?" open":"")+'><summary'+pad+'>'+esc(node.name)
      + '</summary>'+kids+'</details>';
  }
  dr.innerHTML = '<div class="hint">点变更文件 → 接地追问</div>'
    + T.children.map(function(c){ return nodeHtml(c, 0); }).join("");
  dr.querySelectorAll(".ftf").forEach(function(el){
    function act(){
      var p = el.getAttribute("data-path");
      document.getElementById("q").value = "这个文件当初为什么改:" + p;
      pendingTarget = p;
      document.getElementById("q").focus();
      dr.hidden = true;
    }
    el.addEventListener("click", act);
    el.addEventListener("keydown", function(e){
      if (e.key==="Enter" || e.key===" "){ e.preventDefault(); act(); } });
  });
}
document.getElementById("filesbtn").addEventListener("click", function(){
  var dr = document.getElementById("ftdrawer"); dr.hidden = !dr.hidden; });
renderFiletree();
```

(d) `vibetrace/web_chat.html:131` fetch body 加 target,并在发送后清空。把:

```javascript
    body: JSON.stringify({ question:q, conv_id:convId, turn_seq:turn++ }) })
```

改为:

```javascript
    body: JSON.stringify({ question:q, conv_id:convId, turn_seq:turn++, target: pendingTarget }) })
```

并在该 fetch 语句**之前**(读取 `q` 后、发送前,如 `:127` 清空 `#q` 附近)加一行清空 pendingTarget 的暂存(发送用局部变量避免竞态):

```javascript
  var sendTarget = pendingTarget; pendingTarget = null;   // 本条带 target,下一条普通提问不误带
```

并把 fetch body 的 `target: pendingTarget` 改为 `target: sendTarget`(用暂存值发送)。

> 注:测试断言 `target: pendingTarget` 与 `pendingTarget = null`——实现保留 `pendingTarget` 标识名即可(`sendTarget = pendingTarget; pendingTarget = null; ... target: sendTarget`)。两个断言均命中(`target: ` 行含 `pendingTarget` 字样在赋值处、`pendingTarget = null` 在清空处)。**为让 `assertIn('target: pendingTarget')` 精确命中**,实现写成:`var sendTarget = pendingTarget; pendingTarget = null;` 后 fetch body 用 `target: sendTarget`——则断言应改匹配实际代码。落地者:**以下二选一并使测试与实现一致**——(i) fetch 直接 `target: pendingTarget` 且在 `.then(...)` 完成回调里 `pendingTarget=null`;(ii) 暂存式 `sendTarget`。本计划选 (i) 简洁:fetch body `target: pendingTarget`,并在请求发起后同步 `pendingTarget = null`(下一行),JSON.stringify 已在置空前求值,无竞态。

最终采用 (i):fetch body 用 `target: pendingTarget`;在 `fetch(...)` 调用语句**整体之后**紧跟一行 `pendingTarget = null;`(`JSON.stringify` 在 fetch 实参求值时已读取当前 `pendingTarget`,故置空不影响本次请求,且清掉下一条)。测试两断言 `target: pendingTarget` 与 `pendingTarget = null` 均命中。

- [ ] **Step 4: 跑测试 + 静态扫描确认通过**

Run: `python3 -m unittest tests.test_web_chat -v` → PASS。
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` → OK。
Run: `python3 -m scripts.check_static_no_external vibetrace/web_chat.html` → exit 0。
Check: `grep -c "\$" vibetrace/web_chat.html` → 1。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/web_chat.html tests/test_web_chat.py
git commit -m "feat(web): 对话页文件抽屉 + 折叠树 + 点击预填 #q/带 target"
```

---

## Self-Review(对 spec 逐条核对)
- **spec 覆盖**:tree_payload + console 消重 = Task 1;web.py Template+index+双层脱敏+TestClient = Task 2;web_chat 抽屉/树/绑键/点击填#q/target/空树守卫/esc/$ 不变量 = Task 3。三层测试(tree_payload 单测 / web_index TestClient / web_chat 标记)全 CI。
- **占位符扫描**:无 TBD;每步完整代码 + 确切命令。
- **类型一致**:`tree_payload → {"nodes","status"}` 跨 Task 1(产)/Task 2(web.index 注入)/console(消费 `tp["status"]`/`tp["nodes"]`)一致;web.index `substitute(tree_data=...)` ⟺ web_chat `$tree_data` ⟺ `var TREE`(Task 2)⟺ Task 3 消费 `TREE.nodes` 一致;`pendingTarget`/`target` 跨 Task 3 click→fetch 一致。
- **红线**:filetree 纯 stdlib 不 import web;web 惰性 import 不变;双层脱敏在 web.index;`$` 计数==1 + 无 `${}`;check_static_no_external 在 Task 3;filetree.py <300。
- **Vibe-Watch**(落地 commit 留):esc/nodeHtml 现 4+ 份拷贝,新增第 5 份(web_chat 树渲染);第 3 个 JS 消费者或漂移时抽 `vibetrace/static/filetree.js`。
