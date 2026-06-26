# 文件树「接地入口」· Phase B(web 主机)— 设计(spec)

日期:2026-06-26 · 来源:第五轮想法 2 / Phase A spec 末节锚定 · 分支 `feat/filetree-grounding-entry-phaseB-web`(off main)。Phase A(console 零-LLM 面板)已合入 main(PR #62)。
**修订(对抗审 spec 后,2026-06-26)**:19 条经真实代码核实的发现收口——**纠正「web.py 不可 CI 测」错误前提**(实测 fastapi 0.138.0/uvicorn 0.49.0 已装、`TestClient(web.app).get("/")`→200,故新增 index 集成测)、tree_payload 消重(console 复用)、键盘绑键拆分、空树守卫判 children、$ 不变量等。

## 目标(一句话)
让 `vibetrace web` 对话页(`web_chat.html`)也能用同一棵工作区文件树:点 `[文件 ▸]` 滑出折叠树,点变更文件 → 预填「这个文件当初为什么改」进对话框并带 `target` → 走已有 `/api/chat/stream` LLM 接地对话。

## 已定方向(brainstorm 决议,勿再翻)
- **抽屉式(drawer)**:对话保持全宽为主;`[文件 ▸]` 切换从侧边滑出同一棵树;选文件 → 填 `#q` + 收起抽屉 → 提交走 LLM。**不**在对话页常驻全树(`/console` 已常驻全量树 + 零-LLM 面板)。
- **web 端不需 grounding 索引**(点击走 LLM)。复用 Phase A `filetree.py`。树渲染 JS 在 web_chat.html **另放一份**(第 2 个 JS 消费者,按「第三处才抽」约定不抽象——该规则**仅**适用 console.html/web_chat.html 两份 JS 组件)。
- 后端 `ChatReq.target` 已支持(web.py:93)且真接地:web.py:133 `target=req.target` → chat.py:75 `retrieval.assemble(..., target=target)` → retrieval.py:45-47 `parse_target` 叠加行级溯源。缺的只是前端接线。

## 组件与边界

### `vibetrace/filetree.py`(现 89 行,加 tree_payload 后约 104,<300)— 可测装配 + 消重
- `tree_payload(project_path) -> dict`:返回 `{"nodes": build_tree(tracked | set(status_map), status_map), "status": st}`,其中 `tracked = gitlog.tracked_files(pp) or set()`(None 守卫)、`st = status(pp)`、`status_map = {s["path"]: s for s in st}`。纯 stdlib、零 LLM、不新增任何 import、只产纯 dict(`inline_json`/redact 都在 web.py 出口做)。git 失败 → status []/tracked set() → 仍产出合法(可能空根)树。**返回也含 `status` 列表**,供 console 复用以消除同构装配。

### `vibetrace/console.py`(消重,~125 行)— 改用 tree_payload(对抗审 DRY)
`_assemble` 现有的四步树装配(console.py:75-79:tracked/status/status_map/build_tree)与 tree_payload 一字不差。改为复用:
```
tp = filetree.tree_payload(pp)
data["tree"] = {"nodes": tp["nodes"],
                "grounding": _file_grounding([s["path"] for s in tp["status"]], commits, narratives)}
```
消除双份 Python 装配 + 省一次 `status()` git 子进程;且让 tree_payload 立获 console 既有 CI 测间接覆盖。`_file_grounding` 不变。

### `vibetrace/web.py`(217 行)— Template 化 + 按请求渲染(可 CI 测)
- `_CHAT_HTML`:`read_text()` 常量 → `Template(read_text())`(`from string import Template`)。
- `index(project: Optional[str] = None)`:按请求渲染——`pp = _project(project)` → `tree = filetree.tree_payload(pp)` → `html = _CHAT_HTML.substitute(tree_data=inline_json(redact_data(tree)))` → `HTMLResponse(redact_secrets(html))`(出口兜底脱敏,同 console._build_html 收口)。
- import 增 `from string import Template`、`from . import filetree`、`from .webserve import inline_json`(`redact_data`/`redact_secrets` 已 import)。CSP middleware / `/console` / `/tunnel` / `/api/*` 不动。

### `vibetrace/web_chat.html`(157 行)— 抽屉 + 树 + 点击接线
- **占位**:加 `var TREE = $tree_data;`。
- **$ 不变量**:web_chat.html 现已核实**无任何字面 `$`**(`grep -c "\$"`→0);Template 化后唯一合法占位 = `$tree_data`。落地约束:新增 drawer/树渲染 JS 一律字符串拼接(照搬 console.html nodeHtml 范式)、**禁 `${}`/反引号/正则 `$1`/`$&`/`$<`**,从源头不引入裸 `$`;落地后 `grep -c "\$" web_chat.html` 必须恰等于 1(=`$tree_data`)。**注**:`inline_json` 代入的 `tree_data` 值里的 `$`(文件名/标签)无需也不应预转义——`string.Template` 只扫模板正文不扫代入值(console.py `var DATA = $data` 生产先例已上线);数据安全由 `redact_data`+`redact_secrets` 负责,与 `$` 转义正交。
- **抽屉 UI**:`<main>` 顶部加 `<button id="filesbtn">文件 ▸</button>` + `<aside id="ftdrawer" hidden>`;`#filesbtn` 切 `#ftdrawer.hidden`。**(可选润色)** 若加滑出过渡,用 console.html 同款 `@media (prefers-reduced-motion: reduce){...}` 守卫;MVP 纯 `hidden` 切换即满足滑出/收起语义。
- **树渲染**:抽屉内渲染 `TREE.nodes` 折叠树,两步(对抗审强调勿合并):
  - **(a) 模板** `nodeHtml`:产 `role=button`/`tabindex=0`/`title`(tooltip)/状态三重(tooltip+颜色 class+徽章)/删除置灰(`node.code.indexOf("D")>=0`)。**安全语义拷贝**:`esc()` 转义不可省(`data-path`、name、label 全经 `esc`);若 web_chat.html 无 `esc()` 则照搬 console.html 的加一份。
  - **(b) 渲染后绑键循环**:对每个文件节点 `addEventListener("click")` + `addEventListener("keydown")`(`Enter`/`" "`→`preventDefault`→act),范式见 console.html 的 `querySelectorAll(".ftf").forEach`。键盘可达靠这步,**不能只拷 (a) 模板**。
- **点击接线(在 (b) 的 act() 内)**:`#q`.value = 「这个文件当初为什么改:」+path;`pendingTarget = path`;focus `#q`;收起抽屉。
- **fetch 带 target**:`#f` 提交 fetch body `{question, conv_id, turn_seq}` → 加 `target: pendingTarget`;**发送后 `pendingTarget = null`**(防下一条普通提问误带旧 target)。
- **空树守卫**:`var T = TREE && TREE.nodes; if (!T || !T.children || !T.children.length) { 抽屉显示「无文件或非 git 仓」 }`(判**根 dir 的 children 数组**,`build_tree` 恒返真值根,`!TREE.nodes` 对空仓永不触发)。

## 数据流
每 GET `/`:`filetree.tree_payload(pp)`(status+tracked+build_tree)→ `redact_data` → `inline_json` → `$tree_data` substitute → 出口 `redact_secrets` → 前端 `TREE` → 抽屉折叠树 → 点文件 → `#q`+`pendingTarget` → `#f` 提交 → `/api/chat/stream`(带 `target`)→ chat.answer_stream 接地。LLM 出网仍唯一例外、受 `no_llm`。
- **性能面包屑**:每 GET `/` 跑 2 次 git 子进程(`status` 的 git status + `tracked_files` 的 git ls-files),与 `/console` 同量级(实更少,/console 还跑 git log),可接受;若大仓/慢盘首页变慢再议按 last-commit-sha 缓存 tree_payload。

## 错误处理 / 红线
- `tree_payload` 容错:`status` git 失败→[]、`tracked_files` None→set();产出合法(可能空根)树,**绝不崩**;前端空树守卫(见上)。
- 注入前 `redact_data`(path 落 value 位故被脱)+ 出口 `redact_secrets` 兜底。
- web extra(FastAPI/uvicorn)允许;**惰性 import**:web.py 仅 `vibetrace web` 时按需 import,CLI/MCP 核心纯 stdlib 不变;`filetree.py` 纯 stdlib、不 import web/fastapi。
- 只绑 127.0.0.1(不动);CSP `connect-src 'self'`(不动);前端零外链 → 改后 `python3 -m scripts.check_static_no_external vibetrace/web_chat.html`;`filetree.py` <300。

## 测试(TDD · 三层全 CI 可测 + 真机 smoke)
**纠正前稿错误前提**:实测 fastapi 0.138.0/uvicorn 0.49.0 已装、`from vibetrace import web` 成功、`TestClient(web.app).get("/")`→200、全套 480 绿。故 web.py 渲染链(承载双层脱敏 + substitute 红线)**必须**入 CI,不再「真机 smoke 豁免」。
- **① `filetree.tree_payload()`**(`tests/test_filetree.py` 加 `TestTreePayload`):**建临时 git 仓 fixture**(沿用 test_console.py 的 `_git` 范式:init+改/增/删文件)为首选;或 `mock.patch.object(filetree.gitlog, "_git", side_effect=按命令分派 status/ls-files 输出)`(一处 `_git` 桩同覆盖 status+tracked_files;`mock filetree.status` 拦不住直调的 `gitlog.tracked_files`)。断言:返 `{"nodes","status"}`、nodes 是 dir、含变更文件;`tracked_files` 返 None(ls-files `side_effect=RuntimeError`)→ 不崩、树仅 status 路径。
- **② `web_chat.html` 标记**(新建 `tests/test_web_chat.py`,读 HTML 文本,**不导入 web.py/fastapi**):断言 `$tree_data` 占位出现且**恰一次**(等价校验「键集⟺占位集」,如 `assertEqual(html.count("$"), 1)`)、`id="filesbtn"`/`id="ftdrawer"`、`<details`、`role="button"`、**`addEventListener("keydown"`(防只拷模板漏绑键)**、`"Enter"`/`" "`、**`esc(` 出现在树渲染段 + `data-path="'+esc(` 模式**(防漏转义)、**空树守卫含 `.children.length`**、fetch body 含 `target`、**无 `${`**。
- **③ `web.py index` 集成**(新建 `tests/test_web_index.py`,`TestClient`):`TestClient(web.app).get("/")`→200、渲染后含 `var TREE`/树节点标记;**双层脱敏真生效**——注入含 secret 模式的合成 status path(经 mock `filetree.tree_payload` 返带 `sk-...`/`AKIA...` 的路径),断言出口 HTML 已 `[REDACTED]`、无原 secret。**注**:TestClient 会触发 `StarletteDeprecationWarning`(httpx,依赖噪音非本代码)——用 `warnings.catch_warnings()`+`simplefilter`(或 `assertWarns` 外隔离)保持测试输出 pristine。
- **真机 smoke(补充非替代)**:`pip install -e ".[web]"` → `vibetrace web` → `/` → `[文件▸]` 出树 → 点文件 → `#q` 预填 + 提交 → 观察 `/api/chat/stream` 带 target(连续两条、第二条普通提问 target=null 的 DOM 行为靠此手验,静态文本测试层不表达)。
- 全量 `python3 -m unittest discover -s tests` 绿;`filetree.py` <300。

## YAGNI / 非目标
- **采纳 tree_payload 消重**(console 复用),消除同构 Python 装配双份;`_file_grounding` 不动。
- 不抽象树渲染 JS 组件(console + web_chat = 2 消费者;第 3 处或两份漂移时再抽到 `vibetrace/static/filetree.js`,`<script src='/static/filetree.js'>` 同源不破 CSP)。
- web 不做零-LLM 面板(那是 `/console`);不做 diff 查看;不在对话页常驻全树;reduced-motion 过渡为可选润色非硬要求。

## Vibe-Watch(落地 commit 留痕)
- `esc()`/`nodeHtml` 现 4+ 份字节级拷贝(console.html/web_chat.html/tunnel.html/course.html);新增第 5 份(web_chat 树渲染)。第 3 个 JS 消费者或两份漂移时抽到 `vibetrace/static/filetree.js`。

## 开放问题
无(drawer 已定;CI 可测性已实证纠正;消重已采纳)。
