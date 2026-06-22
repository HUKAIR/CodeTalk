# 会话原话接地锚点 + align 语义修正 — 设计 spec

**状态**:设计已由用户认可(= 对抗效能审核 task wdccub7rh 的 to_be_thorough #1/#2/#3 + 用户「按建议完成全部」)。
**日期**:2026-06-21
**分支**:`feat/session-evidence`(stacked on `feat/cursor-source`/#29;#29 合并后 rebase 到 main)。

## 背景
对抗效能审核(`docs/discovery/gap-analysis-问卷1.md` 链路)判定 Cursor 源「仅解决前置」:捕获做对了,但用户1 头号痛点「不被 LLM 反推式编造、拿到可核验的当初原话」没解,且有两个结构性问题会**帮倒忙**:
1. **原话被 LLM 重述后丢弃**:enrich 把会话原话喂 LLM,只缓存 LLM 合成的 `narrative.why`;ask/blame 读时只输出 `narrative.why`(LLM 转述),没有任何原话出口。用户拿回的正是他只信 6 分、最警惕的「事后重解释」。
2. **软关联误挂被不可变 SHA 漂白**:Cursor 的 `files_written` 取自 `relevantFiles/attachedCodeChunks`(=AI 看过/附带的**上下文**文件,非真实编辑),而 `align` 用 `files_written` 求交定 high 置信 → 把热点文件附进 Cursor 问无关问题、落 ±30min 窗就盖 `high` → 错的 why 烙进 SHA 缓存 → ask 用真实 SHA 言之凿凿、无置信度警示 → 更难识破。

本特性修这两条 + 加置信度警示,把「仅前置」推向「实质解决」。对 **Claude + Cursor 两源都生效**(#1 是通用问题)。

## 目标 / 非目标
**目标**:ask/blame 回答「当初为什么」时,在 LLM 综合的 why 旁展示**对齐到的真实会话原话**(session/source/时间戳)供用户自行核验;修正 Cursor 编辑 vs 上下文文件语义,消除误挂漂白;对软关联 why 打置信度警示。
**非目标(留待后续)**:摄取 PR/测试/需求文档源(O5);端到端 dogfood 拦截记录;对齐召回率离线评测;捕获源占比问卷题。这些是验证/扩展,不在本代码特性内(spec 末「待验证」记录)。

## A. Cursor 编辑/上下文文件分离(修漂白根因)
改 `cursor_sessions.py`:
- `files_written` ← composerData 的 `addedFiles` + `removedFiles`(真实编辑;已实测 composerData 含这些键);为空时退取各 bubble 的 `assistantSuggestedDiffs` 涉及文件。
- `files_read` ← `relevantFiles`/`recentlyViewedFiles`/`attachedCodeChunks`(上下文,**不计入** align high 置信)。
- (现状是全部并入 `files_written`;改为分离。`_abs_files` 拆成 `_edited_files(head)` 与 `_context_files(bubble)` 两个取数,或加参数。)
- **align.py 无需改**:它只用 `files_written` 求交(align.py:34),字段语义修对即修了漂白;`files_read` 本就不参与(与 Claude 一致)。

## B. 原话接地锚点(evidence,修「LLM 转述代替原话」)
- `enrich.py`:富集每个 commit 时,把**最高置信 match** 的原话结构化存进 `narrative["evidence"]`:
  ```
  narrative["evidence"] = [
    {"session_id": str, "source": "claude"|"cursor", "ts": ISO_str,
     "confidence": "high"|"low", "prompts": [str][:3], "excerpts": [str][:2]}
  ]  # 取 commit["matches"] 里置信最高的前 1-2 个;match.session 已脱敏
  ```
  - source 判定:Claude summary 有 `is_subagent` 但无 source 标记 → 用 `session_id` 是否为 Cursor composer 区分较脆;**改为**在合并时给会话打 `summary["source"]`(cursor_sessions 置 "cursor",sessions 置 "claude"),enrich/evidence 透传。
  - `put_narrative` 已统一脱敏 → evidence 落盘安全。无 schema 变更(narrative 是 JSON,加键即可;旧缓存无该键,读时 `.get("evidence", [])` 兼容)。
- `ask.py` / `blame.py` 读时:在 why 之后追加一段「原话佐证(可自行核验)」,列每条 evidence 的 `source·session 短id·ts` + prompts/excerpts 片段。
  - ask:在 LLM 综合答案后附原话块,让 LLM 的 why 旁永远有用户自己的原话可对照(对抗反推式编造)。
  - blame:零-LLM 路径直接列 evidence 原话(确定性),不是只读被 LLM 重写的 `narrative.why`。

## C. 置信度警示
- ask/blame 输出:当某条 why 的支撑 evidence 仅为 `low`(软关联,只命中时间或仅上下文文件)时,显式标注「(基于软关联会话,置信较低,请核对原话)」,杜绝错挂被 SHA 漂白成确定答案。

## 数据流
digest → align(commits×sessions,sessions 带 source)→ enrich(写 narrative.why + narrative.evidence)→ cache(SHA,已脱敏)。
ask/blame 读 → narrative.why(LLM)+ narrative.evidence(原话锚点)+ 置信度警示 一并呈现。

## 影响文件
- 改:`cursor_sessions.py`(编辑/上下文分离 + summary["source"]="cursor")、`sessions.py`(summary["source"]="claude")、`enrich.py`(写 evidence)、`ask.py`/`blame.py`(展示 evidence + 警示)。
- 测:`tests/test_*`(分离后 align high 不再被上下文文件触发;evidence 写入与展示;low 警示)。

## 红线合规
仅 stdlib + 现有模块;各模块 <300(cursor_sessions 现 257,分离逻辑需控量,必要时抽小函数);落盘前 redact(evidence 来自已脱敏 summary + put_narrative 二次脱敏);容错(evidence 缺失 `.get` 兼容、不崩);本地优先不变。

## 待验证(本特性外,记录)
- 端到端:Cursor 会话→enrich→ask/blame 读回并**展示原话** 的端到端测试 + floor→round dogfood 拦截。
- 对齐召回率离线数;接地原话 vs LLM 重解释 真实性对比;PR/测试/文档源(O5);捕获源占比 + ≥3 人复现。
- 本地优先出网边界文案(README)。

## 开放问题
- composerData `addedFiles/removedFiles` 在所有 Cursor 版本是否稳定提供(非官方 schema);为空时退 bubble suggestedDiffs;再空则该会话无 high 置信文件(只剩时间窗 low)——可接受降级。
- evidence 体量:每 commit ≤2 会话 × (3 prompts+2 excerpts),控 token/隐私面;原话已截断脱敏。
