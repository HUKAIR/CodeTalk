# vibetrace 自我试点报告 II(dogfood on CodeTalk · 全命令面)

日期:2026-06-25 · 分支:`chore/dogfood-2026-06-25` · 在 CodeTalk 仓库自身跑**当前全部子命令**。

> 续 `2026-06-18-pilot-report.md`(只覆盖最早 6 命令)。此后 #45–#50 又上了 ~12 条命令
> (blame/search/prompts/console/report/web/mcp-serve/self/watch/init + 接地对话 web app),
> 从未系统 dogfood。本轮把试点补到完整命令面,并按护城河两条不变式(**零-LLM 仍有价值**、
> **隐私脱敏在落盘/出网前生效**)逐条核验。环境:LLM key 在 `~/.vibetrace/config.json`
> (deepseek),cache 有 CodeTalk 真实数据(53 条 commit 叙事、108 胶囊、FTS 已建)。

## 计划状态:丰富化计划(Pack A–D)已被 #36–#50 吸收,本轮补完 Phase E

逐项已核实在 `main`:A 脱敏 trivy 模式 + ask 接地优先级、B 反 AI 腔文风 + course 密度纪律、
C graph→Obsidian Canvas(`--canvas` 接线 + 测试)、D 打包/`init`/README/`--help`——全 ✅,
重做即重复立项。唯一缺口是 **Phase E 自我试点**,即本报告。

## 命令逐条结果(18 条)

| 命令 | LLM | 结果 | 验证点 |
|---|---|---|---|
| `brief` | 零 | ✅ | 理解债 top3 + 「你上次停在哪」+「悬而未决」,亚秒、纯本地。 |
| `brief --all` | 零 | ✅ | 跨项目 2 个(CodeTalk/另一本地仓);`LIKE '/%'` 滤掉 basename 幻影项目。 |
| `watch` | 零 | ✅ | 待验证收件箱空,友好提示。 |
| `self --days 30` | 零 | ✅ | 3064 次运行 **3032 次零-LLM**——「关掉大模型仍有价值」量化自证。 |
| `blame llm.py:64-76` | 零 | ✅ | 引真实 `b8ced37` + 其 Vibe-Decision 原话(行级溯源)。 |
| `search` | 零 | ❌→✅ | **发现并修复 moat-critical 召回 bug**(见下);修复后中文多字主题召回真实 commit。 |
| `prompts --since 30d` | 零 | ✅ | 指令时间线 + files_written,带会话名/时间。 |
| `graph` / `--canvas` | 零 | ✅ | HTML + `.canvas`(54 节点 / 305 边 / 40 决策节点配色 / 0 悬挂边,JSON 合规)。 |
| `course --no-llm` | 降级 | ✅ | 朴素分章 HTML,零-LLM 降级成立。 |
| `digest --no-llm` | 降级 | ✅ | 干净退出(exit 2)+ 明确理由,不崩。 |
| `ask …:行 --no-llm` | 降级 | ✅ | 确定性决策史罗列,引真实 commit。 |
| `ask …:行`(实时) | 是 | ✅ | 材料不足时**如实答「材料不足」+ 标不确定**,不编造——事实纪律生效。 |
| `tunnel` / `console` / `report`(静态) | 零 | ✅* | 各写单文件 HTML;**`console` 发现并修复脱敏顺序 bug**(见下)。 |
| `web`(GET / + 端点) | 零* | ✅ | `/`→200、CSP `connect-src 'self'`、`/api/search|graph|projects|console`→200。 |
| `web` 接地对话(实时) | 是 | ❌→✅ | 修复前只能引到无关讨论;修复后**引 5 个真实 commit、复述 `7bfb13a` 真实决策**。 |
| `mcp-serve` | 零 | ✅ | JSON-RPC initialize + tools/list(4 个零-LLM 工具)+ **tools/call vibetrace_search 修复后端到端通**。 |
| `init` | — | ✅ | 写配置模板,**chmod 600**,引导填 key。 |

未实时跑(成本/避免改仓):`digest`/`course` 实时(2026-06-18 已实测 + 测试覆盖)、
`install-hook`/`install-agent-seed`(会改仓,测试已覆盖)。

## 修复的两个真 bug

### 1)(moat-critical)`search` 与接地对话召回坏了 —— FTS 缺全部真实叙事

**现象**:`search "决策面包屑"/"时光轴"/"脱敏红线"` 全空;web 接地对话问「为什么用 vanilla-JS」
被引到无关的旧讨论。**根因**:`narrative_fts` 只含派生键(71 `graph:` + 4 `conv:` + 1 `ask:`,
body 多为空),**53 条真实 commit 叙事一条都没进 FTS**——`put_narrative` 虽在写时建 FTS,但
commit 叙事按 SHA immutable、`enrich.py` 命中缓存即跳过(永不重写),故「FTS 写入逻辑出现前
就已缓存」的叙事再也没机会被索引。`ask`/`blame` 直读 `get_narrative` 不走 FTS,所以一直没事。

**修复**(经 2 路对抗验证):`fts.py` 加一次性幂等 `backfill(conn)`,`Cache` 初始化时把缺失的
真实叙事(`sha NOT LIKE '%:%'` 排派生键)补建索引,**落 FTS 前 `redact_secrets`**——git 史证明
这 53 条叙事都在 redact 上线前入库、可能含明文 secret,与 `put_narrative` 的 FTS 写口径一致。
放 `fts.py` 而非 `cache.py`(已 283/300 行),无 import 环。**实测**:回填 53 条;`search`/MCP
`tools/call`/web 接地对话均恢复;二次构造补 0 行(幂等)。

### 2)(隐私红线 · Important)`console` 静态页脱敏顺序 bug

`console._build_html` 先 `inline_json(data)` 再对整页 `redact_secrets`——`json.dumps` 把 `="`
转义成 `=\"`,`key="value"` 形式的 secret(来自原始 commit subject / 债 / 概览)会绕过脱敏。
兄弟模块 `tunnel.py`/`course.py` 早已 `inline_json(redact_data(data))` 编码前脱敏,`console`
当初漏掉。**修复**:`inline_json(redact_data(data))`,保留落盘前整页 `redact_secrets` 兜底。
影响面:`render_console`(vault)/`serve_console`(127.0.0.1)/web `/console`(HTTP)。

> 其余 17 组逐命令 moat 扫描(零-LLM 纯度 + 脱敏顺序)全 **CLEAN**:brief/watch/self/debt、
> blame/search/prompts/graph、tunnel/report/web 非-LLM 端点/mcp 工具、digest/course/ask/chat
> 及 web `/api/chat[/stream]` —— 均无 LLMClient 误入零-LLM 路径,均在编码/出网前脱敏。

## 护城河核验结论

- **零-LLM 仍有价值**:self 报告 3032/3064 次零-LLM;brief/graph/search/blame/prompts 等纯本地产出有效。
- **隐私不出本机**:所有实时输出 0 secret;`console` 脱敏顺序补齐;web 绑 127.0.0.1 + CSP `connect-src 'self'`;静态产物无自动外联资源(`check_static_no_external` 过)。
- **确定性接地对抗幻觉**(本轮新证):接地对话引 `7bfb13a` 等真实 commit、复述其真实决策;材料不足时如实说「材料不足」绝不编造。

## 已知限制 / 后续(未在本 PR 修,显式登记不静默)

1. **2 字中文主题召回仍为空**(脱敏/缓存/隐私/胶囊…):`build_match` 丢弃 <3 字 term,trigram 对 2 字 CJK 天然无 shingle。这是与本 bug **不同**的查询侧限制,已由 `test_two_char_cjk_returns_empty` 钉为现状。修法另议(<3 字 CJK 走 LIKE 回退,或加 2-gram 索引)。**不可宣称「脱敏」已可召回。**
2. **派生叙事不可搜**:`backfill` 仅补真实 commit 叙事;`digest:`/`course:`/`ask:`(共 ~37 条,有 LLM 合成的 why/决策)仍不进 FTS。是否该可搜是产品取舍,本 PR 故意收窄到真实 commit(接地于真实决策)。
3. **富集覆盖缺口**:全仓 64 commit 仅 53 条有叙事,~11 条(含 squash 合并 `b8ced37`)无任何叙事——故「vanilla-JS vs React」那条理由在 commit 正文里、不在可搜叙事里。与 FTS 缺口不同的另一个缺口。
4. **接地召回噪声**:落库的 `[你的讨论]`「材料不足」非答会被索引、bm25 可能排前。可仿 `recent_open_loops` 过滤「材料不足」开头的 turn(未做)。
5. **`report.append_usage` 编码后脱敏**(report.py:155):现有调用只记元数据(命令/路径/计数),不漏;但对未来记自由文本的调用者是潜在隐患,建议统一为编码前脱敏。

## 结论

当前全部 18 条命令在 CodeTalk 真跑通、不崩、产出合理、0 secret 泄漏;补回了一个 **moat-critical
召回 bug** 和一个**隐私脱敏顺序 bug**,并端到端实证了护城河三性(零-LLM 有用 / 数据不出本机 /
确定性接地对抗幻觉)。416 单测全绿,各模块 <300 行。**可落地。** 限制项已显式登记,不静默。
