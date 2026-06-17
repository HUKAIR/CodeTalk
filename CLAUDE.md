# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Project-Specific Guidelines
- Python 3.11+;M0 仅允许标准库 + anthropic SDK(GitPython 可选)。
  禁止引入 LangGraph、向量数据库、Web 框架——出现即违反 Simplicity First
- 所有 LLM 调用走统一封装 llm.py:prompt 模板、重试、token 计数日志、
  Anthropic prompt caching(系统提示+项目上下文作缓存前缀)
- 所有解析外部数据(JSONL、git)的代码必须容错:失败记警告并降级,绝不崩溃
- 单模块 <300 行;将超出时先停下向我说明
- 缓存约定:commit 叙事以 SHA 为键(immutable,永不重算);
  会话富集以 session_id + last_msg_ts 为键,增量更新
- 隐私红线:数据不出本机(LLM API 调用除外);写缓存前对常见 secret
  模式(API key/token)脱敏
- 决策面包屑:做关键技术取舍时,在 commit message 正文留 `Vibe-Decision: <一句话决策,
  可含被否决备选>`;没把握、需日后验证的留 `Vibe-Watch: <一句话>`。digest 会把 Decision
  并进该 commit 决策、Watch 并进 risks(到期封成可验证胶囊),`vibetrace ask <文件>[:行]
  "问题"` 据此接地回答"这段代码当初为什么这么写"。行首精确匹配、区分大小写
