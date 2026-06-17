# 决策影响图(`graph`)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 vibetrace 加 `vibetrace graph` —— 把"哪个决策沿时间向前牵动了哪些后续改动"装配成单文件 HTML(时间轴 DAG + 点击展开下游列表),纯本地零 LLM。

**Architecture:** 复用现成数据(`Vibe-Decision` 面包屑 + 已缓存叙事 `decisions` + 胶囊 + git 文件历史)。`graph.py` 装配 nodes/edges/徽标(像 `debt.py` 纯本地可独立测),注入 `graph.html` 模板(像 `course.py`/`tunnel.py`)。边=文件级,节点稀疏(仅决策性 commit + top-N=40 + 每决策画最近 8 条出边)。

**Tech Stack:** Python 3.11+,仅标准库 + anthropic SDK;**不引任何图库**(手写 SVG/CSS/JS);stdlib `unittest`;git 子进程(经现有 gitlog);SQLite 缓存。源于已批准 spec `docs/superpowers/specs/2026-06-17-decision-impact-graph-design.md`。

## Global Constraints
- Python 3.11+;**仅标准库 + anthropic SDK**,禁第三方(含 d3 等图库)。
- 每模块改后 **< 300 行**。
- 测试用 **stdlib `unittest`**(非 pytest),仓库根目录 `python3 -m unittest discover -s tests`。
- 解析外部数据(git/缓存)**必须容错**:失败记警告并降级,绝不崩溃。
- **隐私红线**:写盘(缓存 / HTML)前对所有文案 `redact_secrets`。
- 缓存:commit 叙事按 SHA 不可变;派生行用前缀键(`graph:<head>`),复用 `commit_narratives` 表,不加表。
- **`graph` 全程零 LLM**:不构造 `LLMClient`。
- 每次 `git commit` 末尾附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`;关键取舍留 `Vibe-Decision:` trailer(吃狗粮)。
- **string.Template 陷阱**:`graph.html` 里除 `$project`/`$data`/`$generated` 三个占位符外,**不得出现裸 `$`**——JS 一律用字符串拼接(`'a'+x`),**不要用 `${}` 模板字面量**(会被 `Template.substitute` 当占位符而报错)。

## 文件结构
| 文件 | 职责 | 改动 |
|---|---|---|
| `vibetrace/cache.py` | SQLite 缓存 | `recent_open_loops` WHERE 加第 4 子句排除 `graph:%` |
| `vibetrace/graph.py` | **新建**:装配 + 注入 | `_assemble`(纯数据,可测)、`build_graph`(collect→cache→注入→写盘) |
| `vibetrace/graph.html` | **新建**:模板 | 时间轴 DAG + 点击展开下游列表,手写 SVG/CSS/JS |
| `vibetrace/cli.py` | CLI | `graph` 子命令 |
| `tests/` | unittest | `test_cache_filter` 扩 `graph:` 行;新 `test_graph.py`、`test_cli_graph.py` |

`gitlog.py` 不改 —— 复用 `collect_commit_files` / `commit_body` / `parse_breadcrumbs`。

---

## Task 1: cache.recent_open_loops 排除 `graph:%`(防污染简报)

**Files:**
- Modify: `vibetrace/cache.py`(`recent_open_loops` 的 SQL)
- Modify: `tests/test_cache_filter.py`(加 `graph:` 行断言)

**Interfaces:**
- Consumes: 现有 `recent_open_loops(project, limit=10)`(WHERE 已排除 `digest:/ask:/course:`)。
- Produces: 无新接口,行为收紧。

- [ ] **Step 1: 改测试,加 `graph:` 行(先让它失败)**

把 `tests/test_cache_filter.py` 的 `test_excludes_ask_course_digest_rows` 方法体改为(在三行派生行后再加一行 `graph:`):
```python
    def test_excludes_ask_course_digest_rows(self):
        c = Cache(":memory:")
        c.put_narrative("realsha", "P", "m", {"open_loops": ["真未闭环"]})
        c.put_narrative("digest:x", "P", "m", {"open_loops": ["不该出现-digest"]})
        c.put_narrative("course:v2:y", "P", "m", {"open_loops": ["不该出现-course"]})
        c.put_narrative("ask:z", "P", "m",
                        {"answer": "a", "open_loops": ["不该出现-ask"]})
        c.put_narrative("graph:head1", "P", "graph",
                        {"open_loops": ["不该出现-graph"]})  # 测试给个 open_loops 逼出过滤
        self.assertEqual(c.recent_open_loops("P"), ["真未闭环"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_cache_filter -v`
Expected: FAIL —— 现 SQL 未排除 `graph:`,结果里混入 `不该出现-graph`(`['真未闭环','不该出现-graph']`)。

- [ ] **Step 3: 改 SQL 加第 4 子句**

`vibetrace/cache.py` 的 `recent_open_loops` 查询,把:
```python
            "AND sha NOT LIKE 'digest:%' AND sha NOT LIKE 'ask:%' "
            "AND sha NOT LIKE 'course:%' "
```
改为(追加一行):
```python
            "AND sha NOT LIKE 'digest:%' AND sha NOT LIKE 'ask:%' "
            "AND sha NOT LIKE 'course:%' AND sha NOT LIKE 'graph:%' "
```
并把该方法 docstring 的"排除 digest:/ask:/course: 派生行"改为"排除 digest:/ask:/course:/graph: 派生行"。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_cache_filter -v`
Expected: PASS。再跑全量:`python3 -m unittest discover -s tests` → 全绿。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/cache.py tests/test_cache_filter.py
git commit -m "fix(cache): recent_open_loops 排除 graph: 派生行(防污染简报)" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: graph._assemble(决策节点 + 文件级边 + top-N + 徽标,纯数据)

**Files:**
- Create: `vibetrace/graph.py`(本任务先放 imports/常量 + `_assemble`)
- Create: `tests/test_graph.py`

**Interfaces:**
- Consumes:
  - `gitlog.commit_body(project_path, sha) -> str`、`gitlog.parse_breadcrumbs(body) -> (decisions, watches)`(模块级 import,便于 monkeypatch)。
  - `cache.all_capsules(project) -> [{capsule_id, sha, risk, outcome, opened}]`、`cache.get_narrative(sha) -> dict|None`(narrative 有 `decisions` 键)。
  - `config.redact_secrets(text) -> str`。
- Produces: `_assemble(commits, project_path, project, cache) -> {"nodes":[{id,date,subject,text,kind,badge,ts}], "edges":[{from,to}]}`。`kind` ∈ `breadcrumb|narrative|change`;`id` = `sha[:7]`;edges 的 from/to 也是 `sha[:7]`。常量 `SCAN_LIMIT=200, TOP_N=40, MAX_OUT=8`。

- [ ] **Step 1: 写失败测试**

`tests/test_graph.py`:
```python
import unittest
from datetime import datetime, timezone
from unittest import mock

from vibetrace import graph
from vibetrace.cache import Cache


def _c(sha, day, files, subject="s"):
    return {"sha": sha, "date": datetime(2026, 6, day, tzinfo=timezone.utc),
            "subject": subject, "files": files}


class TestAssemble(unittest.TestCase):
    def test_breadcrumb_decision_file_edge_not_unrelated(self):
        commits = [_c("d1aaaaaa", 1, ["a.py"]),     # 决策(面包屑)
                   _c("c2bbbbbb", 2, ["a.py"]),     # 后续,碰 a.py → 下游
                   _c("x3cccccc", 3, ["z.py"])]     # 碰无关文件 → 不连
        cache = Cache(":memory:")
        bodies = {"d1aaaaaa": "Vibe-Decision: 用 urllib",
                  "c2bbbbbb": "", "x3cccccc": ""}
        with mock.patch.object(graph, "commit_body", lambda p, s: bodies[s]):
            data = graph._assemble(commits, ".", "P", cache)
        ids = {n["id"]: n for n in data["nodes"]}
        self.assertEqual(ids["d1aaaaa"]["kind"], "breadcrumb")
        self.assertEqual(ids["d1aaaaa"]["text"], "用 urllib")
        froms = {(e["from"], e["to"]) for e in data["edges"]}
        self.assertIn(("d1aaaaa", "c2bbbbb"), froms)        # 同文件、更晚 → 连
        self.assertNotIn(("d1aaaaa", "x3ccccc"), froms)     # 无关文件 → 不连

    def test_narrative_fallback_kind(self):
        commits = [_c("n1aaaaaa", 1, ["a.py"]), _c("c2bbbbbb", 2, ["a.py"])]
        cache = Cache(":memory:")
        cache.put_narrative("n1aaaaaa", "P", "m",
                            {"decisions": ["叙事决策"], "risks": [], "open_loops": []})
        with mock.patch.object(graph, "commit_body", lambda p, s: ""):  # 无面包屑
            data = graph._assemble(commits, ".", "P", cache)
        n = {x["id"]: x for x in data["nodes"]}["n1aaaaa"]
        self.assertEqual(n["kind"], "narrative")
        self.assertEqual(n["text"], "叙事决策")

    def test_capsule_badge_and_redaction(self):
        commits = [_c("d1aaaaaa", 1, ["a.py"])]
        cache = Cache(":memory:")
        cache.seal_capsule("P", "d1aaaaaa", 0, "并发风险", "2026-06-01", "2026-06-22")
        with mock.patch.object(graph, "commit_body",
                               lambda p, s: "Vibe-Decision: token=sk-abcdefghijklmnop1234"):
            data = graph._assemble(commits, ".", "P", cache)
        n = data["nodes"][0]
        self.assertTrue(n["badge"].startswith("胶囊:"))     # 有胶囊 → 徽标
        self.assertNotIn("sk-abcdefghijklmnop1234", n["text"])  # 决策文案脱敏
        self.assertIn("[REDACTED]", n["text"])

    def test_out_edges_capped_at_max_out(self):
        commits = [_c("d1aaaaaa", 1, ["a.py"])] + [
            _c("c%da" % i, i + 2, ["a.py"]) for i in range(12)]  # 12 个后续都碰 a.py
        cache = Cache(":memory:")
        with mock.patch.object(graph, "commit_body",
                               lambda p, s: "Vibe-Decision: x" if s == "d1aaaaaa" else ""):
            data = graph._assemble(commits, ".", "P", cache)
        out = [e for e in data["edges"] if e["from"] == "d1aaaaa"]
        self.assertEqual(len(out), graph.MAX_OUT)            # ≤8,取最近

    def test_empty_commits_no_nodes(self):
        self.assertEqual(graph._assemble([], ".", "P", Cache(":memory:")),
                         {"nodes": [], "edges": []})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_graph -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibetrace.graph'`

- [ ] **Step 3: 建 graph.py(imports/常量 + `_assemble`)**

`vibetrace/graph.py`:
```python
"""Decision-impact graph: which decision rippled into which later changes.

纯本地、零 LLM。节点=决策性 commit(Vibe-Decision 面包屑优先,否则叙事 decisions;
top-N=40 按全量出度),边=文件级(决策 commit → 其后碰了同一文件的 commit,每决策
画最近 8 条)。胶囊作节点徽标。装配成单文件 graph.html(时间轴 DAG + 点击展开下游列表)。
像 debt.py 一样可独立测;像 course/tunnel 一样注入 HTML 模板。
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .gitlog import collect_commit_files, commit_body, parse_breadcrumbs

SCAN_LIMIT = 200
TOP_N = 40
MAX_OUT = 8


def _assemble(commits, project_path, project, cache):
    """commits: oldest-first [{sha,date,subject,files}] → {nodes, edges}。零 LLM。"""
    order = {c["sha"]: i for i, c in enumerate(commits)}
    caps_by_sha = {}
    for cap in cache.all_capsules(project):
        caps_by_sha.setdefault(cap["sha"], []).append(cap)
    info = {}
    for c in commits:
        decisions, _ = parse_breadcrumbs(commit_body(project_path, c["sha"]))
        narr = cache.get_narrative(c["sha"]) or {}
        narr_dec = narr.get("decisions") or []
        if decisions:
            text, kind = decisions[0], "breadcrumb"
        elif narr_dec:
            text, kind = narr_dec[0], "narrative"
        else:
            text, kind = "", ""
        info[c["sha"]] = {"files": set(c["files"] or []), "subject": c["subject"],
                          "date": c["date"], "text": text, "kind": kind}
    decisions = [s for s, v in info.items() if v["text"]]
    full_out = {}
    for d in decisions:
        df, do = info[d]["files"], order[d]
        full_out[d] = [c["sha"] for c in commits          # commits 升序 → 下游升序
                       if order[c["sha"]] > do and (info[c["sha"]]["files"] & df)]
    ranked = sorted(decisions, key=lambda s: (len(full_out[s]), order[s]),
                    reverse=True)[:TOP_N]                  # 按全量出度取 top-N
    ranked_set = set(ranked)
    node_ids, edges = set(ranked), []
    for d in ranked:
        for t in full_out[d][:MAX_OUT]:                    # 时间最近的 8 个
            edges.append((d, t))
            node_ids.add(t)

    def _badge(sha):
        caps = caps_by_sha.get(sha) or []
        if not caps:
            return ""
        done = [redact_secrets(str(c["outcome"])) for c in caps if c.get("outcome")]
        return "胶囊:" + ("、".join(done) if done else "待验证")

    nodes = []
    for sha in node_ids:
        v = info[sha]
        is_dec = sha in ranked_set
        date = v["date"]
        nodes.append({
            "id": sha[:7],
            "date": date.date().isoformat() if hasattr(date, "date") else str(date)[:10],
            "subject": redact_secrets(v["subject"] or ""),
            "text": redact_secrets(v["text"]) if is_dec else "",
            "kind": v["kind"] if is_dec else "change",
            "badge": _badge(sha) if is_dec else "",
            "ts": order[sha],
        })
    nodes.sort(key=lambda n: n["ts"])
    return {"nodes": nodes,
            "edges": [{"from": d[:7], "to": t[:7]} for d, t in edges]}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_graph -v`
Expected: PASS(5 tests)。再跑全量 → 全绿。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/graph.py tests/test_graph.py
git commit -m "feat(graph): _assemble 装配决策节点+文件级边+胶囊徽标(纯本地零LLM)" -m "Vibe-Decision: 边用文件级+稀疏节点而非行级——评审下 Simplicity First,行级作非目标延后" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: graph.html 模板 + graph.build_graph(注入 + 写盘)

**Files:**
- Create: `vibetrace/graph.html`
- Modify: `vibetrace/graph.py`(追加 `build_graph`)
- Modify: `tests/test_graph.py`(加 `build_graph` 端到端结构测试)

**Interfaces:**
- Consumes: `_assemble`(Task 2);`collect_commit_files`、`load_config`、`Cache`、`CACHE_DB_PATH`。
- Produces: `build_graph(project_path, vault=None) -> (output_path: Path, error_or_None)`。写 `<vault>/<project>-graph.html`;无 git 历史 → 空图、返回 `(path, None)`(不报错);git 失败 → `(None, err)`。

- [ ] **Step 1: 写 graph.html 模板**

`vibetrace/graph.html`(完整文件;**JS 全用字符串拼接,无 `${}`,无裸 `$`**):
```html
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>$project · 决策影响图</title>
<style>
:root{--bg:#0e0e0e;--fg:#e8e8e8;--mut:#8a8a8a;--accent:#1783ff;--line:#2c2c2c;--px:ui-monospace,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--px);image-rendering:pixelated}
header{padding:14px 20px;border-bottom:2px solid var(--line)}
h1{margin:0;font-size:15px;letter-spacing:1px}
.sub{color:var(--mut);font-size:11px;margin-top:4px;line-height:1.5}
#wrap{display:flex;height:calc(100vh - 64px)}
#graph{flex:1;overflow:auto}
#panel{width:330px;padding:16px;overflow:auto;border-left:2px solid var(--line)}
.empty{padding:48px;color:var(--mut);text-align:center;line-height:1.8}
svg text{font-family:var(--px);fill:var(--fg)}
.node rect{cursor:pointer}
.dec-b{fill:var(--accent);stroke:#0d4f99;stroke-width:2}
.dec-n{fill:#242424;stroke:var(--accent);stroke-width:2;stroke-dasharray:3 2}
.chg{fill:#161616;stroke:#4a4a4a;stroke-width:2}
.edge{stroke:#4a4a4a;stroke-width:1.5;fill:none;marker-end:url(#a)}
.sel{stroke:#fff !important;stroke-width:3 !important}
#panel h2{font-size:13px;color:var(--accent);margin:0 0 10px}
#panel .txt{font-size:12px;line-height:1.6;margin:0 0 12px;white-space:pre-wrap;word-break:break-word}
#panel ul{padding:0;margin:0}
#panel li{font-size:11px;color:var(--mut);margin:4px 0;list-style:none}
#panel li b{color:var(--fg)}
</style>
</head>
<body>
<header>
  <h1>$project · 决策影响图</h1>
  <div class="sub">决策 → 沿时间向前牵动的改动 · 点蓝色决策节点看下游 · $generated · 纯本地零 LLM</div>
</header>
<div id="wrap">
  <div id="graph"><svg id="svg"></svg><div id="empty" class="empty" hidden>还没有可画的决策。<br>去关键 commit 留 <b>Vibe-Decision:</b> trailer,或先跑 <b>vibetrace digest</b>。</div></div>
  <div id="panel"><div class="sub">点左侧蓝色(实线=面包屑,虚线=叙事)决策节点,查看它牵动了哪些后续改动。</div></div>
</div>
<script>
var DATA = $data;
var NW = 150, NH = 26, GAPX = 64, GAPY = 44, PAD = 30;
var svg = document.getElementById('svg'), panel = document.getElementById('panel');
function esc(t){ return (t || '').replace(/[&<>]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;'}[c]; }); }
function render(){
  var nodes = DATA.nodes, edges = DATA.edges;
  if(!nodes.length){ document.getElementById('empty').hidden = false; return; }
  var xsArr = []; for(var i=0;i<nodes.length;i++){ if(xsArr.indexOf(nodes[i].ts)<0) xsArr.push(nodes[i].ts); }
  xsArr.sort(function(a,b){ return a-b; });
  var xi = {}; for(var j=0;j<xsArr.length;j++){ xi[xsArr[j]] = j; }
  var dl = 0, cl = 0, byId = {};
  for(var k=0;k<nodes.length;k++){
    var n = nodes[k];
    n.x = PAD + xi[n.ts] * (NW + GAPX);
    n.y = (n.kind === 'change') ? (PAD + (6 + (cl++ % 4)) * GAPY) : (PAD + (dl++ % 5) * GAPY);
    byId[n.id] = n;
  }
  var W = PAD * 2 + xsArr.length * (NW + GAPX), H = PAD * 2 + 11 * GAPY;
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  var s = '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#4a4a4a"/></marker></defs>';
  for(var e=0;e<edges.length;e++){
    var a = byId[edges[e].from], b = byId[edges[e].to];
    if(!a || !b) continue;
    var x1 = a.x + NW, y1 = a.y + NH/2, x2 = b.x, y2 = b.y + NH/2;
    s += '<path class="edge" d="M' + x1 + ',' + y1 + ' C' + (x1+30) + ',' + y1 + ' ' + (x2-30) + ',' + y2 + ' ' + x2 + ',' + y2 + '"/>';
  }
  for(var m=0;m<nodes.length;m++){
    var nd = nodes[m];
    var cls = nd.kind === 'breadcrumb' ? 'dec-b' : (nd.kind === 'narrative' ? 'dec-n' : 'chg');
    var lbl = esc((nd.text || nd.subject || '').slice(0, 22));
    s += '<g class="node" data-id="' + nd.id + '">';
    s += '<rect class="' + cls + '" x="' + nd.x + '" y="' + nd.y + '" width="' + NW + '" height="' + NH + '" rx="3"/>';
    s += '<text x="' + (nd.x + 6) + '" y="' + (nd.y + 17) + '" font-size="10">' + lbl + '</text>';
    if(nd.badge){ s += '<text x="' + (nd.x + NW - 8) + '" y="' + (nd.y - 4) + '" font-size="11" fill="#1783ff">●</text>'; }
    s += '</g>';
  }
  svg.innerHTML = s;
  var gs = svg.querySelectorAll('.node');
  for(var g=0;g<gs.length;g++){ gs[g].addEventListener('click', (function(id){ return function(){ showPanel(id); }; })(gs[g].getAttribute('data-id'))); }
}
function showPanel(id){
  var rects = svg.querySelectorAll('rect');
  for(var i=0;i<rects.length;i++){ rects[i].classList.remove('sel'); }
  var g = svg.querySelector('.node[data-id="' + id + '"]');
  if(g){ g.querySelector('rect').classList.add('sel'); }
  var n = null, dn = DATA.nodes;
  for(var k=0;k<dn.length;k++){ if(dn[k].id === id){ n = dn[k]; break; } }
  if(!n) return;
  var downs = [];
  for(var e=0;e<DATA.edges.length;e++){
    if(DATA.edges[e].from === id){
      for(var x=0;x<dn.length;x++){ if(dn[x].id === DATA.edges[e].to){ downs.push(dn[x]); break; } }
    }
  }
  var kindTxt = n.kind === 'breadcrumb' ? '决策(面包屑)' : (n.kind === 'narrative' ? '决策(叙事)' : '改动');
  var h = '<h2>[' + n.id + '] ' + kindTxt + ' · ' + esc(n.date) + '</h2>';
  if(n.text){ h += '<div class="txt">' + esc(n.text) + '</div>'; }
  if(n.badge){ h += '<div class="txt" style="color:var(--accent)">' + esc(n.badge) + '</div>'; }
  h += '<div class="sub">牵动的后续改动(' + downs.length + '):</div><ul>';
  for(var d=0;d<downs.length;d++){ h += '<li><b>[' + downs[d].id + ']</b> ' + esc(downs[d].subject) + '</li>'; }
  h += '</ul>';
  panel.innerHTML = h;
}
render();
</script>
</body>
</html>
```

- [ ] **Step 2: 写 build_graph 的失败测试**

把下面方法加入 `tests/test_graph.py` 的一个新类(用真实临时 git 仓库 + 真实 Cache 文件,验证端到端写盘):
```python
import shutil, subprocess, tempfile
from pathlib import Path


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class TestBuildGraph(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        p = Path(self.dir)
        (p / "a.py").write_text("x\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c1\n\nVibe-Decision: 决策一"], self.dir)
        (p / "a.py").write_text("y\n")
        _git(["add", "."], self.dir)
        _git(["commit", "-q", "-m", "c2 改 a.py"], self.dir)
        self.vault = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.vault, ignore_errors=True)

    def test_build_writes_html_with_decision(self):
        out, err = graph.build_graph(self.dir, vault=self.vault)
        self.assertIsNone(err)
        self.assertTrue(out.exists())
        html = out.read_text(encoding="utf-8")
        self.assertIn("决策影响图", html)
        self.assertIn("决策一", html)          # 决策文案注入了
        self.assertIn('"nodes"', html)          # 数据 JSON 注入了

    def test_empty_repo_writes_empty_graph_not_error(self):
        empty = tempfile.mkdtemp()
        _git(["init", "-q"], empty)
        try:
            out, err = graph.build_graph(empty, vault=self.vault)
            self.assertIsNone(err)               # LOW-3:空仓不报错
            self.assertTrue(out.exists())
        finally:
            shutil.rmtree(empty, ignore_errors=True)
```

Run: `python3 -m unittest tests.test_graph -v`
Expected: FAIL — `AttributeError: module 'vibetrace.graph' has no attribute 'build_graph'`

- [ ] **Step 3: 追加 build_graph 到 graph.py**

在 `vibetrace/graph.py` 末尾追加:
```python
def build_graph(project_path, vault=None):
    """→ (output_path, error_or_None)。无 git 历史→空图 exit 0(不报错)。"""
    cfg = load_config()
    if vault:
        cfg["vault_path"] = vault
    pp = Path(project_path).resolve()
    project = pp.name
    commits, err = collect_commit_files(pp)
    if err:
        return None, err
    commits = commits[-SCAN_LIMIT:]                 # graph.py 自己截断最近 200
    cache = Cache(CACHE_DB_PATH)
    head = commits[-1]["sha"] if commits else "empty"
    key = "graph:" + head[:40]
    cached = cache.get_narrative(key)
    if cached and "nodes" in cached:
        data = cached
    else:
        data = _assemble(commits, pp, project, cache)
        cache.put_narrative(key, project, "graph", data)
    cache.close()
    today = datetime.now(timezone.utc).astimezone().date()
    template = Template((Path(__file__).parent / "graph.html")
                        .read_text(encoding="utf-8"))
    html = template.substitute(
        project=project,
        data=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
        generated="%04d.%02d.%02d" % (today.year, today.month, today.day))
    vault_dir = Path(cfg["vault_path"]).expanduser()
    vault_dir.mkdir(parents=True, exist_ok=True)
    out = vault_dir / (project + "-graph.html")
    out.write_text(html, encoding="utf-8")
    return out, None
```

- [ ] **Step 4: 跑测试确认通过 + 行数**

Run: `python3 -m unittest tests.test_graph -v` → PASS(全部)。
Run: `python3 -m unittest discover -s tests` → 全绿。
Run: `wc -l vibetrace/graph.py` → 应 < 300(预期 ~95)。

- [ ] **Step 5: 手动浏览器核验(HTML 无法 unittest)**

Run: `python3 -m vibetrace graph --project . --vault /tmp/vt-graph`
打开 `/tmp/vt-graph/CodeTalk-graph.html`,确认:时间轴 DAG 渲染、蓝色决策节点可点、点击后右栏列出下游。若布局错位/JS 报错,修 graph.html 再来(注意 `$` 陷阱)。

- [ ] **Step 6: 提交**

```bash
git add vibetrace/graph.html vibetrace/graph.py tests/test_graph.py
git commit -m "feat(graph): graph.html 时间轴DAG+下游列表 + build_graph 注入写盘" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: cli graph 子命令

**Files:**
- Modify: `vibetrace/cli.py`
- Create: `tests/test_cli_graph.py`

**Interfaces:**
- Consumes: `graph.build_graph(project_path, vault=None) -> (path, err)`。
- Produces: `vibetrace graph [--project P] [--vault V]` 子命令;成功打印路径返回 0,err 打 stderr 返回 2。

- [ ] **Step 1: 写失败测试**

`tests/test_cli_graph.py`:
```python
import unittest
from unittest import mock

from vibetrace import cli, graph


class TestCliGraph(unittest.TestCase):
    def test_graph_subcommand_dispatches(self):
        got = {}

        def fake_build(project_path, vault=None):
            got.update(p=project_path, v=vault)
            return ("/tmp/x-graph.html", None)

        with mock.patch.object(graph, "build_graph", fake_build):
            rc = cli.main(["graph", "--project", ".", "--vault", "/tmp/v"])
        self.assertEqual(rc, 0)
        self.assertEqual(got, {"p": ".", "v": "/tmp/v"})


if __name__ == "__main__":
    unittest.main()
```

Run: `python3 -m unittest tests.test_cli_graph -v`
Expected: FAIL — argparse "invalid choice: 'graph'"。

- [ ] **Step 2: 加 subparser + 分派**

`vibetrace/cli.py` `main` 里,在 `ask` 的 subparser 之后、`args = parser.parse_args(argv)` 之前:
```python
    grp = sub.add_parser("graph", help="决策影响图(决策→下游改动,纯本地零 LLM)")
    grp.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    grp.add_argument("--vault", help="覆盖输出目录")
```
在 `if args.command == "ask":` 分派块之后、`return digest(args)` 之前:
```python
    if args.command == "graph":
        from .graph import build_graph
        path, err = build_graph(args.project, vault=args.vault)
        if err:
            print(f"错误:{err}", file=sys.stderr)
            return 2
        print(f"图谱已写入:{path}")
        return 0
```

- [ ] **Step 3: 跑测试确认通过 + help**

Run: `python3 -m unittest tests.test_cli_graph -v` → PASS。
Run: `python3 -m vibetrace graph --help` → 显示 `--project`/`--vault`。
Run: `python3 -m unittest discover -s tests` → 全绿。
Run: `wc -l vibetrace/cli.py` → < 300。

- [ ] **Step 4: 提交**

```bash
git add vibetrace/cli.py tests/test_cli_graph.py
git commit -m "feat(cli): 新增 graph 子命令分派到 build_graph" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: 验收(纯本地可复现)

**Files:** 无代码改动;运行验证并把结果追加到本计划"验收记录"。

- [ ] **Step 1: 全量回归 + 行数**

Run: `python3 -m unittest discover -s tests -v` → 全绿(含新 test_graph / test_cli_graph,test_cache_filter 扩展)。
Run: `wc -l vibetrace/*.py` → 每个 < 300。

- [ ] **Step 2: 零 LLM 校验**

Run: `grep -n "LLMClient\|llm" vibetrace/graph.py` → 期望**无任何 LLMClient 引用**(graph.py import 不含 llm)。

- [ ] **Step 3: 验收 #1/#3 — 真仓出图 + 决策节点**

Run: `python3 -m vibetrace graph --project . --vault /tmp/vt-graph`
打开 HTML;确认时间轴 DAG 出现、`c60655f`("watch→risks"那条 `Vibe-Decision`)作为**实线**决策节点出现;点它 → 右栏列出其下游改动 + 决策原文 +(若有)胶囊徽标。

- [ ] **Step 4: 验收 #2 — 文件级边正确**

造一个改 `vibetrace/enrich.py` 的后续小 commit(或观察现有改 enrich.py 的 commit),重跑 `graph`(注意:`graph:<head>` 缓存按 HEAD;HEAD 变即重算),确认它连为相关决策的下游;只改无关文件的 commit 不连。验证后回滚临时 commit:`git reset --hard HEAD~1`(若造了)。

- [ ] **Step 5: 验收 #4 — 空仓不崩**

Run: `cd /tmp && git init -q vt-empty && python3 -m vibetrace graph --project /tmp/vt-empty --vault /tmp/vt-graph; echo "exit=$?"`
Expected: 写出空图、`exit=0`、提示"还没有可画的决策"。清理:`rm -rf /tmp/vt-empty`。

- [ ] **Step 6: 记录并提交**

把 #1 看到的决策节点、#2 的边验证结果摘要追加到本计划"验收记录",然后:
```bash
git add docs/superpowers/plans/2026-06-17-decision-impact-graph.md
git commit -m "docs: 记录决策影响图验收结果" -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## 验收记录(2026-06-17 执行)
- **#1 决策节点**:真仓生成 `CodeTalk-graph.html` = 29 节点 / 85 边,kind `{narrative:19, change:7, breadcrumb:3}`。"watch→risks" 的 `Vibe-Decision`(PR#8 squash 后落在 `9b391e9`)及 `f86c2fb`/`063a861` 均以 **breadcrumb 实线节点**出现。(原 spec 写的 `c60655f` 因 squash 合并已不在历史,等价节点为 `9b391e9`。)
- **#2 文件级边**:由 `tests.test_graph`(含 nearest-8 身份断言)覆盖;真图 85 条决策→下游边佐证。
- **#3 下游列表**:`graph.html` `showPanel` 渲染点击决策的下游;结构 + 手动核验通过。
- **#4 空仓**:`graph --project <空 git 仓>` 写空图、`exit 0`、不崩(亦由 `test_empty_repo_writes_empty_graph_not_error` 覆盖)。
- **#5 行数 / 零 LLM**:各模块 <300(graph.py 118,最大 cli.py 232);`grep LLMClient graph.py` = 0。
- **#6 隐私 / 过滤**:文案经 `_assemble` `redact_secrets`(`test_capsule_badge_and_redaction` 覆盖);`graph:` 行不污染简报(`test_cache_filter` 覆盖)。注入无裸 `$data` 残留。
- 全量 **31/31** 单测通过。
- Minor(留终审):`test_cli_graph` 让 cli 的 `决策图已写入:…` print 泄进套件输出,可用 `contextlib.redirect_stdout` 收敛。
