# 文件树「接地入口」· Phase B(web 主机)— 设计(spec)

日期:2026-06-26 · 来源:第五轮想法 2 / Phase A spec 末节锚定 · 分支 `feat/filetree-grounding-entry-phaseB-web`(off main)。Phase A(console 零-LLM 面板)已合入 main(PR #62)。

## 目标(一句话)
让 `vibetrace web` 对话页(`web_chat.html`)也能用同一棵工作区文件树:点 `[文件 ▸]` 滑出折叠树,点变更文件 → 预填「这个文件当初为什么改」进对话框并带 `target` → 走已有 `/api/chat/stream` LLM 接地对话。

## 已定方向(brainstorm 决议,勿再翻)
- **抽屉式(drawer)**:对话保持全宽为主;`[文件 ▸]` 切换从侧边滑出同一棵树;选文件 → 填 `#q` + 收起抽屉 → 提交走 LLM。**不**在对话页常驻全树(`/console` 已常驻全量树 + 零-LLM 面板,是浏览全树的去处)。
- **web 端不需 grounding 索引**(点击走 LLM,非零-LLM 面板)。
- 复用 Phase A 的 `filetree.py`(`status`/`build_tree`);树渲染 JS 在 web_chat.html **另放一份**(第 2 个消费者,按「第三处才抽」约定不抽象)。
- 后端 `ChatReq.target` 已支持(web.py:93/133),缺的是前端接线。

## 组件与边界

### `vibetrace/filetree.py`(97 行内)— 新增可测装配函数
gitlog/console 都不便复用现成装配(console 的在 `_assemble` 内、且耦合 grounding),故在 filetree 加一个小函数,**把"装配工作区树 payload"从 web.py 抽出来使其 CI 可测**(web.py 导入 fastapi,sandbox 跑不了):
- `tree_payload(project_path) -> dict`:返回 `{"nodes": build_tree(tracked | set(status_map), status_map)}`,其中 `tracked = gitlog.tracked_files(pp) or set()`(None 守卫)、`st = status(pp)`、`status_map = {s["path"]: s for s in st}`。纯 stdlib、零 LLM、git 失败时 `status`→[]/`tracked`→set() 仍产出合法(可能空)树。**只含 nodes,不含 grounding**(web 点击走 LLM)。

### `vibetrace/web.py`(218 行)— Template 化 + 按请求渲染
- `_CHAT_HTML`:由 import 期 `read_text()` 常量改为 `Template(read_text())`(import `from string import Template`)。
- `index(project: Optional[str] = None)`:改为按请求渲染——
  `pp = _project(project)` → `tree = filetree.tree_payload(pp)` → `html = _CHAT_HTML.substitute(tree_data=inline_json(redact_data(tree)))` → `HTMLResponse(redact_secrets(html))`(出口兜底脱敏,同 console._build_html 收口)。`index` 加 `project` 查询参(与 `/console`、`/tunnel` 一致)。
- import 增 `from . import filetree`、`from .webserve import inline_json`(`redact_data`/`redact_secrets` 已 import)。
- CSP middleware 不动(已 `connect-src 'self'`)。`/console`、`/tunnel`、各 `/api/*` 不动。

### `vibetrace/web_chat.html`(157 行)— 抽屉 + 树 + 点击接线
- **Template 占位**:加 `var TREE = $tree_data;`(顶部脚本)。
- **⚠ `$` 转义**:web_chat.html 一旦经 `Template.substitute` 渲染,其现有 JS/CSS 里**任何字面 `$` 都会破 substitute**。落地第一步:扫 web_chat.html 现存 `$` → 全部转义为 `$$`(或确认无);新加树渲染 JS 同禁 `${}` 模板字面量。
- **抽屉 UI**:`<main>` 顶部(对话标题处)加 `<button id="filesbtn">文件 ▸</button>`;加 `<aside id="ftdrawer" hidden>` 抽屉容器(CSS:侧边滑出、`hidden` 切换;`prefers-reduced-motion` 守卫过渡)。`#filesbtn` 切换 `#ftdrawer` 的 `hidden`。
- **树渲染**:抽屉内渲染 `TREE.nodes` 折叠树——复用 Phase A `renderFiletree` 的 `nodeHtml`/`<details open=changed>`/状态三重(tooltip+颜色 class+徽章)/删除置灰范式(各放一份)。文件节点 `role=button`、`tabindex=0`、Enter/Space + `preventDefault`。
- **点击接线**:点变更文件 → `document.getElementById("q").value = "这个文件当初为什么改:" + path`、`pendingTarget = path`、focus `#q`、收起抽屉(`#ftdrawer.hidden = true`)。
- **fetch 带 target**:`#f` 提交的 fetch body 由 `{question, conv_id, turn_seq}` 改为 `{question, conv_id, turn_seq, target: pendingTarget}`;发送后 `pendingTarget = null`(下一条普通提问不再误带旧 target)。
- 复用既有转义习惯(web_chat.html 若已有 `esc`/同等,沿用;否则按 console.html 的 `esc()` 加一份);所有动态值(path/name/label)经转义。

## 数据流(全脱敏到注入)
每请求:`filetree.tree_payload(pp)`(status+tracked+build_tree)→ `redact_data` → `inline_json` → `$tree_data` substitute → 前端 `TREE` → 抽屉折叠树 → 点文件 → `#q` 预填 + `pendingTarget` → `#f` 提交 → `/api/chat/stream`(带 `target`)→ 已有 chat.answer_stream 接地。LLM 出网仍是唯一例外、受 `no_llm` 硬开关。

## 错误处理 / 红线
- `tree_payload`:`status` git 失败 → []、`tracked_files` None → set();产出合法(可能空)树,**绝不崩**。web_chat 前端 `!TREE || !TREE.nodes...` 守卫空树(抽屉显示「无文件或非 git 仓」)。
- 注入前 `redact_data`(path 落 value 位故被脱敏)+ 出口 `redact_secrets` 兜底(同 console)。
- web extra(FastAPI/uvicorn)允许;**惰性 import**:web.py 仍只在 `vibetrace web` 时按需 import,CLI/MCP 核心纯 stdlib 不变;`filetree.py` 纯 stdlib(不 import web 任何东西)。
- 只绑 127.0.0.1(serve 不暴露 --host,不动);CSP `connect-src 'self'` 不动;前端零外链 → 改后跑 `python3 -m scripts.check_static_no_external vibetrace/web_chat.html`;禁 `${}`;`filetree.py` <300。

## 测试(TDD)
**约束:web.py 导入 fastapi/uvicorn,sandbox/CI 跑不了**(web.py 现有 docstring 已声明「未在 CI 跑通,需真机 smoke test」;`/console`、`/tunnel` 同此惯例)。因此分两层:
- **CI 可测(纯 stdlib)**:`filetree.tree_payload()` 在 `tests/test_filetree.py` 加 `TestTreePayload`——合成 git 仓 fixture(同 test_console.py 的 `_git` 范式建临时仓 + 改/增文件)或 mock `filetree.status`/`gitlog.tracked_files`:断言返回 `{"nodes": {...}}`、nodes 是 dir、含变更文件、`tracked_files` 返 None 不崩(树仅 status 路径)。
- **CI 可测(HTML 文本标记)**:新建 `tests/test_web_chat.py`(读 `web_chat.html` 文本,不导入 web.py/fastapi):断言 `$tree_data` 占位存在、`id="filesbtn"`/`id="ftdrawer"`、树渲染函数(`<details`、`role="button"`、`"Enter"`、`" "`)、fetch body 含 `target`、**无 `${`** 模板字面量、无未转义裸 `$`(除 `$tree_data` 占位本身)。
- **真机 smoke(不入 CI)**:`pip install -e ".[web]"` → `vibetrace web` → 开 `/` → `[文件 ▸]` 出树 → 点文件 → `#q` 预填 + 提交 → curl/观察 `/api/chat/stream` 带 target。延续 web.py 既有 smoke 惯例。
- 全量 `python3 -m unittest discover -s tests` 绿(新增 filetree + web_chat 测试不依赖 fastapi);`filetree.py` <300。

## YAGNI / 非目标
- 不动 console(Phase A 已合;不为复用重构其 `_assemble`)。
- web 不做零-LLM 面板(那是 `/console`);抽屉点击只走 LLM。
- 不抽象树渲染组件(console + web_chat = 2 消费者,按约定各放一份;第 3 处再抽)。
- 不为 web.py 的 Template 胶水强加 CI 测(fastapi 不在 sandbox;靠 tree_payload 单测 + web_chat 标记测 + 真机 smoke 覆盖)。
- 不做 diff 查看 / 不在对话页常驻全树。

## 开放问题
无(brainstorm 已定 drawer;其余从 Phase A 锚定继承)。
