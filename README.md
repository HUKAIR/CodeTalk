# vibetrace

**回答「这段代码当初为什么这么写」——零-LLM 确定性接地到你项目里真实的 commit / PR / 会话原话(M0)。**
别人要你**手写**决策记录(ADR / Notion),vibetrace 从你已有的 `git log` + Claude Code 会话里
**自动挖出「当初为什么」并逐字接地**,对抗 AI 反推式编造。答案沉淀成 markdown / 单文件 HTML 写进
Obsidian,偿还 AI 高速写码欠下的**理解债**。

护城河是一个复合体(别人难同时给齐):**① 零-LLM 确定性 · ② 逐字引真实记录(可点开核验,不是 LLM
重述)· ③ 自动挖掘(非手写)· ④ 数据不出本机**。`brief` / `graph` / `blame` / `search` 及理解债
**完全不调用 LLM**——关掉大模型照样有价值,这是和「套壳」的分界线。接地**覆盖上限**(能零-LLM
确定性接地回答 why 的 commit 占比,**非答对率**)本仓 dogfood 自测约九成(撰写时 `78/85 = 91.8%`,
2026-06-25;随 commit 增长漂移,以复跑当下输出为准:`python3 scripts/grounding_hitrate.py`,口径=本仓
commit、不外推你的仓)。

为什么非得引真实记录、而不是让 AI 从 diff 反推:有三类 why **结构性**地不在 diff 里——**① why-NOT /
defer**(「为什么**没**这么做」「为什么先缓」,diff 只录已发生的改动)· **② diff 不可见的外部约束**
(如「沙箱无 `node` 故走零-build vanilla-JS」,约束不在代码里)· **③ `Vibe-Watch` 待验证项**(作者标的
「这条到期要回看」,diff 无此维度)。反推这些只能靠**编**——它还会**凭空捏造被否决的备选**(diff 里
根本没有的「考虑过 X 但放弃」)。这正是 Cursor / Claude Code 那种只能**从当前 diff 反推** why 的 git
考古结构上够不到的地方,也是 vibetrace 逐字引真实 commit / 会话原话、而非让 AI 事后编一个理由的地方。

> 本仓 6 commit 盲测自证(N=1,口径=本仓、非人群断言,见
> `docs/discovery/2026-06-25-护城河与北极星验证.md`;原为手工对抗实验,**现已可复跑**:
> `python3 scripts/blind_test.py [仓] [N]`——任意仓取 N 个带面包屑 commit,纯 diff 反推 vs 真实记录
> 并排 + 确定性「数据泄漏标」(标 why 是否已被 diff 夹带),**判对错由你**(语义需人,不自动打分)):
> 取 6 个带真实 `Vibe-Decision` 的 commit,让只看 diff 的 agent 重建「当初为什么」再逐条比对——
> **6/6 都有编造或遗漏,2/6 完全弄错真实理由**(`ed14b3c` 漏掉真决策、`b8ced37` 把因果讲反)。诚实
> 说明:看似「基本命中」的少数里有一半,只因 diff 本身**夹带了作者一并 commit 进去的说明文本**——是
> why 被一起提交进 diff,不是 diff 反推出了 why;扣掉这层数据泄漏,纯 diff 反推命中更低。
> **可复跑工具 + 干净样本复验**(`docs/discovery/2026-06-27-护城河盲测-可复跑+干净样本.md`;**与上面手工
> 6/6 是不同口径**——这里工具**默认自动挑「泄漏最低」的干净 commit**(why 不在 diff、对反推最有利)跑反推):
> 本仓 3 个干净样本上**反推 3/3 漏真决策、2/3 露骨编造**(含幻觉数字、整条认错主题)。诚实口径:N=3、
> 本仓、人工判读、未自动打分。

> 注:接地的是「当初到底说了什么、为什么这么写」这份**可核验的真实记录**,**不等于保证代码正确**
> ——源记录本身可能有误。vibetrace 解决的是「找回 why、对抗反推编造」,不是「替你审对错」。

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
  前端零外联(CSP `connect-src 'self'`;静态产物经 `scripts/check_static_no_external.py` 守)。
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
    "anthropic": {"api_key": ""},
    "ollama":    {"base_url": "http://localhost:11434/v1", "api_key": "ollama", "local": true}
  }
}
```

API key 也可用环境变量:`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `QWEN_API_KEY` /
`ANTHROPIC_API_KEY`。deepseek / openai / qwen 走 OpenAI 兼容协议(标准库 urllib,零额外
依赖;DeepSeek 上下文缓存自动生效);anthropic 走官方 SDK(json_schema 结构化输出 +
prompt caching)。

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
