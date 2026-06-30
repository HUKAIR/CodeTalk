# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

**编码纪律选用:** 本项目「重活」(写 / 改 / 调试 / 审代码)优先调起 `/karpathy-enhanced` —— 它是下面 4 条的超集(另加:读后写、验证、调试、依赖、沟通、命名反模式目录);下面 4 条是其精炼核心,轻量任务够用。

**按分量分档(别一刀切上全套):**
- **琐碎**(改常量 / 重命名 / 一行 / 文案):直接改 + 跑相关测试;跳 TDD 仪式、跳对抗 subagent 审、能直接合就别走 PR 全套。
- **中等**(一个函数 / 一个小功能 / 一个 bug):读相关文件 + TDD 红→绿 + 跑全量。**性价比甜区,默认档。**
- **重活**(架构 / 跨多文件 / 有回滚成本 / 动 M0 红线):`/karpathy-enhanced` 超集 + 对抗审 + superpowers 流水线(brainstorm→spec→对抗审 spec→plan→subagent-TDD→PR)。
- **刚性三条**(§4 surgical、§5 验证、§7 调试):成本极低、专拦最贵事故,**任何分量都守**。
- **对抗 subagent 审触发阈值**:中高风险 diff 或 ultracode 开启时才挂;琐碎 / 已 TDD + 全量绿的小改**不挂**(过度加工)。

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
- 决策面包屑:关键取舍在 commit message 正文留 `Vibe-Decision:`、待验证留 `Vibe-Watch:`
  (**格式与示例的唯一权威见 `codetalk/agent_seed.md`**,可 `codetalk install-agent-seed`
  植入任意项目)。digest 把 Decision 并进该 commit 决策、Watch 并进 risks(到期封成可验证
  胶囊),`codetalk ask <文件>[:行] "问题"` / `graph` 据此接地回答"这段代码当初为什么这么写"。
- **依赖分面(M0 修订 2026-06-24,web app 落地)**:上面「禁 Web 框架 / 仅 stdlib」适用
  **CLI / MCP 核心面**(`pip install -e .` 仍 `dependencies=[]`,anthropic 为可选 extra)。
  **新 web-app 面**(`codetalk web`,`pip install -e ".[web]"` 可选 extra)允许 FastAPI /
  uvicorn 等框架;但 ① web extra 不得被 CLI/MCP import(惰性 import,核心仍纯 stdlib);
  ② 仍禁 LangGraph / 向量库 / 重前端构建链——优先零-build 单文件 vanilla-JS(`web_chat.html`),
  React/Vite 仅在 chat UX 真需要(流式/消息管理)时再上。**隐私红线不变**:web 默认仅绑
  127.0.0.1、绝不 phone home(除 LLM 唯一例外)、出网前 + 落库前脱敏、前端零 LLM 直连
  (CSP `connect-src 'self'`;静态产物经 `scripts/check_static_no_external.py` 扫无外链)。

## Agent 记忆卫生(我维护本仓跨会话记忆的约定)
跨会话记忆在 `~/.claude/projects/-Users-gavin-Github-CodeTalk/memory/`(`MEMORY.md` 索引 + 每事一文件);retro 设施已运转(`~/.claude/retro/`)。借另一本地仓的成熟做法,克制采纳:
- **收尾按判据蒸馏,不乱记**:retro 提示 / 会话 / PR 收尾时,只有同时满足「跨会话还会用 + 不重复已有 + 不是产品功能决策(那进 spec/ROADMAP,不进记忆)」才写一条;琐碎会话跳过。类型用 `user/feedback/project/workflow/reference`,别照搬别处枚举。
- **每条带 `Why` + `How to apply`**:结论之外写清为什么 + 下次怎么用,尤其 `project` 长文——没 How 就只是「读过」不是「会用」,下次仍会重推同一裁决。
- **真溯源 + supersedes**:`originSessionId` 写真实当前 session_id,别复制同一默认值(伪溯源比没有更糟);事实被推翻时就地改 `MEMORY.md` 索引行 + 在旧条目正文头标一行「已被 X 取代(日期)」,自然语言标注,不引版本系统。
- **别做**:不建 consolidation 脚本 / 定期整固(条目少、人眼可去重;逼近约 25–30 篇且出现重复簇再回来重审)· 不做向量 / 语义去重 · 不建月度日报台账(待验证赌注写在对应 memory 正文,别两处维护成漂移源)。
