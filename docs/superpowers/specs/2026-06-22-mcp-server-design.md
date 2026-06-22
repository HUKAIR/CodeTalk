# Spec: vibetrace MCP server(纯 stdlib stdio)

**Goal:** 把 vibetrace 的零-LLM 确定性接地能力(`ask` / `blame` / `graph`)暴露成一个 **MCP server**,让 Claude Code / Cursor / Windsurf 等 MCP 客户端在 agent 工作流里直接调用。一次构建覆盖多客户端、零 CAC 分发、被动产生使用(解冷启动)。**纯 stdlib 实现**(无 MCP SDK)。

**Architecture:** 新模块 `vibetrace/mcp_server.py`(<300 行):从 stdin 读**换行分隔的 JSON-RPC 2.0**、向 stdout 写响应、**所有日志只走 stderr**。实现最小 MCP:`initialize` 握手 → `tools/list` → `tools/call`,三个工具直接复用现成 `--json` 闭包(`ask.answer_question(as_json=True)` 等),不重写业务逻辑。CLI 加 `vibetrace mcp-serve` 入口(亦可 `python -m vibetrace.mcp_server`)。

**Tech:** stdlib `sys` / `json` 手写 JSON-RPC 循环;对照官方 MCP 规范 **2025-11-25**(已逐字核实:stdio = 换行分隔 JSON-RPC、消息内不得含换行、server 可写 stderr、**stdout 必须只含合法 MCP 消息**)。

## Global Constraints (M0)
- 仅 stdlib + anthropic;`mcp_server.py` <300 行;不引任何 MCP/JSON-RPC 第三方库。
- **容错降级绝不崩**:畸形 JSON / 未知 method / 工具内部异常 → 回 JSON-RPC error 或 `isError:true`,server 循环不退出。
- **数据不出本机**:stdio 本地进程通信,无网络;工具内部若触发 LLM(`ask` 有 key 时)是既有 M0 许可的 LLM 调用,无 key 则降级(`ask` 本就支持)。
- **脱敏**:工具输出复用已脱敏的 `--json` 产物(`answer_question` 经 `redact_secrets`),server 不新增落盘。

## 关键纪律(load-bearing)
- **stdout 纯净**:stdout 只能出现 MCP JSON-RPC 消息。因此:① 只调**返回字符串的闭包**(`answer_question(...,as_json=True)` 返回 text、`blame.collect_segments`+`_format`、`graph` 的 json 装配),**绝不调** `ask.ask()` / `blame.blame()` 这类 `print()` 到 stdout 的 CLI 入口;② server 启动时 `logging` 重定向到 stderr(`logging.basicConfig(stream=sys.stderr)`),压住 vibetrace 既有的 `log.warning` 与 token 计数日志;③ 任何 `print` 一律 `file=sys.stderr`。
- **握手**:`initialize` → result `{protocolVersion, capabilities:{tools:{listChanged:false}}, serverInfo:{name:"vibetrace", version}}`;收到 `notifications/initialized`(无 id)→ 不回。不实现 resources/prompts/sampling。

## Components / Interfaces
- `vibetrace/mcp_server.py`
  - `_handle(req, cache, cfg) -> response|None`:按 `req["method"]` 分发;notification(无 `id`)返回 `None`(不回)。
  - `initialize` → 上述 result。
  - `tools/list` → `{tools:[...]}`,每个 `{name, description, inputSchema(JSON Schema)}`:
    - `vibetrace_ask` {target: "file 或 file:line[-line]", question: str, project?: str}
    - `vibetrace_blame` {target: str, project?: str}
    - `vibetrace_graph` {project?: str}
  - `tools/call` → 取 `params.name`/`params.arguments`,dispatch 到适配函数,成功 `{content:[{type:"text", text:<闭包返回的 json/文本>}], isError:false}`;异常 → `{content:[{type:"text", text:错误}], isError:true}`(不抛出循环外)。
  - `serve(stdin=sys.stdin, stdout=sys.stdout)`:逐行读 → `json.loads`(失败回 JSON-RPC parse error `-32700`)→ `_handle` → 若有响应 `stdout.write(json.dumps(resp)+"\n"); flush`。EOF 退出。
  - 适配:复用 `Cache`/`load_config`/`LLMClient`(无 key→None,`ask` 降级)与现有 `answer_question` / blame collect+format / graph 装配;`project` 缺省取 cwd。
- `cli.py`:`_DISPATCH` 加 `"mcp-serve": commands.mcp_serve_cmd`;子命令解析加 `mcp-serve`(可选 `--project`)。
- `commands.py`:`mcp_serve_cmd(args)` → 装配 cache/cfg/llm → `mcp_server.serve()`;以 stderr 提示已启动。

## Testing(全部喂 JSON-RPC 帧给 `_handle`/`serve`,不依赖真实客户端)
- `initialize` → 返回含 `protocolVersion` 与 `capabilities.tools`;`notifications/initialized` → 返回 `None`。
- `tools/list` → 含三工具且各有 `inputSchema`。
- `tools/call` `vibetrace_ask`(用 mock 仓/mock answer_question)→ `content[0].text` 是闭包的 json 串、`isError:false`。
- **stdout 纯净**:跑一轮 initialize+list+call,断言 stdout 每行都是合法 JSON-RPC、无任何非 MCP 行(日志须在 stderr)。
- 容错:畸形 JSON 行 → parse error,循环继续;未知 method → method-not-found `-32601`;工具内部抛错 → `isError:true` 而非崩溃。

## 非目标
resources/prompts/sampling;HTTP/SSE 传输(只做 stdio);把 digest/course 这类长流程或写盘命令暴露成工具(只暴露零-LLM/读路径的 ask/blame/graph);MCP SDK 依赖。

---

## 评审修订(对抗审 wksn06gfj 后,这些覆盖上文冲突处)

**裁决:GO(首版 ask+blame+graph,以下 blocking 全部纳入)。**

1. **graph 无纯 JSON 闭包(blocking)** — `build_graph` 会写 HTML 到 vault。**前置任务**:在 `graph.py` 抽出 `build_graph_json(project_path, cache) -> (json_str | None, err)` 纯内存函数(内部 `collect_commit_files`→`commits[-SCAN_LIMIT:]` 截断→空仓兜底→`_assemble`→`json.dumps(ensure_ascii=False)`,**不写盘**),`build_graph` 与 MCP 工具共用它。MCP **绝不调** `build_graph`。
2. **blame/graph 出口未脱敏(blocking,隐私红线)** — 交给 MCP 客户端 = 出本机。MCP tools/call 适配层对**最终文本统一过 `redact_secrets`** 再放进 `content[0].text`(ask 已脱敏,重复幂等无害)。测试:blame 输出含 `sk-xxx` → content 内 `[REDACTED]`。
3. **tools/call 校验(blocking)** — 先校验 `name` ∈ {三工具}(否则 `isError:true` 注明未知工具)、`arguments` 为 dict 且必填键(ask 的 target/question)齐全(缺则 `isError:true` 友好文本),整段 dispatch 包 try→`isError:true`(覆盖参数层+业务层,绝不崩循环)。
4. **JSON-RPC id 透传(blocking)** — 所有 error/result 透传 `req.get("id")`;parse-error(拿不到请求体)id=`null`;notification(无 id)不回。
5. **protocolVersion 策略** — initialize **回显客户端 `params.protocolVersion`**,缺失则回服务端支持值 `"2025-11-25"`(已核实该修订真实存在)。不硬编码臆造值。
6. **编码/健壮性** — stdout 写 `json.dumps(..., ensure_ascii=False)`,serve 入口 `sys.stdout.reconfigure(encoding="utf-8")`(中文叙事);收到 JSON 数组(batch)→ `-32600`(明确不支持);`ping` → 回空 result;未知 method → `-32601`。
7. **入口** — `mcp_server.py` 末尾 `if __name__=="__main__"` 守卫 + cli `mcp-serve` 子命令**共用同一装配函数**(cache/cfg/llm→serve);经 `-m` 入口 server 自己 `logging.basicConfig(stream=sys.stderr)`(经 cli 入口已是 stderr)。
8. **参数面** — 只暴露 `{target, question, project?}`(ask)/`{target, project?}`(blame)/`{project?}`(graph);**不暴露 `vault`(会写笔记)**;`since` 后置不做。`project` `Path.resolve()` 后在 stderr 记一行审计;不做路径白名单(纯本地只读 + 出口脱敏兜底)。
9. **副作用如实记** — 工具调用复用既有 `append_usage` 往 `~/.vibetrace/usage.log` 追加(已脱敏),非"零副作用"。
10. **测试补** — `llm=None`(本机缺 key)时 `vibetrace_ask` 回 `isError:false` 且 text 为 degraded 检索结果、不 print 到 stdout;stdout 纯净(每行合法 JSON-RPC,日志在 stderr);未知 notification 不回。
