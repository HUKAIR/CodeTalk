# vibetrace

**AI writes your code. Three months later, nobody knows why it was written that way.**

vibetrace grounds "why" in real commit history — verbatim citations you can click and verify, not AI confabulation. Zero-LLM, local-only, pure stdlib.

---

**AI 高速写码，三个月后没人知道当初为什么这么写。** vibetrace 把「为什么」钉在真实 commit 记录上——逐字引用、可点开核验，不是 AI 反推编造。零 LLM、数据不出本机、纯标准库。

### Why this matters

- **Trust is collapsing.** 46% of developers actively distrust AI output; only 3% highly trust it. *(Stack Overflow 2025, N=33,244)*
- **AI "explanations" are fabricated.** We blind-tested 5 real commits: AI inferred "why" from diffs alone — **5/5 missed the real decisions, 2/5 completely wrong.** *(This repo, reproducible: `python3 scripts/blind_test.py . 5`)*
- **Your chat history is fragile.** 8+ bug reports across Cursor, Claude Code, and Copilot: conversations silently vanish — data still on disk, UI can't surface it.

### 为什么重要

- **信任正在崩塌。** 46% 开发者不信 AI 输出，仅 3% 高度信任。*(SO 2025, N=33,244)*
- **AI「解释」是编造的。** 本仓 5 commit 盲测：纯 diff 反推 5/5 漏真实决策、2/5 完全弄错。*(可复跑: `python3 scripts/blind_test.py . 5`)*
- **你的对话历史很脆弱。** Cursor / Claude Code / Copilot 共 8+ bug 报告：对话静默消失——数据还在磁盘，UI 接不回。

### How vibetrace is different

| | AI inference (Cursor/Copilot) | vibetrace |
|---|---|---|
| Source | current diff | real commit + session transcript |
| Method | LLM guesses from code | zero-LLM deterministic lookup by SHA |
| Verifiable | no — plausible but ungrounded | yes — click SHA to see original |
| Data | sent to cloud | local-first; LLM calls opt-in (`--no-llm` for zero egress) |

### vibetrace 有什么不同

| | AI 反推 (Cursor/Copilot) | vibetrace |
|---|---|---|
| 来源 | 当前 diff | 真实 commit + 会话原话 |
| 方法 | LLM 从代码猜测 | 零-LLM 确定性按 SHA 查找 |
| 可核验 | 否——听起来对但无据 | 是——点开 SHA 看原文 |
| 数据 | 发往云端 | 本地优先；LLM 调用可关（`--no-llm` 零出网） |

> **Honest boundaries / 诚实边界:** Blind test is N=5, this repo only, human-judged — not a population claim. Coverage depends on `enrich`: this repo (with full backfill) reaches 100% (199/199); a separate 605-commit repo **without** enrich starts at 0.3%, reaching ~100% after `vibetrace enrich`. Without enrich or breadcrumbs, blame shows commit subjects only — similar to `git log`. Run `grounding_hitrate.py` on your own repo to measure. vibetrace finds "what was actually said and decided", not "whether the code is correct" — source records themselves may be wrong. Full methodology: `docs/discovery/2026-06-29-护城河对照卡-真实记录vs反推.md`.
>
> 盲测 N=5、本仓、人工判读，不是人群结论。覆盖率取决于 `enrich`：本仓（全量补全）100%（199/199）；另一本地 605-commit 仓**未 enrich** 时仅 0.3%，跑完 `vibetrace enrich` 后可达 ~100%。未 enrich 且无面包屑时，blame 只显示 commit subject——与 `git log` 接近。请在你自己的仓上跑 `grounding_hitrate.py` 度量。vibetrace 找的是「当初到底说了什么、为什么这么写」，不保证代码正确——源记录本身可能有误。完整方法见 `docs/discovery/` 下对照卡和盲测文档。

## 5 分钟上手 / Quick Start

```bash
# 1. Install
git clone https://github.com/HUKAIR/CodeTalk && cd CodeTalk
pip install -e .

# 2. Enrich your repo (builds decision narratives from git history — needs LLM key)
vibetrace init                              # write config, fill your API key
vibetrace enrich --project /path/to/repo    # backfill narratives (zero-LLM evidence auto-included)

# 3. See decisions
vibetrace blame /path/to/repo/somefile.py   # who decided what, with real citations
vibetrace ask /path/to/repo/somefile.py:20-30 "why was this written this way?"
```

Without `enrich`, blame shows commit subjects only (~0% coverage). After enrich, coverage reaches ~100%. No LLM key? Use `--no-llm` — blame/search/graph still work with breadcrumbs and git data.

```bash
# 不用 enrich 也可以 / Zero-LLM path (no key needed)
vibetrace install-agent-seed --project .    # AI agents auto-leave decision breadcrumbs
vibetrace blame somefile.py                 # shows Vibe-Decision breadcrumbs from commits
```

## 安装

```bash
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

把 `vibetrace.mcpb` 拖进客户端的扩展安装入口,装时选一个项目根目录即可。暴露 **7 个工具**
(全标 `readOnlyHint: true`,Claude Code / Cursor 可自动批准不弹确认):

| 工具 | 作用 | LLM |
|---|---|---|
| `vibetrace_ask` | 接地提问「当初为什么这么写」 | 有 key 用 LLM;无 key 降级确定性 |
| `vibetrace_blame` | 行级决策溯源 | 零 LLM |
| `vibetrace_graph` | 决策影响图(时间轴 DAG) | 零 LLM |
| `vibetrace_search` | 主题级「为什么」召回 | 零 LLM |
| `vibetrace_drift` | 偏差自检:AI 改了但没提交的文件 | 零 LLM |
| `vibetrace_prompts` | 指令回看:你给 AI 下了什么指令 | 零 LLM |
| `vibetrace_adr` | ADR 导出:MADR / Nygard / CycloneDX(AIBOM) | 零 LLM |

> 各客户端逐步安装 + 自检 + 排错见 **[`docs/mcp-install.md`](docs/mcp-install.md)**。
> Spec-driven 工作流(GitHub Spec Kit / AWS Kiro / OpenSpec / Antigravity)对接见
> **[`docs/spec-kit-integration.md`](docs/spec-kit-integration.md)**。

## IDE Extension (VS Code / Cursor / Windsurf)

Foldable decision CodeLens + hover cards — see **why** a line was written that way, with real commit citations. Like GitLens but for decisions, not just authorship.

**IDE 扩展**——可折叠 CodeLens + hover 决策卡：点开一条提交看 why / decision / rejected / risk，hover 任意行看完整上下文。类 GitLens 但补 why。

```bash
cd vscode-vibetrace
npm install && npm run build                        # 构建
npx @vscode/vsce package --no-dependencies          # 打包 .vsix
```

安装（三选一）：

```bash
cursor --install-extension vscode-vibetrace-0.2.0.vsix   # Cursor
code --install-extension vscode-vibetrace-0.2.0.vsix      # VS Code
# Windsurf: Extensions → Install from VSIX → 选文件
```

装完 Cmd+Shift+P → **Reload Window**，打开有 vibetrace 缓存的项目即可看到可展开的决策 CodeLens；hover 行可看完整卡片。

| 设置 | 默认 | 说明 |
|---|---|---|
| `vibetrace.enabled` | `true` | 主开关 |
| `vibetrace.pythonPath` | `"python3"` | 装了 vibetrace 的 Python 解释器路径 |

> 详细安装 + 排错 + 配置见 **[`vscode-vibetrace/README.md`](vscode-vibetrace/README.md)**。

## vibetrace web —— 自托管接地对话(新)

一个本地优先的交互网页:和 LLM 多轮讨论「这段代码当初为什么这么写」,但每一轮**先零-LLM
检索你项目的真实记录**(commit 叙事 / 决策面包屑 / 会话原话),把真实证据喂给模型,答案旁
**并排可核验的引用**;讨论本身脱敏后落库,反哺未来的 `ask`/`search`。**自托管 = 数据留在
你自己机器,卖软件不卖服务。**

```bash
pip install -e ".[web]"                            # web 面可选 extra(FastAPI/uvicorn;CLI/MCP 仍纯 stdlib)
vibetrace web --project /path/to/repo              # 绑 127.0.0.1、自动开浏览器、逐字流式
vibetrace web --project /path/to/repo --no-llm     # 零出网:降级为零-LLM 接地罗列
```

- **接地、可核验**:答案锚定真实 commit / 决策 / 会话原话,每条结论旁的引用可点开核验——这是
  和「套壳聊天」的分界线;**模型脱离真实材料不作答**(材料空 → 不调模型,只确定性罗列)。
- **隐私红线**:默认只绑 `127.0.0.1`、绝不 phone home(除 LLM 调用)、出网前 + 落库前脱敏、
  前端零外联(CSP `connect-src 'self'`;静态产物经 `scripts/check_static_no_external.py` 守);
  后端拒绝非 loopback Host 与跨 Origin 请求,防其它网页借 localhost 触发本地检索/LLM 调用。
- **给客户自托管**:单镜像 Docker(见 `Dockerfile`:`docker build -t vibetrace .` → `docker run`)。
- 前端首版为零-build 单文件 vanilla-JS;React/Vite 仅在 chat UX(流式已有,后续如需消息管理)再上。

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
    "kimi":      {"base_url": "https://api.moonshot.cn/v1", "api_key": ""},
    "doubao":    {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "api_key": ""},
    "glm":       {"base_url": "https://open.bigmodel.cn/api/paas/v4", "api_key": ""},
    "grok":      {"base_url": "https://api.x.ai/v1", "api_key": ""},
    "gemini":    {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key": ""},
    "anthropic": {"api_key": ""},
    "ollama":    {"base_url": "http://localhost:11434/v1", "api_key": "ollama", "local": true}
  }
}
```

切换模型:把顶层 `provider` 改成上面任一,并设对应 `model`(如 kimi→`kimi-k2-0905-preview`、
glm→`glm-4.6`、grok→`grok-4`、gemini→`gemini-2.5-pro`、doubao→端点 ID 或 `doubao-seed-1-6`)。
API key 也可用环境变量 `<PROVIDER>_API_KEY`(如 `DEEPSEEK_API_KEY` / `KIMI_API_KEY` /
`GLM_API_KEY` / `GROK_API_KEY` / `GEMINI_API_KEY` / `DOUBAO_API_KEY` / `ANTHROPIC_API_KEY`)。
除 anthropic 走官方 SDK(json_schema 结构化输出 + prompt caching)外,其余全走 OpenAI 兼容
协议(标准库 urllib,零额外依赖;DeepSeek 上下文缓存自动生效)。

**零-egress 本地推理**:把 `provider` 设为 `ollama`(或任何 `local: true` / 指向 `localhost`、
`127.0.0.1` 的 OpenAI 兼容端点,如 LM Studio / llama.cpp / vLLM),综合推理就在本机跑、**连
「LLM 调用」这唯一出网例外也不出网**(本地无需 key)。本地 32B 级代码模型在生成类任务上已逼近
云端;定位为「接地后的本地润色/解释」,agentic / 复杂综合仍建议云端。与 `--no-llm`(完全不调
LLM)形成两档隐私梯度。

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

- 会话源不是完整审计日志:Claude 主会话与 `*/subagents/**/agent-*.jsonl` 会纳入,但
  journal/meta 等旁路文件不采;Cursor / Codex 本地会话源为 opt-in 且依赖非官方本地格式。
- 会话-commit 对齐是软关联(±30 分钟时间窗 + 文件交集),目标准确率 80%,带 high/low 置信度
  标注,**不保证全对**。
- commit 被 amend / rebase 后 SHA 变化即视为新 commit;旧 SHA 缓存成为死数据。
- `graph` 文件级边在极小项目(如本仓 7 文件)偏密,靠稀疏节点压制;行级精度作非目标延后。
- Claude Code / Cursor / Codex 的本地会话格式都非官方稳定 API;版本升级可能破坏解析,
  解析器对未知字段忽略、缺字段降级,最坏退化为纯 git 模式。

## 架构

```
cli → gitlog(commit/diff/行历史/面包屑) ─┐
      sessions(Claude/Cursor/Codex 容错) ─┼→ align(软关联) → enrich(LLM,SHA 缓存) → report → vault
      cache(SQLite 单一真相源)          ─┘
零-LLM 工具:brief / debt / graph 直接读 cache + git,不经 enrich/llm。
LLM 统一封装:llm.py(多 provider / 重试 / token 日志 / prompt caching / 反幻觉+文风纪律)。
```

## 设计哲学(M0)

核心 CLI/MCP 面保持标准库 + anthropic SDK(可选);**禁** LangGraph / 向量库 / 重前端链路。
`vibetrace web` 是可选 web extra,仅该面允许 FastAPI / uvicorn,且惰性 import、不污染核心依赖。
单模块 <300 行;解析外部数据一律容错、失败降级绝不崩溃。行为准则见 `CLAUDE.md`(Karpathy
编码纪律:想清再写 / 简单优先 / 外科手术式改动 / 目标驱动)。设计与实现计划见 `docs/superpowers/`。
