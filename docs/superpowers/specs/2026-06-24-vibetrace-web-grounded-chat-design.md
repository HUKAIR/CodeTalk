# vibetrace web + 接地式 Claude 对话 — 设计 spec

> 状态:草稿(待对抗审 spec)。架构经多轮对话与设计 workflow 定为 **A:Python FastAPI 后端 + React/Vite SPA**,首屏 = 接地式 Claude 对话 + 引用证据面板;对话落库反哺接地。

## Goal(一句话)
给 vibetrace 一个**自托管、可部署、零安装摩擦**的交互 web app:核心是一个**接地式 Claude 对话**——你和 Claude 多轮讨论「这段代码当初为什么这么写」,但每一轮都先零-LLM 检索你项目的真实记录(commit 叙事 / 决策面包屑 / 会话原话 / 测试 / PR)作为上下文喂给 Claude,答案旁并排显示**可点开核验的真实引用**;讨论本身脱敏后落库,成为新的接地记录源,反哺未来的 ask/blame/search/digest。

## 北极星 / 护城河约束(load-bearing)
- **差异化不是「跟 Claude 聊」**(套壳人人有),而是「**聊的每句都锚定在你真实记录上、且每条结论可当场核验**」。引用与接地 = 产品本身,不是装饰。
- **绝不让 Claude 脱离检索到的真实记录自由发挥**——否则就成了 vibetrace 一直对抗的「AI 反推式编造」。
- **零-LLM 接地仍是地基**:`no_llm` 开启时,对话降级为纯零-LLM 的 `search`/`blame` 罗列,不崩。

## 隐私红线(不变,适用所有面)
1. **自托管 + 绝不 phone home**:除「LLM 调用」这唯一例外,无任何遥测/外联;vendored 前端静态资源不走 CDN。
2. **默认只绑 `127.0.0.1`**(继承 webserve.py)。
3. **双脱敏**:发给 Claude 前 + 落库前都过 `redact_secrets`/`redact_data`;对话记录属「皇冠明珠」级,留本机。
4. **`no_llm` 三入口硬开关**(config/env/CLI)对对话生效:开启即不出网,降级零-LLM。

## M0 分面修订(写进 CLAUDE.md)
- **新 web-app 面**:允许框架/依赖,作 `pip install -e ".[web]"` **可选 extra**(fastapi/uvicorn/anthropic);前端 React/Vite/npm 构建链允许,但产物 vendored 进包、用户侧不碰构建。
- **CLI / MCP 面**:守 stdlib(核心 `dependencies=[]` 不变);web extra 不得被 CLI/MCP import。
- **隐私红线**:不变(见上)。

## 架构
```
客户机器(单一信任域,数据不出本机)
┌──────────────────────────────────────────────────────────────┐
│  浏览器 React SPA  ──HTTP/JSON + SSE(127.0.0.1)──►  FastAPI    │
│   · 接地对话(流式)                                  (vibetrace.web)│
│   · 右侧引用证据面板(可点开核验)                       │ 直接 import │
│   · 时间轴/决策图/blame 支撑视图              ┌─────────▼─────────┐│
│                                              │ 接地对话核心(新)   ││
│                                              │ chat.py / conversation.py ││
│                                              │  retrieve→inject→stream→cite ││
│                                              │  + 复用零-LLM 引擎  ││
│                                              │  blame/search/graph/cache ││
│                                              └────┬──────────┬────┘│
│  Claude API(唯一 egress,脱敏后,可 no_llm 硬关)◄┘          ▼     │
│                                              ~/.vibetrace/cache.db │
│                                              + 本地 git + 会话 JSONL│
└──────────────────────────────────────────────────────────────┘
```

## 接地对话协议(每一轮的确定性流程)
1. **检索(零 LLM)**:据本轮问题 + 对话历史,跑 `search.topic_search` / `blame.collect_segments` / `cache.search_narratives` / 相关 commit narratives,取真实证据集(每条带 SHA / 决策 / 会话原话锚点 / 测试 / PR)。
2. **脱敏注入**:证据集过 `redact_secrets` 后,作为「材料」拼进发给 Claude 的上下文;system prompt 强制「只据材料综合,每条结论标注依据的锚点 id;材料不足直说」(复用 ASK_SYSTEM_PROMPT 纪律)。
3. **流式综合**:`llm.py` 新增 `chat_stream(messages, ...)`(anthropic streaming),token 级流回前端。
4. **引用回挂**:把本轮检索到的证据集 id 化,前端右侧面板按引用 id 展开真实记录(可核验)。
5. **落库**:本轮(问题 + 综合答 + 引用的证据 id + 时间)脱敏后写 cache.db 新表;成为新接地记录源。
6. **no_llm 降级**:步骤 3 跳过,直接把步骤 1 的零-LLM 检索结果作为「答案」返回(确定性罗列,不崩)。

## 数据落库(cache.db 新表,反哺接地)
- 新表 `web_conversations`(或复用 narratives 加前缀键):字段 `conv_id, project, ts, role(user/assistant), text(已脱敏), cited_shas(json), model`。
- 反哺:未来 `ask`/`search`/`digest` 可把这些讨论作为额外 why 源召回(「你在 X 日讨论过,结论 Y,依据 commit Z」)。落库即脱敏,immutable。
- 隐私:web_conversations 属皇冠明珠,留本机;`no_llm` 下不产生(无对话)。

## HTTP 端点(FastAPI,def 路由自动入线程池;每请求新 Cache 连接;出口必经 redact)
- `POST /api/chat`(SSE 流式):body {project, conv_id?, question} → 流式 token + 末尾 citations payload。
- `GET /api/conversations?project=` / `GET /api/conversation/{id}`:回看历史讨论(落库的)。
- `GET /api/console?project=`:`console._assemble` 一份聚合(时间轴/概览/图/债)。
- `GET /api/blame?project=&target=`、`GET /api/graph?project=`、`GET /api/search?project=&q=`:支撑视图,全复用现成纯函数。
- `GET /api/projects`:`cache.distinct_projects()` 项目切换器。
- `POST /api/capsule`、`POST /api/reviewed`:写回逻辑移植自 webserve.py(含 `_OUTCOMES` 白名单)。
- `GET /`:托管 vendored SPA 构建产物(StaticFiles)。

## 复用清单(引擎零重写,直接 import)
`console._assemble` · `tunnel._payload` · `graph.build_graph_json` · `blame.collect_segments` · `search.topic_search` · `cache.search_narratives/get_narrative/distinct_projects/set_capsule_outcome/mark_reviewed` · `config.redact_secrets/redact_data/load_config` · `ask.format_evidence/_test_refs/_pr_refs`(引用渲染)· `llm.LLMClient`(加 chat_stream)。新写:`chat.py`(对话编排 <300)、`conversation.py`(落库/召回 <300)、`web.py`(FastAPI 路由 <300)、`llm.chat_stream`、`frontend/`(SPA)。

## 部署(零安装摩擦)
- 主路径:`vibetrace web [--project .] [--port 0]` — 已装 vibetrace 的用户**零新增安装**(`[web]` extra 装一次),一条命令、自动开浏览器、自动认当前 git 仓、复用 ~/.vibetrace、localhost 不要登录。
- 给客户服务器:一条 `docker run`(预构建单镜像含 SPA dist;不让客户碰构建);默认绑 127.0.0.1。
- 全新用户:`pip install "vibetrace[web]" && vibetrace web` 或 `uvx`。

## MVP 范围
1. **接地式对话(首屏/卖点)**:多轮、流式、右侧引用证据面板;落库;no_llm 降级。
2. **引用证据面板**:本轮答案依据的真实 SHA/决策/会话原话/测试/PR,可点开核验。
3. **支撑视图**:时间轴(console/tunnel 数据)、决策图(JS 孤岛复用 graph.html)、blame/search。
4. 顶栏项目切换器。
**不含**:account/权限、course、PDF 导出、对话分支/编辑(v2)。

## 分阶段实施(关键:先建可测的护城河核心)
- **Phase 1（现在可 TDD,纯 Python,不需 web extra)**:`conversation.py`(cache.db 新表 + 脱敏落库 + 召回 + 反哺接地)、`chat.py`(retrieve→inject→build messages→cite 的接地编排,LLM 用 mock 测)、`llm.chat_stream`(可测非流式回退 + 接口)、`no_llm` 降级路径。全 stdlib unittest,复用引擎。
- **Phase 2（需 [web] extra）**:`web.py` FastAPI 路由 + SSE + StaticFiles + 写回移植;pyproject `[web]` extra;`vibetrace web` 子命令接线。
- **Phase 3（需前端构建链）**:React/Vite SPA(聊天 + 引用面板 + 支撑视图 + 项目切换器);vendored 进包。
- **Phase 4**:单镜像 Dockerfile + 部署文档 + M0 修订写入 CLAUDE.md。

## 测试与验证
- Phase 1:stdlib unittest，LLM mock；接地协议(检索→注入材料含真实锚点 id；答案落库脱敏；no_llm 降级返回零-LLM 结果不崩);conversation 反哺(召回落库讨论)。
- Phase 2/3:需 `[web]` extra + node;在装齐环境跑 FastAPI TestClient + 前端构建。沙箱内标注「需 web extra」。
- 各 Python 模块 <300 行;隐私:测「发 LLM 前 + 落库前」均脱敏、出口 redact、no_llm 不出网。

## 非目标(YAGNI)
多租户/账号/团队、云托管、对话分支编辑、PDF、把零-LLM 引擎迁出 Python、给客户暴露构建链。
**补(对抗审 M-3)**:不做对话历史回看 UI、不做项目切换器(锁单项目 `--project .`)、不在 web 外壳移植胶囊/reviewed 写回(那是 console --serve 的活)——均与「接地对话」首屏卖点无关。

---

## 对抗审修订(2026-06-24,已采纳;5 Critical + 7 Important)

### 贯穿不变式(验收锚)
> **喂模型的材料 ≡ 面板展示的证据 ≡ 落库反哺召回的内容 —— 三者必须是同一份「过了 egress redact 的可核验真实记录」。** C-1/C-2/C-3 都是它的实例。

### Critical 修订
- **C-1 脱敏锚点错位**:检索材料含 `merge_breadcrumbs` 现场读的 git 原文(Vibe-Decision/Watch)+ commit subject,**从不进 cache、从不脱敏**(ask.py:69 发 LLM 前无 redact)。改:**发给 LLM 的完整 user message(question + 注入历史轮 + 全部检索材料)在拼进 messages 的最后一步整体过一次 `redact_data`**,不依赖上游已脱敏假设。
- **C-2 反哺闭环实测是断的**:`fts_body` 只索引 `why`+`decisions`,对话存进 commit_narratives 会被索引成空 body、永远 0 命中。改:**独立新表 `web_conversations`**(非派生键),insert 方法内部强制 `redact_data`(对齐 put_narrative 单点收口),`project` 存绝对路径;**对话 text 接进 FTS,使 `topic_search` 能召回**。
- **C-3 三源同步**:`ask._retrieve` 只喂 LLM 二手 `context` 摘要(EXCERPT=200 截断),evidence/test/pr 原话只附给人看、**LLM 从没读到**。改:**注入模型的材料 = context 摘要 + evidence/test/pr 全文锚点块**(同一份既喂模型又挂面板)。
- **C-4 复用清单纠错(import 即崩)**:`ask.format_test_refs/format_pr_refs`(非 `_test_refs`);删 `tunnel._payload` 单列(用 `console._assemble(pp,cache)`);`format_*` 是**文本渲染器**(仅用于 no_llm 罗列 + 喂 LLM 材料文本,**前端 citation 面板需新写 evidence→JSON 序列化层**);`graph.build_graph_json` 返回 `(json_str, err)` 元组;`_OUTCOMES` 在 `report.py`。
- **C-5 流式绑错 provider**:默认 `provider=deepseek`(urllib + json_object,无流式);全仓零流式代码。改:正名「Claude」→「配置的 LLM provider(默认 deepseek,可配 anthropic)」;**Phase 1 只承诺非流式 `chat()` 可测接口**,全 provider token 级流式移入 Phase 2 + 诚实标注「对话把脱敏材料 POST 给第三方 deepseek」。

### Important 修订
- **I-1** `chat()`/`chat_stream` 必经 `LLMClient`(继承 `__init__` no_llm 抛 LLMError 闸门);no_llm 在进流式前就降级。
- **I-2** no_llm/材料空 降级:SSE 单 event 推完整零-LLM 罗列 + citations + `done`(不挂起前端);材料空 → LLM 不被调用。
- **I-3** 引用由**检索层**确定(非模型自报 `cited_shas`,流式自由文本下会丢);新写 `CHAT_SYSTEM_PROMPT`(基于 ASK 硬纪律,去掉「输出单个 JSON」)。
- **I-4** 多轮:每轮重检索;历史仅供理解追问意图、不得作事实依据。
- **I-5** search.py 新增 `collect_topic_hits`(主题级 + 返回结构化锚点,~15 行);`topic_search` 重构为复用它;chat 检索 = `collect_topic_hits` ∪ `blame.collect_segments`。
- **I-6** 前端「不走 CDN/不 phone home」可验证机制:构建产物 grep 扫 dist 断言无外链(CI 失败)+ 运行时 CSP `default-src 'self'; connect-src 'self'` + **前端零 LLM 直连**(egress 只在后端)。
- **I-7** 拆 `retrieval.py`(零-LLM 证据集装配,纯函数最易测)+ `chat.py`(编排),各 <300。

### Phase 1a 落地切片(本次自动执行,纯 Python,沙箱全测,无需 key/node/web-extra)
新模块:`search.collect_topic_hits`(I-5)· `retrieval.py`(证据集装配:topic_hits ∪ segments + 去重 + 锚点 id 化,同一份既喂 LLM 又 id 化进 citations)· `conversation.py`(`web_conversations` 表 + `save_turn` 内部 redact + list/get)· FTS 扩展(对话 text 可被 topic_search 召回)· `chat.py`(retrieve→inject→cite + no_llm/材料空 降级,LLM 作注入依赖)· `llm.chat()` 非流式接口(复用 LLMClient no_llm 闸门)· `prompts.CHAT_SYSTEM_PROMPT`。
测试(stdlib unittest + mock + fixture cache):① 真实锚点进材料 ② citations ≡ 材料 & prompt 含 evidence 原话 ③ sk-live breadcrumb 不进最终 payload + 落库前脱敏 ④ no_llm 零出网不崩 ⑤ 材料空 LLM 不被调用 ⑥ 落对话 → topic_search 召回。
后延(需环境):FastAPI/SSE 外壳、真流式 chat_stream、React SPA、Docker(Phase 2-4)。
