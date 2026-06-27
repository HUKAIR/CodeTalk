# 答案内逐字命中片段高亮 — 设计(spec)

日期:2026-06-27 · 来源:ROADMAP line 21 仍开放项① · 分支 `feat/answer-verbatim-highlight`(off main)。前置:line 21 的 dev-only 逐字引用保真自检已落地(PR #65 `citation_audit.py`)。

## 目标(一句话)
在 ask / web 接地对话的 LLM 答案里,**确定性(零-LLM)标出哪些片段逐字源自被引材料**,并链回来源——让用户一眼看到「这几个字逐字来自来源 X」,其余是综合释义(见引用面板核验)。

## 已定边界(R6 + 前几轮对抗,勿再翻)
- 字符串恒等**只在逐字子串处成立**:只高亮逐字重叠片段;**不**逐句语义归因、**不**打 grounded/inferred/unsupported 标签、**不**设 τ 阈值、**不**宣称「答案零幻觉 / 满足 Trust-Score」。
- **诚实-稀疏现实**:`CHAT_SYSTEM_PROMPT` 让答案是综合释义,逐字重叠通常**稀疏** → 高亮可能很少甚至没有。这本身诚实(答案是综合、引用面板才是逐字核心);web 用一行 legend 设预期。
- **范围**:web 视觉高亮 + `ask --json` 结构化 spans;**ask 文本模式不动**(终端高亮低价值 + 多余面)。

## 架构与组件

### 新模块 `vibetrace/highlight.py`(~45 行,纯 stdlib `difflib`)
- `MIN_SPAN = 6`(常量;逐字块最小字符数,滤「的/是」类短噪)。
- `verbatim_spans(answer, citations) -> list[dict]`(**纯函数,可单测**):
  - 对每条 citation(`{id, evidence, ...}`):`difflib.SequenceMatcher(None, answer, cit["evidence"]).get_matching_blocks()` → 取 `size >= MIN_SPAN` 的块,记 `{start: a, end: a+size, cite_id: cit["id"]}`(`a` 是块在 **answer** 中的起点)。
  - **跨 citation 去重叠**:汇总所有块 → 按 `(start, -length)` 排序 → 贪心接受不与已接受块重叠者(先到、长者优先)→ 返回按 `start` 升序、**互不重叠**的 spans(每个带 `cite_id`)。
  - `citations` 空 / answer 空 / 无 ≥MIN_SPAN 块 → `[]`(降级答案、纯释义答案天然空,合法)。
  - 纯字符串运算,零 LLM、零 IO、不崩。

### `vibetrace/chat.py`(import `highlight`,+2 处)
- `answer()` 返回字典加 `"highlights": highlight.verbatim_spans(answer_text, ev["citations"])`(line 65-67 处,`answer_text`/`ev["citations"]` 已在作用域)。
- `answer_stream()` 的 `done` 事件(line 97-99)加同字段(`answer_text` 在 line 93 已拼齐)。
- 降级答案(`answer_text = ev["material"]`)会与 evidence 大量逐字重叠 → 高亮密;LLM 释义答案 → 稀疏。两者都正确。

### `vibetrace/web_chat.html`(done 时重渲染答案 + legend)
- 流式期间 `.body` 仍逐 token 追加纯文本(不变);**需累积完整答案文本**到一个变量(随 token 追加),供 done 重渲染。
- `renderDone` 里,若 `ev.highlights` 非空:用 `ev.highlights`(已排序互不重叠的 `{start,end,cite_id}`)对**完整答案文本**切片重渲染 `.body`:
  - 按 span 边界把答案切成「普通段 / 高亮段」交替;**每段都过 `esc()`**;高亮段包 `<mark class="vb" data-cite="ID">esc(片段)</mark>`(只有 `<mark>` 标签是字面,文本一律 esc——XSS 红线)。offset 是对**原始答案**的字符下标,切片用原始文本、再逐段 esc。
  - 点 `<mark>` → 高亮/滚动到对应 citation chip(用 `data-cite` 关联已渲染的 chip)。
  - 一行 legend:`高亮=逐字源自来源;其余为综合,点引用核验`。
  - `ev.highlights` 空 → 不重渲染、不显示 legend(纯释义答案保持原样,不强加空 UI)。
- 零-build vanilla-JS;**禁 `${}`**;复用已有 `esc()`。

### `vibetrace/ask.py`(`--json` 加字段)
- `--json` payload(`_json_text` 的 `llm` 模式)加 `"highlights"`(从 `chat.answer` 返回透传;agent 可读)。**文本模式不动**。

## 数据流
`retrieval.assemble` → citations(各带 `evidence`)+ LLM `answer_text` → `highlight.verbatim_spans(answer_text, citations)`(零-LLM difflib)→ `chat.answer`/`answer_stream.done` 的 `highlights` → web 在 done 切片重渲染 `<mark>`+legend / `ask --json` 透传。全程零 LLM、数据不出本机、注入前 redact(highlights 只是 offset+cite_id 整数/短串,evidence 文本本就经出口脱敏)。

## 错误处理 / 红线
- `verbatim_spans` 纯字符串、不崩;answer/citations 任意为空 → `[]`。
- web 切片重渲染:offset 越界/错乱时**回退为纯 `esc(answer)`**(不崩、不漏未转义文本)。
- 仅 stdlib(`difflib`);`highlight.py` <300;零 LLM(`grep LLMClient` = 0)。
- web 前端零外链(改后 `python3 -m scripts.check_static_no_external vibetrace/web_chat.html`);CSP 不变;每段 `esc()`(XSS)。

## 测试(TDD)
- `highlight.verbatim_spans`(纯函数,合成):① answer 含某 citation 的 evidence 逐字片段 → 命中 span 起止 + `cite_id` 正确;② <MIN_SPAN 短重叠被滤;③ 两 citation 重叠命中 → 输出互不重叠、按 start 升序;④ 纯释义 answer(无 ≥MIN_SPAN 重叠)→ `[]`;⑤ 空 citations / 空 answer → `[]`。
- `chat.answer` 含 highlights:`llm=None` 降级(answer=material 含 evidence)→ highlights 非空且 cite_id 指向真实 citation;有/无命中两态。
- `web_chat.html`(文本标记,读 HTML 不导 fastapi):`<mark class="vb"`、`data-cite`、legend 文案、累积变量、空 highlights 不渲染分支、`esc(` 用于片段、无 `${`。
- 全量 `python3 -m unittest discover -s tests` 绿;`highlight.py`/`chat.py` <300;`check_static_no_external` exit 0。

## YAGNI / 非目标
- 不做语义归因 / 蕴含 / τ / grounded 标签(R6 红线)。
- ask 文本模式不加视觉高亮(只 --json 结构化)。
- 不抽象 web 的 difflib 逻辑到前端(difflib 在后端,前端只渲染 spans)。
- 不为「提高高亮密度」改 CHAT_SYSTEM_PROMPT(答案该是综合;稀疏是诚实结果)。

## 开放问题
无(机制、落点、范围、诚实边界 brainstorm 已定)。
