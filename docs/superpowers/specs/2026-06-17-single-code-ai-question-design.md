# 单代码 AI 提问(`ask`)+ 决策面包屑 — 设计

日期:2026-06-17  ·  阶段:M0 扩展  ·  状态:已通过设计评审,待写实现计划

## 背景与目标

vibetrace 已能把 git 历史 + Claude Code 会话富集成"AI 替我做了什么、为什么"的叙事。
但用户随时会盯着一段代码问"这里当初为什么这么写、有没有否决过别的方案"。

产品要回答的核心质疑:**用户看 logfile 也能问 AI,我们的优势在哪?**
答案是 **检索**:logfile 里没有"贴着这几行代码的决策痕迹"。本功能把这条痕迹做成
一等公民,并让"问"这个动作只做廉价检索 + 一次轻综合。

目标:`vibetrace ask <文件>[:起-止] "问题"` 给出**有据可查**的回答,材料来自这段代码
相关 commit 的已缓存叙事 + 人/agent 在写代码时留下的决策面包屑。

## 架构原则:write-time 捕获,read-time 廉价检索

把认知重活从"问的时候"挪到"写的时候":

```
写代码时(捕获,几乎零成本)              问的时候(检索 + 一次轻 LLM)
─────────────────────────              ────────────────────────────
agent 在 commit message 留:            vibetrace ask foo.py:42-60 "为什么这么写"
  Vibe-Decision: 用 urllib 不引第三方        │
  Vibe-Watch:    先这么扛,X 待验证           ├─ git log -L42,60:foo.py → 命中的 commit(旧→新)
        │                                    ├─ 每个 commit:取已缓存叙事(why/decisions/risks)
   digest/enrich 收割 trailer:               │              + 收割该 commit 的 Vibe-* trailer
     Decision → 并进该 commit decisions       ├─ 拼成有界上下文(几条决策,不灌整 diff)
     Watch    → 进 risks → 封胶囊         └─ 一次轻 LLM:只对着这份现成材料答问题
```

贵活(叙事)只在 commit 那次按 SHA 算一遍、永久缓存;`ask` 永远只取现成的。
这就是 logfile 拿不到的东西,也是"深耦合却不重"的实现:要不要日后验证由人/agent
在**写的当下**用 `Vibe-Watch` 标,不靠 query-time 让 LLM 猜。

## 决策面包屑约定

git trailer 风格,写在 commit message 正文(body)。区分大小写,行首匹配:

- `Vibe-Decision: <一句话决策,可含被否决备选>` — 收割后**用人原话**并进该 commit 的
  `decisions`(不让 LLM 改写,最忠实);去重。
- `Vibe-Watch: <一句话:不确定 / 待验证的点>` — 收割后并入该 commit 的 `risks`(**不是**
  `open_loops`:全仓唯一封胶囊入口 `cli.py:97` 只遍历 `risks`),由现有 risks→`seal_capsule`
  链路封一枚 21 天后到期、可验证的胶囊。

**捕获靠约定,不靠代码**:在 `CLAUDE.md` / `AGENTS.md` 加一句——"做关键取舍时留
`Vibe-Decision:` trailer;没把握、需日后验证的留 `Vibe-Watch:`"。你本就用 agent 写代码,
让 agent 自动留,你零额外动作。人手写也可。无面包屑时,功能降级到只用已有叙事(B 兜底)。

## 组件

### 1. `gitlog.py`(+~45 行 → ~162)
- `line_log(project_path, file, start, end)` → `(shas oldest-first, error_or_None)`:
  `git log -L<start>,<end>:<file> -s --format=%H` 取命中这几行的 commit SHA(`-s` 抑制
  patch,只要 SHA);超过上限(12 条)取最近 12 条。失败(坏行号/文件不在历史等)返回
  error,调用方降级到文件级 `git log --format=%H -- <file>`。
- `parse_breadcrumbs(body)` → `(decisions: list[str], watches: list[str])`:逐行 strip,
  匹配 `Vibe-Decision:` / `Vibe-Watch:` 前缀,取冒号后内容。无则返回两个空列表。容错:
  body 为空/None 不报错。

### 2. `enrich.py`(+~12 行 → ~139)
在 `enrich_commits` 内,**把面包屑合并放在现有 `redact_secrets` 脱敏(`enrich.py:74`)之前**——
让那一次脱敏顺带覆盖面包屑文本(修 priv-1,零新增脱敏调用):
- `decisions, watches = parse_breadcrumbs(commit["body"])`
- `decisions` 去重并入 `narrative["decisions"]`;`watches` 并入 **`narrative["risks"]`**
  (**不是 open_loops**:`cli.py:97` 封胶囊只遍历 `risks`,进 open_loops 永远封不出胶囊),
  合并后再走现有 `json.loads(redact_secrets(json.dumps(...)))` 才 `put_narrative`。

`commit["body"]` 已由 `collect_commits` 提供,无需新取数据。缓存命中(SHA 已叙事)的
commit 不回补——SHA immutable,首次富集时折叠一次即终生固定,符合缓存约定。

### 3. `llm.py`(+~25 行 → ~168)
- `narrate(...)` 增加可选参数 `system=None`,贯穿到 `_openai_compat` / `_anthropic`;
  为 `None` 时用现有 `SYSTEM_PROMPT`(行为不变)。
- 新增 `ASK_SYSTEM_PROMPT`:接地问答纪律——只用给定材料作答;材料不足直说"材料不足",
  不补全、不编造文件名/SHA/数字;在 `cited_shas` 列出实际用到的 commit;延续现有反幻觉
  与不张冠李戴红线。
- 新增 `ASK_SCHEMA`:`{answer: string, cited_shas: string[], unsure: string}`,
  required `[answer, cited_shas]`。`unsure` 给模型一个诚实出口(没把握的部分)。

### 4. `ask.py`(新建,~150 行)
- `_parse_target(target)` → `(file, start_or_None, end_or_None)`:末段 `:` 后匹配
  `\d+-\d+` 或 `\d+` 才当行范围(路径含 `:` 极少);否则整串为文件。
- `_retrieve(project_path, file, start, end, cache)` → `(context_str, shas, code_state)`:
  - 有范围走 `line_log`,失败/无范围走文件级;取到命中 SHA(旧→新)。
  - 逐 SHA:`cache.get_narrative(sha)` 取 why/decisions/risks;`get -s body` 收割 trailer
    补进去;拼一段 `[sha7] date subject / 决策… / 风险…`。叙事为 None(从未 digest)时只用
    subject + 面包屑(降级仍有料)。
  - 按字符预算(6000)截断;`code_state` = 命中行的最新 commit SHA(供缓存键)。
- `ask(project_path, target, question, vault=None)`:
  - 组缓存键 `"ask:" + sha256(file|range|question|code_state)`;命中直接返回缓存答案。
  - 无命中:`LLMClient` → `narrate(prompt, schema=ASK_SCHEMA, system=ASK_SYSTEM_PROMPT)`;
    `redact_secrets` 后缓存(复用 `put_narrative`,如 course 用 `course:` 前缀的先例,不加表)。
  - 打印 `answer` + `据此回答的 commit: <cited_shas>`;`vault` 给定时写一份脱敏 Q&A 笔记。
  - 返回 `(answer_text, error_or_None)`。

### 5. `cache.py`(+1 行 → ~203)
`recent_open_loops` 的 `WHERE` 补 `AND sha NOT LIKE 'ask:%' AND sha NOT LIKE 'course:%'`
(详见『数据与缓存』cons-4)。不加表,继续复用 `put/get_narrative`。

### 6. `cli.py`(+~25 行 → ~238)
新增子命令:`ask`,位置参数 `target`、`question`;`--project`(默认 `.`)、`--vault`。
转调 `ask.ask`,有 error 打印到 stderr 返回 2,否则返回 0。

### 7. `CLAUDE.md` / `AGENTS.md`(+2 行约定)
加面包屑约定(见上)。这是"产品化"的关键:让协作的 agent 自动留痕。

## 数据与缓存
- ask 答案:键 `ask:<hash>`,复用 `commit_narratives` 表(经 `put/get_narrative`),
  值 `{answer, cited_shas, unsure}`。`code_state` 进哈希 → 代码一变,旧答案自然失效。
- 面包屑:不单独存,折进 SHA 叙事(immutable),随叙事缓存。
- **检索污染防护**(cons-4):`ask:` 行(同 `digest:`/`course:`)与 commit 叙事同表却无
  `open_loops`,会挤占 `recent_open_loops` 的 `LIMIT` 名额、令简报『悬而未决』随提问增多越查越空。
  故改 `cache.recent_open_loops` 的 `WHERE`,在 `sha NOT LIKE 'digest:%'` 上补
  `AND sha NOT LIKE 'ask:%' AND sha NOT LIKE 'course:%'`(`course:%` 既存漏网,同行顺手补全)。

## 隐私(红线)
- 喂 LLM 的上下文可能含 diff 片段 → 属"数据不出本机,LLM API 调用除外"的允许例外。
- 写缓存、写 vault 笔记**之前**一律 `redact_secrets`(答案可能回显 diff 里的 key)。
- **面包屑入缓存也须脱敏**(priv-1):人原话可能粘 token;实现上把面包屑合并放在 `enrich.py:74`
  那次 `redact_secrets` 之前,单次脱敏即覆盖,绝不在脱敏之后才并入再 `put_narrative`。

## 降级与容错(CLAUDE.md:解析外部数据必须容错,绝不崩溃)
- 无 API key / LLM 失败 → 不综合,直接打印这几行的**原始决策史**(commit + 决策 + 面包屑),
  照样有用。
- `git log -L` 失败(坏行号、文件不在历史)→ 退文件级 `git log -- <file>`。
- 文件级也失败 / 文件无任何历史 → 明确报错(返回 2),不崩。
- trailer 解析、body 缺失:静默降级为"无面包屑"。

## 验收标准(goal-driven)
1. `vibetrace ask vibetrace/llm.py:72-78 "为什么 narrate 要带 max_tokens"` 的回答引用真正
   改过这几行的 SHA,并命中"推理模型(deepseek-v4-pro)先花 reasoning token、3000 不够"
   这条理由(该理由在叙事/注释里有据)。验证 `cited_shas` 确属命中那几行的 commit。
2. 反幻觉:问一段**无历史**的行 → 回答"材料不足",不编造 commit / 文件名。
3. 无 API key 运行 → 打印这几行的原始决策史(不崩、不空)。
4. 造一个带 `Vibe-Watch:` trailer 的 commit,跑 `digest` 后 → 该 watch 进 `risks`、经现有
   risks→`seal_capsule` 封出一枚到期可验证的胶囊;其 `Vibe-Decision:` 原话进当日 decisions。
5. 多次 `ask` 后跑 `brief`:『悬而未决』仍只列真 open_loops,不被 `ask:`/`course:` 行挤掉。
6. 各模块行数:ask.py <300,gitlog/enrich/llm/cli/cache 改后均 <300(预算见上)。

## 非目标(YAGNI)
- **ask 不回写理解债**:"问 = 理解"语义可疑;认知耦合已由面包屑→叙事/胶囊达成,够了。
- **不做上下文包(原 C 方案)**:`vibetrace context` 喂给外部 coding agent 范围更大,延后。
- 不做函数/符号级解析(需 AST/ctags,违反 M0 简单优先);只到文件 + 行范围。
- 不做内嵌 HTML / Obsidian 回写入口;CLI 一问一答即可,检索器以后可被任何入口复用。

## 风险与开放问题
- `git log -L` 在某些 git 版本对 `-s` 行为不一:实现时验证"`-s` 确实只剩 SHA",否则解析
  `^commit <sha>` 行兜底。
- 行范围会随代码漂移(今天的 42-60 ≠ 历史的 42-60):`git log -L` 本就按行历史回溯,
  语义正确;文档需告诉用户行号按**当前文件**给。
- 面包屑靠 agent 自觉留;初期历史没有面包屑,功能完全靠 B(已有叙事)兜底,可用但signal较弱
  ——这是预期的渐进增强,不阻塞上线。

## 评审修订(2026-06-17 对抗审查:23 agent / 4 维度 / 逐条反驳)
确认并已折入 3 处真问题(LOW cons-3 随 #1 自然消解,无需单独动):
1. **HIGH cons-1**(consistency/m0/moat 三维独立命中):Vibe-Watch 原设计进 `open_loops`,但
   全仓唯一封胶囊入口 `cli.py:97` 只遍历 `risks` → 永远封不出胶囊、验收 #4 必败。已改为
   Vibe-Watch 收割进 `risks`,直接复用现有 risks→`seal_capsule` 链路。
2. **HIGH priv-1**:面包屑(人原话)原在脱敏之后才并入再写缓存 → 可能把粘进 commit 的 token
   落盘。已改为把合并提前到 `enrich.py:74` 那次 `redact_secrets` 之前,单次脱敏覆盖。
3. **MED cons-4**:`ask:` 行复用 `commit_narratives` 同表却无 open_loops,挤占
   `recent_open_loops` 的 LIMIT、污染简报『悬而未决』。已改 `cache.recent_open_loops` 的
   WHERE 排除 `ask:%`/`course:%`(后者既存漏网,顺手补全)。
