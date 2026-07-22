# CodeTalk MCP 构建、安装与验证指南

把 CodeTalk 的零-LLM 接地能力(`ask`/`blame`/`graph`/`search`/`drift`/`prompts`/`adr`)装进 Claude Desktop /
Claude Code / Cursor 等 MCP 客户端,在 agent 工作流里直接问「这段代码当初为什么这么写」。
MCP transport 使用同机 stdio。只有显式启用 LLM 并调用 `ask` 综合时,脱敏后的接地材料
才会发给所配置的模型 provider;设置 `CODETALK_NO_LLM=1` 可保证零出网。

> 各步骤下方斜体「预期界面」描述你装好后应看到什么;可选截图素材规范见
> [`docs/images/README.md`](images/README.md)。

---

## 0. 前置条件

- `python3 ≥ 3.11` 在 PATH 上(`blame`/`graph`/`search` 只需这个,零 LLM、不出网)。
- 已 `pip install -e .` 过本仓 —— **JSON 配置方式需要**;`.mcpb` 拖拽方式**不需要**(包内自带源)。
- 想用 `ask` 的 LLM 综合:跑过 `codetalk init` 配好 key(不配也行,`ask` 自动降级为确定性检索)。

## 1. 构建包

```bash
cd ~/Github/CodeTalk
python3 -m scripts.build_mcpb        # → 生成 dist/codetalk-0.3.0.mcpb
```

## 2.(推荐)命令行自检,先确认包本身没问题

```bash
vt="$(mktemp -d "${TMPDIR:-/tmp}/codetalk-mcp.XXXXXX")"
unzip -q dist/codetalk-0.3.0.mcpb -d "$vt"
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
 | PYTHONPATH="$vt/server" python3 -P -m codetalk mcp-serve --project ~/Github/CodeTalk
```

**通过标准**:输出两行 JSON —— 第一行含 `"serverInfo":{"name":"codetalk"}`,第二行含 7 个
`codetalk_*` 工具。看到 = 包 OK,可进客户端。(`-P` 屏蔽当前目录,保证用的是包内源。)

## 3. 装进客户端(按你用哪个选一条)

### A. Claude Desktop —— `.mcpb` 主场,拖拽即装

1. 打开 Claude Desktop → **Settings(设置)→ Extensions(扩展)**
2. 点 **Install Extension…** 选 `codetalk-0.3.0.mcpb`,或直接把文件拖进窗口
3. 安装界面会要一个 **项目路径(project)** → 填某个 git 仓根目录(如 `~/Github/你的项目`)
4. 开启扩展 → 新建对话,工具列表里应出现 7 个 `codetalk_*`

_（预期界面:Claude Desktop → Settings → Extensions:安装 codetalk-0.3.0.mcpb,填 project 路径,启用后 7 个工具出现）_

### B. Claude Code —— 用 JSON 配置(不吃 `.mcpb` 拖拽)

仓根放 `.mcp.json`:

```json
{
  "mcpServers": {
    "CodeTalk": {
      "command": "python3",
      "args": ["-m", "codetalk", "mcp-serve", "--project", "/abs/path/to/your/repo"]
    }
  }
}
```

或一行命令:

```bash
claude mcp add CodeTalk -- python3 -m codetalk mcp-serve --project /abs/path/to/your/repo
```

_（预期界面:Claude Code:.mcp.json 配置 + claude mcp list 显示 CodeTalk connected）_

### C. Cursor —— `~/.cursor/mcp.json`(全局)或 `.cursor/mcp.json`(项目)

```json
{
  "mcpServers": {
    "CodeTalk": {
      "command": "python3",
      "args": ["-m", "codetalk", "mcp-serve", "--project", "/abs/path/to/your/repo"]
    }
  }
}
```

_（预期界面:Cursor Settings → MCP:CodeTalk 已连接、显示工具数）_

> ⚠️ **关键坑(B/C 用 JSON 时)**:客户端用自己的环境启动子进程,`python3` 可能解析到
> **没装 CodeTalk 的那个解释器**。稳妥做法:`which python3`(或装 CodeTalk 的那个
> venv/conda 的 python),把 `"command"` 换成**绝对路径**,例如
> `"command": "/opt/homebrew/Caskroom/miniconda/base/bin/python3"`。所有路径都用绝对路径。

## 4. 确认真能用(装好后,在 agent 对话里)

- 让它**列出工具** → 7 个 `codetalk_*` 在。
- `codetalk_blame`,target 填 `codetalk/llm.py:27-33` → 返回触达这些行的 commit + 决策史(**零 LLM**)。
- `codetalk_search`,关键词 ≥3 字(如「脱敏」)→ 相关 commit 的真实 why / 原话锚点。
- `codetalk_ask` 问「这段为什么这么写」→ 接地回答(配了 key 才有 LLM 综合,否则确定性检索)。
- 有真实内容 = 端到端通。

_（预期界面:agent 实际调用 codetalk_blame / codetalk_ask 的接地返回）_

## 5.(可选)零-egress 硬开关

要保证连 `ask` 都不调云端 LLM、数据一点不出本机:

- **MCP 场景**(mcp-serve 不吃 `--no-llm` flag,用环境变量或 config):
  - 在 step B/C 的服务器配置里加 `env` 块:
    ```json
    "CodeTalk": {
      "command": "python3",
      "args": ["-m", "codetalk", "mcp-serve", "--project", "/abs/path/to/your/repo"],
      "env": { "CODETALK_NO_LLM": "1" }
    }
    ```
  - 或在 `~/.codetalk/config.json` 设 `"no_llm": true`(对所有命令 + MCP 全局持久生效)。
- **CLI 场景**:`codetalk digest/ask/course --no-llm`。
- 开启后:`blame`/`graph`/`search` 照常;`ask` 降级为确定性检索、**零网络**;`digest` 因必须用
  LLM 而直接退出并提示原因。

## 6. 排错

| 现象 | 多半原因 | 处理 |
|---|---|---|
| 工具不出现 / server 起不来 | `python3` 不是装了 CodeTalk 的那个,或不在客户端 PATH | 用绝对路径 python(见 step 3 坑) |
| `ask` 说「材料不足」/ 没综合 | 没配 key,或该文件无 commit 历史 | 用 blame/graph/search(不需 key),或 `codetalk init` 配 key |
| `blame`/`ask` 说没有提交历史 | `--project` 不是 git 仓 / 路径错 | 填正确的 git 仓绝对路径 |
| 想看失败原因 | server 日志全在 stderr | 看客户端的 MCP 日志面板 |

---

## 附:工具速查(7 个)

| 工具 | 作用 | LLM |
|---|---|---|
| `codetalk_ask` | 就一段代码接地提问「当初为什么这么写」 | 配 key 用云端 LLM 综合;无 key 降级确定性 |
| `codetalk_blame` | 行级决策溯源(罗列触达这些行的 commit + 决策史) | 零 LLM |
| `codetalk_graph` | 决策影响图(哪个决策 commit 波及后续改动) | 零 LLM |
| `codetalk_search` | 主题级「当初为什么」召回(全项目按关键词找真实 why) | 零 LLM |
| `codetalk_drift` | 偏差自检:AI 工具改了但没提交的文件(「说了没做」检测) | 零 LLM |
| `codetalk_prompts` | 指令回看:你给 AI 下了什么指令 + 软对齐 commit | 零 LLM |
| `codetalk_adr` | ADR 导出:从真实 git 历史自动生成架构决策记录(MADR/Nygard/CycloneDX) | 零 LLM |

> 📌 所有 7 个工具都标注了 `readOnlyHint: true`——Claude Code / Cursor 可自动批准,不弹确认。

> 📌 仓根的 `.mcp.json` 是本地开发用便利配置(含硬编码路径),不是模板。
> 如需复制配置到你自己的项目,请用 **`.mcp.json.example`** 作为起点。

---

## 另一种集成:IDE 扩展(VS Code / Cursor / Windsurf)

MCP 是在 agent 对话里用 CodeTalk;如果你想在编辑器里**直接看到可折叠 CodeLens**
(hover 一行就看到 why / decisions / rejected / risks),可以装 VS Code 扩展:

```bash
cd vscode-codetalk && npm install && npm run build
npm run package
cursor --install-extension vscode-codetalk-0.3.0.vsix
```

详见 **[`vscode-codetalk/README.md`](../vscode-codetalk/README.md)**。两者互补:
MCP 给 agent 用(问答式)、IDE 扩展给你自己用(浏览式)。
