# 答案内逐字命中片段高亮 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) tracking.

**Goal:** web 接地对话答案里零-LLM 确定性高亮逐字源自被引**纯原话**的片段,链回来源。

**Architecture:** 新 `highlight.py` 纯函数 `segments(answer, citations)` 返回**已切好的交替段** `[{text, cite_id}]`(Python 切片,拼接===answer)→ `retrieval._citation` 加 `verbatim`(纯原话,非 render_hit)→ `chat.answer`/`answer_stream.done` 带 `highlights` → `web_chat.html` done 时单一 `setBody` 切段重渲染 `<mark>`+legend、chip 加 `dataset.cite` 锚点。

**Tech Stack:** Python stdlib `difflib`;零-build vanilla-JS;stdlib unittest。

## Global Constraints
- 仅 stdlib(`difflib`);`highlight.py`/`chat.py`/`retrieval.py` 各 <300;零 LLM(`grep LLMClient vibetrace/highlight.py` = 0)。
- 后端返切好的段(非裸 offset)——消灭 Python 码位 vs JS UTF-16 错位;前端只 esc 拼接、不切片。
- 匹配 `cit["verbatim"]`(纯原话)**绝不**匹配 `render_hit`/脚手架(R6 诚实红线)。
- web:单一 `setBody(html)` 唯一 `innerHTML=` sink;每段 `esc()`,只 `<mark>` 标签字面;段拼接≠累积答案→回退 `setBody(esc(acc))`;空 highlights→不重渲染。禁 `${}`;前端零外链(`check_static_no_external`)。
- 范围仅 web;ask 不动。数据不出本机;web.py 出口脱敏不变。

---

### Task 1: `highlight.segments()`(纯函数切段)

**Files:** Create `vibetrace/highlight.py`、Test `tests/test_highlight.py`

**Interfaces:** Produces `segments(answer, citations) -> list[{"text": str, "cite_id": int|None}]`(拼接===answer;无 ≥MIN_SPAN 命中→`[]`;`answer` None/空→`[]`)。Consumes citation `{id, verbatim}`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_highlight.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace.highlight import segments, MIN_SPAN


def _cit(i, vb):
    return {"id": i, "verbatim": vb}


class TestSegments(unittest.TestCase):
    def test_verbatim_hit_segments_concat_to_answer(self):
        ans = "模型综合:这是一段真实原话内容,以及别的话"
        segs = segments(ans, [_cit(0, "这是一段真实原话内容")])
        self.assertEqual("".join(s["text"] for s in segs), ans)   # 拼接===answer
        hot = [s for s in segs if s["cite_id"] == 0]
        self.assertTrue(any("这是一段真实原话内容" in s["text"] for s in hot))

    def test_scaffolding_not_matched_redline(self):
        # 脚手架词不在 verbatim → 不高亮(只匹配纯原话,守 R6)
        segs = segments("从测试场景反推设计了重试", [_cit(0, "用显式循环重试")])
        self.assertEqual(segs, [])                                # 「重试」<MIN_SPAN、脚手架不在 verbatim

    def test_short_below_min_span_filtered(self):
        self.assertEqual(segments("abc 重试 def", [_cit(0, "重试")]), [])

    def test_paraphrase_no_overlap_empty(self):
        self.assertEqual(segments("完全不同的综合表述方式", [_cit(0, "另一段毫不相干的原话")]), [])

    def test_overlap_deterministic_non_overlapping(self):
        ans = "AAABBBCCCDDDEEE 公共逐字片段 尾"
        segs = segments(ans, [_cit(0, "公共逐字片段"), _cit(1, "公共逐字片段")])
        self.assertEqual("".join(s["text"] for s in segs), ans)
        hot = [s for s in segs if s["cite_id"] is not None]
        # 互不重叠 + 命中段归一个确定来源(tie-break:cite 0 先)
        self.assertTrue(hot and all(s["cite_id"] == 0 for s in hot))

    def test_empty_and_none(self):
        self.assertEqual(segments("", [_cit(0, "x" * 10)]), [])
        self.assertEqual(segments(None, [_cit(0, "x" * 10)]), [])
        self.assertEqual(segments("有内容但无引用", []), [])

    def test_autojunk_false_long_evidence(self):
        vb = ("重复段落 " * 60) + "唯一可命中的逐字尾巴片段"
        ans = "答案里嵌入 唯一可命中的逐字尾巴片段 收尾"
        segs = segments(ans, [_cit(0, vb)])
        self.assertTrue(any(s["cite_id"] == 0 for s in segs))     # autojunk=False 不丢
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_highlight -v` → FAIL `ModuleNotFoundError: vibetrace.highlight`.

- [ ] **Step 3: 实现**

```python
# vibetrace/highlight.py
"""答案内逐字命中片段切分(零 LLM,纯 stdlib difflib)。

把 LLM 答案按「与被引材料纯原话(citation.verbatim)逐字重叠 ≥MIN_SPAN」切成交替段
[{text, cite_id}](cite_id=None 普通段、带 id 命中段),**段拼接 === answer**,供前端只 esc
拼接、不切片(消灭 Python 码位 vs JS UTF-16 下标错位)。只匹配纯原话(非 render_hit 脚手架)、
只标逐字命中下界——非语义归因/幻觉检测。
"""
import difflib

MIN_SPAN = 6


def segments(answer, citations):
    """answer + citations([{id, verbatim, ...}]) → [{text, cite_id|None}](拼接===answer)。
    无 ≥MIN_SPAN 逐字命中 / answer 空 / None → []。"""
    answer = answer or ""
    spans = []                                       # (start, end, cite_id)
    for cit in citations or []:
        vb = cit.get("verbatim") or ""
        if not vb:
            continue
        sm = difflib.SequenceMatcher(None, answer, vb, autojunk=False)
        for blk in sm.get_matching_blocks():         # 末尾哨兵 size=0 自然被 >=MIN_SPAN 滤掉
            if blk.size >= MIN_SPAN:
                spans.append((blk.a, blk.a + blk.size, cit.get("id")))
    if not spans:
        return []
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0]),
                              s[2] if s[2] is not None else -1))
    chosen, last_end = [], 0
    for st, en, cid in spans:
        if st >= last_end:                           # 贪心:按 start、长者优先、不重叠
            chosen.append((st, en, cid))
            last_end = en
    out, pos = [], 0
    for st, en, cid in chosen:
        if st > pos:
            out.append({"text": answer[pos:st], "cite_id": None})
        out.append({"text": answer[st:en], "cite_id": cid})
        pos = en
    if pos < len(answer):
        out.append({"text": answer[pos:], "cite_id": None})
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_highlight -v` → PASS(7)。`wc -l vibetrace/highlight.py` <300。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/highlight.py tests/test_highlight.py
git commit -m "feat(highlight): segments 答案逐字命中切段(零 LLM,后端切片防跨语言错位)"
```

---

### Task 2: `retrieval._citation` 加 `verbatim` + `chat` 带 `highlights`

**Files:** Modify `vibetrace/retrieval.py`(加 `_verbatim` + `_citation` 加字段)、`vibetrace/chat.py`(import + answer/answer_stream)、Test `tests/test_retrieval_verbatim.py` + `tests/test_grounded_chat.py`(加用例)

**Interfaces:** Consumes `highlight.segments`、hit 的 `why`/`decisions`/`evidence[].prompts·excerpts`。Produces citation 增 `"verbatim"`;`chat.answer` 返回 + `answer_stream` done 增 `"highlights"`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_retrieval_verbatim.py
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vibetrace import retrieval


class TestCitationVerbatim(unittest.TestCase):
    def test_verbatim_pure_quotes_no_scaffolding(self):
        hit = {"sha": "a" * 40, "kind": "commit", "why": "因为要支持流式",
               "decisions": ["用显式循环重试"],
               "evidence": [{"prompts": ["把重试改成循环"], "excerpts": ["原话片段"]}],
               "test_refs": [], "pr_refs": []}
        c = retrieval._citation(3, hit)
        self.assertIn("verbatim", c)
        vb = c["verbatim"]
        self.assertIn("用显式循环重试", vb)
        self.assertIn("把重试改成循环", vb)
        self.assertIn("因为要支持流式", vb)
        self.assertNotIn("决策:", vb)            # 无脚手架标签
        self.assertNotIn(hit["sha"][:7], vb)       # 无 sha
        self.assertIn("evidence", c)               # 展示字段仍在
```

```python
# tests/test_grounded_chat.py —— 追加(沿用本文件既有 _cache/llm fixture 范式)
class TestAnswerHighlights(unittest.TestCase):
    def test_degraded_answer_has_highlights(self):
        # llm=None 降级 → answer = material(含某条 verbatim 原话)→ highlights 非空、cite_id 真实
        from vibetrace import chat
        cache = _mk_cache_with_one_commit()          # 复用本文件已有建仓+叙事 helper(见文件顶部)
        out = chat.answer(cache, None, _PROJ, "为什么这么写", now="2026-06-27T00:00:00")
        self.assertIn("highlights", out)
        if out["citations"]:                          # 有材料时降级答案=material 必含 verbatim
            ids = {c["id"] for c in out["citations"]}
            for seg in out["highlights"]:
                if seg["cite_id"] is not None:
                    self.assertIn(seg["cite_id"], ids)
```

> 注:若 `tests/test_grounded_chat.py` 无现成单 commit fixture helper,实现者用本文件已有的临时仓 + `put_narrative` 范式建一个最小 fixture(带 1 条含 evidence/decisions 的叙事),命名 `_mk_cache_with_one_commit`/`_PROJ`;断言只需 `"highlights" in out` + cite_id 属真实 citation,不依赖具体命中数。

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_retrieval_verbatim tests.test_grounded_chat -v` → FAIL(`verbatim` 不在 citation;`highlights` 不在 out)。

- [ ] **Step 3: 实现**

`vibetrace/retrieval.py` 在 `_citation` 之前加:

```python
def _verbatim(hit):
    """纯原话拼接(无 sha/标签/标题),专供逐字高亮匹配(区别于 render_hit 脚手架)。"""
    parts = list(hit.get("decisions") or [])
    if hit.get("why"):
        parts.append(hit["why"])
    for e in hit.get("evidence") or []:
        parts += list(e.get("prompts") or []) + list(e.get("excerpts") or [])
    return "\n".join(p for p in parts if p)
```

`_citation` 返回加 `"verbatim": _verbatim(hit)`:

```python
    return {"id": idx, "sha": hit["sha"][:12], "kind": hit["kind"],
            "evidence": search.render_hit(hit), "verbatim": _verbatim(hit),
            "sources": _sources(hit)}
```

`vibetrace/chat.py`:import 区加 `from . import highlight`;`answer()` 返回 dict 加一项:

```python
    return {"answer": answer_text, "citations": ev["citations"],
            "conv_id": conv_id, "degraded": degraded,
            "grounding": _grounding(ev["hits"], degraded),
            "highlights": highlight.segments(answer_text, ev["citations"])}
```

`answer_stream()` 的 `done` yield 加同项:

```python
    yield {"type": "done", "citations": ev["citations"],
           "conv_id": conv_id, "degraded": degraded,
           "grounding": _grounding(ev["hits"], degraded),
           "highlights": highlight.segments(answer_text, ev["citations"])}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_retrieval_verbatim tests.test_grounded_chat -v` → PASS。
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` → OK。`wc -l vibetrace/retrieval.py vibetrace/chat.py`(各 <300)。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/retrieval.py vibetrace/chat.py tests/test_retrieval_verbatim.py tests/test_grounded_chat.py
git commit -m "feat(chat): citation 加 verbatim 纯原话 + answer/stream 带 highlights"
```

---

### Task 3: `web_chat.html` done 切段重渲染 `<mark>` + legend + chip 锚点

**Files:** Modify `vibetrace/web_chat.html`、Test `tests/test_web_chat.py`(追加)

**Interfaces:** Consumes done 事件 `ev.highlights`(段列表)+ 累积答案 `acc`;复用已有 `esc()`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_web_chat.py —— 追加
class TestAnswerHighlight(unittest.TestCase):
    def setUp(self):
        from vibetrace import web
        self.html = (Path(web.__file__).parent / "web_chat.html").read_text(encoding="utf-8")

    def test_highlight_render_present(self):
        self.assertIn("function setBody", self.html)        # 单一 innerHTML sink
        self.assertIn('<mark class="vb"', self.html)
        self.assertIn("data-cite", self.html)
        self.assertIn("ev.highlights", self.html)
        self.assertIn("高亮=逐字源自来源", self.html)        # legend

    def test_safety_and_invariants(self):
        self.assertIn("dataset.cite", self.html)            # chip 锚点
        self.assertIn("CSS.escape", self.html)              # mark→chip 反查
        self.assertNotIn("${", self.html)                   # 禁模板字面量
        # 高亮段文本经 esc(只 <mark> 标签字面)
        self.assertIn("esc(s.text)", self.html)
        # 段拼接≠累积答案 → 回退 esc(acc)
        self.assertIn("setBody(esc(acc))", self.html)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_web_chat.TestAnswerHighlight -v` → FAIL。

- [ ] **Step 3: 实现**

(a) CSS(`<style>` 内):

```css
.vb{background:rgba(227,179,65,.25);border-radius:2px;padding:0 1px;cursor:pointer}
.hl-legend{font-size:11px;opacity:.6;margin-top:6px}
.cite.cite-hot{outline:2px solid #e3b341;outline-offset:2px}
```

(b) 提交处累积答案:`var body = add("vibetrace", "bot");` 之后加 `var acc = "";`;token 分支 `body.textContent += ev.text;` 同处加 `acc += ev.text;`;done 分支 `renderDone(body, ev);` 改 `renderDone(body, ev, acc);`。

(c) `renderDone` 签名改 `function renderDone(body, ev, acc){`,函数体**最前**(`if (ev.degraded)` 之前)插入:

```javascript
  function setBody(html){ body.innerHTML = html; }
  var H = ev.highlights || [];
  if (H.length){
    if (H.map(function(s){ return s.text; }).join("") !== acc){
      setBody(esc(acc));                                   // 不变式自检失败 → 回退,仍转义
    } else {
      setBody(H.map(function(s){
        return s.cite_id == null ? esc(s.text)
          : '<mark class="vb" data-cite="'+String(s.cite_id)+'">'+esc(s.text)+'</mark>';
      }).join(""));
      var lg = document.createElement("div"); lg.className = "hl-legend";
      lg.textContent = "高亮=逐字源自来源;其余为综合,点引用核验";
      body.parentNode.appendChild(lg);
    }
  }
```

(d) chip 渲染处(`cites.forEach` 内 `s.title = ...` 之后)加锚点:`s.dataset.cite = String(c.id);`

(e) `renderDone` **末尾**(`body.parentNode.appendChild(panel);` 之后)绑 `<mark>` → chip 联动(此时 chip 已渲染、dataset.cite 已设):

```javascript
  body.querySelectorAll("mark.vb").forEach(function(m){
    m.addEventListener("click", function(){
      var el = document.querySelector('[data-cite="' + CSS.escape(m.getAttribute("data-cite")) + '"]');
      if (el){ el.scrollIntoView({ block: "center" });
        el.classList.add("cite-hot");
        setTimeout(function(){ el.classList.remove("cite-hot"); }, 1200); }
    });
  });
```

- [ ] **Step 4: 跑测试 + 静态扫描确认通过**

Run: `python3 -m unittest tests.test_web_chat -v` → PASS。
Run: `python3 -m unittest discover -s tests 2>&1 | tail -3` → OK。
Run: `python3 -m scripts.check_static_no_external vibetrace/web_chat.html` → exit 0。
Run: `grep -cF '$' vibetrace/web_chat.html` → 仍 1(仅 `$tree_data`;新 JS 无 `$`)。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/web_chat.html tests/test_web_chat.py
git commit -m "feat(web): 答案内逐字命中 <mark> 高亮 + legend + chip 锚点联动"
```

---

## Self-Review(对 spec 逐条核对)
- **spec 覆盖**:后端切段 `segments`(防错位)=Task1;`verbatim` 纯原话(R6 红线)+ chat highlights = Task2;web 单 setBody+每段 esc+段拼接自检回退+legend+chip dataset.cite+mark→chip = Task3;ask 不动(spec 砍 ask)。
- **占位符扫描**:无 TBD;每步完整代码 + 确切命令。Task2 的 chat fixture 给了「无现成 helper 则建最小 fixture」明确指引。
- **类型一致**:`segments → [{text,cite_id}]` 跨 Task1→Task2(chat highlights)→Task3(`s.text`/`s.cite_id`)一致;`citation.verbatim` Task2 产、Task1 `segments` 消费(`cit["verbatim"]`)一致;`data-cite`/`dataset.cite` String 归一一致。
- **红线**:highlight.py 纯 stdlib difflib <300 零 LLM;只匹配 verbatim 非 render_hit;web 单 innerHTML sink + 每段 esc + 回退 esc + `<script>` 对抗测试;`$` 计数==1;check_static_no_external。
