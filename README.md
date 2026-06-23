# vibetrace

**本地优先的个人 AI 编码认知层(M0)。** 读你的 `git log` + Claude Code 会话记录,回答
DeepWiki 那类「代码是什么」工具回答不了的问题——**这代码是怎么变成这样的?当时 AI 替我做了
哪些决定、为什么?** 把答案沉淀成 markdown / 单文件 HTML,写进 Obsidian,偿还 AI 高速写码
欠下的**理解债**。

不是又一个 RAG,也不是 agent 框架。它是**跨时间的认知基础设施**:`brief` / `graph` 及理解债
**完全不调用 LLM**——关掉大模型,它们照样有价值。这是和「套壳」的分界线。

## 安装

```bash
git clone https://github.com/HUKAIR/CodeTalk && cd CodeTalk
pip install -e .                 # 核心:纯标准库,零三方依赖
pip install -e ".[anthropic]"    # 可选:仅 anthropic provider 需要
```

要求 Python ≥ 3.11。安装后有 `vibetrace` 命令(等价于 `python3 -m vibetrace`)。

## MCP 一键装(.mcpb)

把零-LLM 接地能力暴露给 Claude Code / Cursor / Codex 等 MCP 客户端,在 agent 工作流里
直接问「这段代码当初为什么这么写」。vibetrace 纯标准库、零三方依赖,打成一个 `.mcpb`
(zip:`manifest.json` + 源码)即可**一键装、一次构建覆盖所有客户端**,靠你已装的
`python3` 运行、**不打包解释器**:

```bash
python3 -m scripts.build_mcpb     # 产出 vibetrace.mcpb
```

把 `vibetrace.mcpb` 拖进客户端的扩展安装入口,装时选一个项目根目录即可。暴露 4 个工具:
`vibetrace_ask` / `vibetrace_blame` / `vibetrace_graph` / `vibetrace_search`。其中
`blame`/`graph`/`search` **零 LLM、stdio 同机直连、数据不出本机**;`ask` 会调用你
`~/.vibetrace/config.json` 里配置的云端 LLM 做综合(无 key 时降级为确定性检索,不崩)。

> 各客户端逐步安装 + 自检 + 排错见 **[`docs/mcp-install.md`](docs/mcp-install.md)**。

## 配置

```bash
vibetrace init        # 写配置模板到 ~/.vibetrace/config.json(自动 chmod 600)
```

`~/.vibetrace/config.json`:

```json
{
  "vault_path": "/path/to/obsidian/vault/folder",
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "diff_token_budget": 3000,
  "output_lang": "中文",
  "providers": {
    "deepseek":  {"base_url": "https://api.deepseek.com/v1", "api_key": "sk-..."},
    "openai":    {"base_url": "https://api.openai.com/v1", "api_key": ""},
    "qwen":      {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": ""},
    "anthropic": {"api_key": ""}
  }
}
```

API key 也可用环境变量:`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `QWEN_API_KEY` /
`ANTHROPIC_API_KEY`。deepseek / openai / qwen 走 OpenAI 兼容协议(标准库 urllib,零额外
依赖;DeepSeek 上下文缓存自动生效);anthropic 走官方 SDK(json_schema 结构化输出 +
prompt caching)。

## 命令

| 命令 | 做什么 | 例 |
|---|---|---|
| `digest` | 把一段时间的 commit + 会话富集成**变更叙事日报**(防幻觉、信件体、内嵌时间胶囊) | `vibetrace digest --since "3 days ago"` |
| `brief` | **开工简报**:你上次停在哪 + 理解债 top 3(**纯本地零 LLM**);`--all` 出**跨项目总览**(所有项目里有到期胶囊的 + 理解债最高的几个,按紧迫度) | `vibetrace brief` · `vibetrace brief --all` |
| `graph` | **决策影响图**:哪个决定牵动了后续哪些改动(时间轴 DAG,**零 LLM**;`--canvas` 导出 Obsidian Canvas) | `vibetrace graph --canvas` |
| `course` | **演进课程**:项目怎么一步步长成这样(分章 + 大白话 + 场景测验,单文件 HTML) | `vibetrace course` |
| `ask` | **就某段代码提问**,答案接项目记忆(叙事 + 决策面包屑),引用真实 commit | `vibetrace ask vibetrace/llm.py:72-78 "为什么这么写"` |
| `console` | **统一控制台(web 入口)**:开工概览 / 时光轴 / 决策图 / 理解债 四视图单页,概览优先、点击钻取——不再一整页 dump(**零 LLM**;`--serve` 回写胶囊) | `vibetrace console --serve` |
| `tunnel` | **时光轴**:线性提交时间线,最新在顶、按天分组、点开看叙事(`--serve` 胶囊回答即时写回) | `vibetrace tunnel` |
| `install-hook` | 装 git 钩子:手写 commit 时在编辑器里提示留 `Vibe-Decision`/`Vibe-Watch` 面包屑 | `vibetrace install-hook` |
| `install-agent-seed` | 把决策捕获约定植入项目 `CLAUDE.md` + `AGENTS.md`,让 **AI coding agent**(Claude / 其他)提交时自动留推导面包屑(**写时捕获 > 事后从 diff 反推**) | `vibetrace install-agent-seed` |

`digest` 产物:`<vault>/YYYY-MM-DD-<project>.md` —— 去年今日 / 上月今日回流 → 今日概览(信件体)
+ 今日决定 → 到期的时间胶囊(供回填)→ 按 commit 的叙事 → 未闭环汇总 → 运行统计。时间胶囊把
每条 risk 密封 21 天,到期在日报里端回面前,闭合「预测—验证」环。

### 决策面包屑(让 `ask` / `graph` 更准)

做关键技术取舍时,在 commit message 正文留一行:

```
Vibe-Decision: 用 urllib 不引第三方——M0 禁三方依赖
Vibe-Watch:    先这么扛,并发安全待验证
```

`digest` 会把 `Vibe-Decision` 并进该 commit 的决策、`Vibe-Watch` 并进风险(到期封成可验证胶囊);
`ask` 据此接地回答、`graph` 据此连决策影响边。你本就用 AI 写代码——让它顺手留痕。行首精确匹配、
区分大小写。

手写 commit(不带 `-m`)的提交者,跑一次 `vibetrace install-hook` 装 `prepare-commit-msg` 钩子,
编辑器里会自动提示这两行——填则成 trailer,不填被 git 剥除。git 钩子不随仓库版本控制,
**每个 clone 各装一次**。

## 缓存与隐私

- commit 叙事以 SHA 为键缓存于 `~/.vibetrace/cache.db`,**永不重算**;重跑同一天 digest 为
  0 次 LLM 调用、亚秒级返回。`graph:`/`course:`/`ask:` 派生结果同表加前缀键缓存。
- 会话解析以 (session_id, mtime, size) 增量缓存;每次运行参数追加到 `~/.vibetrace/usage.log`。
- **数据不出本机**(LLM API 调用除外);写缓存 / 写 vault / 注入 HTML **之前**,对常见 secret
  模式(API key / token / JWT / 私钥 / Google / Stripe / Slack …)一律脱敏。
- **`no_llm` 硬开关**:把那个「LLM 调用」例外也关掉,**保证零 egress**。三种方式任一即生效,
  全局覆盖(含 MCP `ask` 工具):config.json 置 `"no_llm": true`、设环境变量 `VIBETRACE_NO_LLM=1`、
  或给 `digest`/`ask`/`course` 加 `--no-llm`。开启后 blame/graph/search/brief/prompts 照常,
  ask/course/MCP ask 降级为确定性检索,digest 因必须用 LLM 而直接退出(信息明确,不静默)。

## 已知限制(M0)

- 只解析主会话转写(`<sessionId>.jsonl`);subagent / workflow 子转写中的文件改动对齐不可见。
- 会话-commit 对齐是软关联(±30 分钟时间窗 + 文件交集),目标准确率 80%,带 high/low 置信度
  标注,**不保证全对**。
- commit 被 amend / rebase 后 SHA 变化即视为新 commit;旧 SHA 缓存成为死数据。
- `graph` 文件级边在极小项目(如本仓 7 文件)偏密,靠稀疏节点压制;行级精度作非目标延后。
- 会话 JSONL 是 Claude Code 非官方内部格式(实测规格见 `docs/claude-jsonl-schema.md`);
  版本升级可能破坏解析,解析器对未知字段忽略、缺字段降级,最坏退化为纯 git 模式。

## 架构

```
cli → gitlog(commit/diff/行历史/面包屑) ─┐
      sessions(JSONL 容错)              ─┼→ align(软关联) → enrich(LLM,SHA 缓存) → report → vault
      cache(SQLite 单一真相源)          ─┘
零-LLM 工具:brief / debt / graph 直接读 cache + git,不经 enrich/llm。
LLM 统一封装:llm.py(多 provider / 重试 / token 日志 / prompt caching / 反幻觉+文风纪律)。
```

## 设计哲学(M0)

仅标准库 + anthropic SDK(可选);**禁** LangGraph / 向量库 / Web 框架。单模块 <300 行;
解析外部数据一律容错、失败降级绝不崩溃。行为准则见 `CLAUDE.md`(Karpathy 编码纪律:想清再写 /
简单优先 / 外科手术式改动 / 目标驱动)。设计与实现计划见 `docs/superpowers/`。
