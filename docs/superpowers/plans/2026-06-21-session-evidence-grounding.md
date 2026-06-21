# 会话原话接地锚点 + align 语义修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development。每任务 TDD,checkbox 跟踪。完整设计见 `docs/superpowers/specs/2026-06-21-session-evidence-grounding-design.md`(实现前先读它)。

**Goal:** ask/blame 在 LLM 综合的 why 旁展示对齐到的**真实会话原话**(可核验)+ 修正 Cursor 编辑/上下文文件语义消除误挂漂白 + 软关联打置信度警示。对 Claude+Cursor 两源生效。

**Architecture:** session summary 加 `source` 标签;Cursor 分离 `files_written`(编辑)/`files_read`(上下文);enrich 把最高置信 match 原话写进 `narrative["evidence"]`;ask/blame 读时展示 evidence + 置信度警示。

**Tech Stack:** 仅 stdlib + 现有 vibetrace 模块;stdlib unittest。基线 `feat/session-evidence`(stacked on #29)。

## Global Constraints
- 仅标准库 + 现有模块;各 Python 模块 **<300 行**;落盘前 `redact_secrets`;容错降级绝不崩;本地优先不变。
- evidence 来自**已脱敏**的 session summary;`narrative["evidence"]` 经 `put_narrative` 二次脱敏;旧缓存无该键用 `.get("evidence", [])` 兼容。
- 每步 `python3 -m unittest discover -s tests` 全绿。

---

### Task 1: session summary 加 `source` 标签

**Files:** Modify `vibetrace/sessions.py`(_blank/_parse 起点 summary 处)、`vibetrace/cursor_sessions.py`(`_blank_summary`);Test: `tests/test_source_tag.py`

**Interfaces:** Produces — Claude summary `["source"]=="claude"`,Cursor summary `["source"]=="cursor"`。

- [ ] Step1 失败测试:`sessions.scan_sessions` 产物每条 `summary["source"]=="claude"`(真实 git+~/.claude fixture 或直接断言 _parse 起点 dict 含 source);`cursor_sessions._blank_summary("x")["source"]=="cursor"`。
- [ ] Step2 跑测试看失败(KeyError source)。
- [ ] Step3 实现:`sessions.py` 构造 summary 的字典加 `"source": "claude"`;`cursor_sessions._blank_summary` 加 `"source": "cursor"`。两处 `_freeze/_thaw` 用 `**summary` 透传,无需改。
- [ ] Step4 跑测试通过 + 全量绿。
- [ ] Step5 commit `feat(sessions): summary 加 source 标签(claude/cursor)`。

---

### Task 2: Cursor 编辑/上下文文件分离(修 align 漂白根因)

**Files:** Modify `vibetrace/cursor_sessions.py`;Test: `tests/test_cursor_sessions.py`(扩展)

**Interfaces:** Consumes — composerData `addedFiles`/`removedFiles`,bubble `assistantSuggestedDiffs`/`relevantFiles`/`attachedCodeChunks`。Produces — summary `files_written`=真实编辑、`files_read`=上下文。

行为(详见 spec A):
- `files_written` ← composerData `addedFiles`+`removedFiles`(绝对化,复用现有路径还原);为空则退取各 bubble `assistantSuggestedDiffs` 涉及文件。
- `files_read` ← `relevantFiles`/`recentlyViewedFiles`/`attachedCodeChunks`(原 `_abs_files` 的来源)。
- 抽函数:`_edited_files(head, bubbles, root)` 与 `_context_files(bubble, root)`(由现 `_abs_files` 拆出),控模块 <300。

- [ ] Step1 失败测试(用 make_global 扩展,composerData 传 `addedFiles`):
  - 编辑文件进 `files_written`、上下文文件进 `files_read`;
  - **关键回归**:一个 composer 只把某文件作为 `relevantFiles`(上下文)未编辑 → 经 `align.align` 与触碰该文件的 commit **不得**得 `confidence=="high"`(应 low 或不匹配)。
- [ ] Step2 跑测试看失败(当前全进 files_written → high 漂白)。
- [ ] Step3 实现分离。
- [ ] Step4 跑测试通过 + 全量绿;`wc -l vibetrace/cursor_sessions.py` <300。
- [ ] Step5 commit `fix(cursor): 编辑/上下文文件分离,消除 align 误挂漂白`。

---

### Task 3: enrich 写 `narrative["evidence"]`

**Files:** Modify `vibetrace/enrich.py`;Test: `tests/test_enrich_evidence.py`

**Interfaces:** Consumes — `commit["matches"]`(align 产物:`[{session, overlap, confidence}]`,session 含 source/session_id/start/end/prompts/excerpts)。Produces — `narrative["evidence"]=[{session_id, source, ts, confidence, prompts[:3], excerpts[:2]}]`(取置信最高前 ≤2 个 match)。

- [ ] Step1 失败测试:给一个带 matches(high+low)的 commit,`enrich` 后其 narrative 含 `evidence`,第一条是 high、带 session_id/source/ts/prompts/excerpts;无 matches 时 `evidence==[]`。
- [ ] Step2 跑测试看失败(无 evidence 键)。
- [ ] Step3 实现:在 enrich 写 narrative 处,从 `commit.get("matches")` 排序(high 优先、overlap 多优先,已有排序)取前 2,构造 evidence(prompts/excerpts 截断、ts 用 session end isoformat、source 用 session.get("source","?"))并入 normalized,再走 put_narrative(脱敏)。LLM 失败降级路径也写空 evidence。
- [ ] Step4 跑测试通过 + 全量绿。
- [ ] Step5 commit `feat(enrich): narrative 写原话接地锚点 evidence`。

---

### Task 4: ask/blame 展示 evidence + 置信度警示

**Files:** Modify `vibetrace/ask.py`、`vibetrace/blame.py`;Test: `tests/test_ask_evidence.py`、扩展 `tests/test_blame.py`

**Interfaces:** Consumes — `narrative.get("evidence", [])`。Produces — ask/blame 文本输出含「原话佐证(可自行核验)」块(source·session 短id·ts + 原话片段);仅 low 置信支撑时加「(基于软关联会话,置信较低,请核对原话)」。

- [ ] Step1 失败测试:
  - ask:narrative 带 high evidence → 输出含「原话佐证」+ 原话片段 + session 短id;仅 low evidence → 含置信度警示语。
  - blame:某段落对应 narrative 有 evidence → 确定性列出原话片段(不经 LLM)。
- [ ] Step2 跑测试看失败。
- [ ] Step3 实现:ask 在综合答案后追加 evidence 块(从命中 SHA 的 narrative 取);blame 在每段决策史后附 evidence 原话;`evidence` 全 low 或某条 low → 警示。文案中文、`redact` 已在上游。无 evidence 兼容(不输出该块)。
- [ ] Step4 跑测试通过 + 全量绿。
- [ ] Step5 commit `feat(ask,blame): 展示原话接地锚点 + 软关联置信度警示`。

---

## Self-Review
- spec 覆盖:A(Task2)/B(Task1+3+4)/C(Task4);两源生效(Task1 source 标签贯穿 evidence/展示)。
- 无占位符;接口一致(`source`/`evidence` 字段集贯穿 Task1→3→4)。
- 红线:模块 <300(Task2 注意 cursor_sessions 抽函数控量)、脱敏(evidence 上游已脱敏 + put_narrative)、容错(`.get` 兼容)。
- 待验证(端到端/dogfood/召回/PR源)在 spec 末记录,本计划不含(属验证非编码)。

## Execution Handoff
subagent-driven:逐任务 implementer(TDD)→ reviewer(spec+质量)→ 修;末尾整支终审 → PR(不自动合)。
