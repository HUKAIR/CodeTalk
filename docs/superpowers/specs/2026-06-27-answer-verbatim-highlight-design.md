# 答案内逐字命中片段高亮 — 设计(spec)

日期:2026-06-27 · 来源:ROADMAP line 21 仍开放项① · 分支 `feat/answer-verbatim-highlight`(off main)。
**修订(对抗审 spec 后,2026-06-27)**:18 条经真实代码核实的发现收口——**改后端切段(消灭 Python 码位 vs JS UTF-16 错位 blocker)**、**匹配纯原话而非 render_hit 脚手架(R6 诚实红线)**、**砍 ask(其管线不经 chat.answer)**、单一 setBody+esc、chip data-cite、autojunk=False 等。

## 目标(一句话)
在 web 接地对话的 LLM 答案里,**确定性(零-LLM)标出哪些片段逐字源自被引材料的真实原话**,链回来源——让用户看到「这几个字逐字来自来源 X」,其余是综合释义(见引用面板核验)。

## 已定边界(R6 + 前几轮对抗,勿再翻)
- 只高亮逐字重叠片段;**不**逐句语义归因、**不**打 grounded/inferred/unsupported 标签、**不**设 τ、**不**宣称「答案零幻觉 / 满足 Trust-Score」。
- **匹配纯原话、不匹配渲染脚手架**:`render_hit`/grounding_render 含确定性脚手架(`[sha7]`、`意图:`、`决策:`、标题「原话佐证…」「从测试场景反推设计」「相关 PR 讨论」等);若拿它做 difflib,LLM 答案复用这些模板词会被误标「逐字源自来源」→ 违 R6。必须只对**纯原话字段**匹配。
- **高亮是逐字命中的下界**:`get_matching_blocks` 只锚 LCS 式非重叠最长分解,答案重排引用时会漏标确属逐字的次段;**「未高亮」不等于「非逐字」**,逐字核验以引用面板为准。
- **诚实-稀疏现实**:`CHAT_SYSTEM_PROMPT` 让答案是综合释义,逐字重叠通常**稀疏** → 高亮常很少甚至没有(诚实:答案是综合、引用面板才是逐字核心);web 用一行 legend 设预期,无命中则不重渲染、不显示 legend。
- **范围:仅 web 视觉高亮**。**砍 ask**:ask.py 管线独立(`answer_question→_retrieve→llm.narrate(ASK_SCHEMA)→_json_text`),**不经 `chat.answer`**,且其 evidence 是 session 锚点 dict(非 `{id,evidence}` citation),无法透传 highlights;ask 侧高亮属另起任务,本期非目标(ROADMAP line 22 的「ask/web」据此修订为先 web)。

## 架构与组件

### 新模块 `vibetrace/highlight.py`(~55 行,纯 stdlib `difflib`)
- `MIN_SPAN = 6`(常量,逐字块最小字符数)。
- `segments(answer, citations) -> list[dict]`(**纯函数,可单测**)。**返回已切好的有序段**(非裸 offset——彻底消灭后端 Python 码位下标与前端 JS UTF-16 下标在 emoji/astral 字符后的错位 blocker;前端只 esc 拼接、不切片):
  - `answer = answer or ""`(None 兜底:openai-compat 可能 content=null → llm.chat 返 None)。
  - 对每条 citation(`{id, verbatim, ...}`,见下 retrieval 改动):`difflib.SequenceMatcher(None, answer, cit["verbatim"], autojunk=False).get_matching_blocks()` → 取 `size >= MIN_SPAN` 的块 → answer 坐标区间 `(a, a+size, cit["id"])`。`autojunk=False`:对「找所有逐字重叠」语义 autojunk 纯有害(长 evidence 会静默丢块)。
  - **跨 citation 去重叠**(确定性):汇总区间 → 按 `(start, -length, cite_id)` 排序 → 贪心接受不与已接受区间重叠者 → 得按 start 升序、互不重叠的高亮区间(重叠区逐字归属只记一个来源,tie-break 确定;不代表其余来源未逐字含该片段)。
  - **无高亮区间 → 返回 `[]`**(纯释义/降级前缀不撞/空 → 空,web 不重渲染)。
  - 有则**按区间把 answer(Python str 码位切片)切成交替段**:`[{"text": str, "cite_id": int|None}, ...]`,普通段 `cite_id=None`、高亮段带 id;**段文本拼接 === answer**(前端据此自检)。

### `vibetrace/retrieval.py`(`_citation` 加 `verbatim` 字段)
- `_citation` 增 `"verbatim"`:**纯原话拼接**(无 sha/标签/标题)——取 hit 的纯文本字段:`decisions` 各条 + `evidence[].prompts`/`excerpts` + `why`(有则),`\n` 连。面板展示仍用现有 `evidence`(=`render_hit`,保 C-3 同源);`verbatim` 专供高亮匹配。`segments` 匹配 `cit["verbatim"]`,不碰 `render_hit`。

### `vibetrace/chat.py`(import `highlight`,+2 处)
- `answer()` 返回加 `"highlights": highlight.segments(answer_text, ev["citations"])`(line 65-67;`answer_text`/`ev["citations"]` 在作用域)。
- `answer_stream()` `done` 事件(line 97-99)加同字段(`answer_text` 在 line 93 拼齐)。
- 治本兜底(可选):`answer_text = llm.chat(messages) or ""`(line 60)防 None。

### `vibetrace/web_chat.html`(done 切段重渲染 + legend + chip 锚点)
三处改动:
1. **累积完整答案**:流式期 `.body` 仍逐 token 追加(不变),同时把 token 累积进一个变量 `acc`(供 done 切段;**不**用 `.body.textContent`,后者可能被改)。
2. **单一 `setBody(html)`**:全文件唯一 `.body.innerHTML =` 收口在此函数;所有写 body 分支(高亮 / 空 highlights / 回退)都走它。
   - done 时若 `ev.highlights` 非空:`var h = ev.highlights; if (h.map(s=>s.text).join("") !== acc) setBody(esc(acc));`(**不变式自检**:段拼接须 === 累积答案,否则回退)`else setBody(h.map(s => s.cite_id==null ? esc(s.text) : '<mark class="vb" data-cite="'+String(s.cite_id)+'">'+esc(s.text)+'</mark>').join(""))`;并显示 legend「高亮=逐字源自来源;其余为综合,点引用核验」。
   - `ev.highlights` 空 → 不调 setBody(保留流式纯文本)、不显示 legend。
   - **每段文本一律 `esc()`**,只 `<mark class="vb" data-cite="...">` 标签字面(XSS 红线);回退分支 `setBody(esc(acc))`(转义且与高亮分支同走 innerHTML)。
3. **chip 锚点**:chip 渲染时 `s.dataset.cite = String(c.id)`(DOM property 写入,非 HTML 串插值,无需 esc);点 `<mark>` → `document.querySelector('[data-cite="'+CSS.escape(id)+'"]')` 命中 chip → `scrollIntoView({block:"center"})` + 短暂高亮 class。
- 零-build vanilla-JS;**禁 `${}`**;复用已有 `esc()`。

## 数据流
`retrieval.assemble` → citations(各带 `evidence` 展示 + `verbatim` 纯原话)+ LLM `answer_text` → `highlight.segments(answer_text, citations)`(零-LLM difflib,Python 切段)→ `chat.answer`/`answer_stream.done` 的 `highlights`(段列表 `[{text,cite_id}]`)→ web done 自检后切段重渲染 `<mark>`+legend。全程零 LLM、数据不出本机;**highlights 段含文本但该文本是 answer 子串(已是出口内容)**,不引入新外带文本;evidence/verbatim 经 web.py 出口 `redact_data` 脱敏。

## 错误处理 / 红线
- `segments`:`answer or ""`、citations 空/无 ≥MIN_SPAN 块 → `[]`;纯字符串、不崩。
- web:段拼接 ≠ 累积答案(理论不该)→ 回退 `setBody(esc(acc))`,不崩、不漏未转义、DOM 一致。
- XSS:不可信 LLM 答案首次进 innerHTML —— 每段 `esc()`、单一 setBody、回退也 esc;对抗测试钉死。
- 仅 stdlib(`difflib`);`highlight.py` <300;零 LLM(`grep LLMClient` = 0)。前端零外链(`check_static_no_external`);CSP 不变。

## 测试(TDD)
- `highlight.segments`(纯函数,合成):① answer 含某 citation `verbatim` 的逐字片段 → 段列表拼接===answer、高亮段 cite_id 正确;② **脚手架反例红线**:answer 复用「从测试场景反推设计」/「相关 PR 讨论」/某 7 位 sha 等 render_hit 脚手架词 → 因只匹配 `verbatim` 故 `[]`;③ `<MIN_SPAN` 短重叠滤;④ 两 citation 重叠命中 → 互不重叠、确定 tie-break;⑤ 纯释义(无 ≥MIN_SPAN 重叠)/ 空 citations / `answer=None`/`""` → `[]`;⑥ autojunk:长(>200字)重复 evidence 仍命中(autojunk=False 回归)。
- `retrieval._citation`:产 `verbatim`(纯原话、无 sha/标签/标题)+ 保留 `evidence`。
- `chat.answer`:`llm=None` 降级(answer=material 前缀含某条 verbatim)→ highlights 非空、cite_id 指真实 citation;释义态空。
- `web_chat.html`(读 HTML 文本,不导 fastapi):`<mark class="vb"`、`data-cite`、`function setBody`(单一 innerHTML)、legend 文案、累积 `acc`、空 highlights 不重渲染分支、`esc(` 用于段、`String(`/`CSS.escape` 归一、**对抗:含 `<script>` 的答案经高亮与回退两路 setBody 后断言不含未转义 `<script>`**、段拼接≠答案→回退分支、无 `${`。
- 全量 `python3 -m unittest discover -s tests` 绿;`highlight.py` <300;`check_static_no_external` exit 0。

## YAGNI / 非目标 / 已考虑替代
- 不做语义归因/τ/grounded 标签(R6)。**ask 侧高亮非目标**(管线独立 + evidence 形态异,另起任务)。
- **更简替代(已考虑,本期不采)**:只在 chip 上标「本条原话在答案逐字命中 N 处(最长 K 字)」、不切段重渲染 .body——更省、避 innerHTML/XSS 面,但**不满足用户「答案内高亮」明确诉求**;鉴于(A)切段方案已干净解决错位 blocker,本期上完整 web 视觉高亮;若实测过稀视觉无感,可逆降级为 chip 计数。
- highlight 落 `highlight.py`(非并入 retrieval):`answer_text` 是 LLM 产物只在 chat 作用域产生,retrieval 拿不到。
- MIN_SPAN=6:中文「的/是」短噪靠 6 字滤;**英文 6 字符 ≈ 1 词**(`return`/`commit`/`should`)可能偶撞模板公共词→已知取舍,加测试钉行为;纯 ASCII 提阈值/词边界对齐留 Later 据真实英文项目观感再定。

## 开放问题
无(后端切段、纯原话匹配、web-only、单 setBody、chip 锚点、诚实边界均已定)。
