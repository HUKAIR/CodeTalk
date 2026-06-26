# 文件树「接地入口」视图 — 设计(spec)

日期:2026-06-25 · 来源:第五轮外部对标想法 2 · 分支 `feat/filetree-grounding-entry`(off main)。
**修订(对抗审 spec 后,2026-06-25)**:据 4 视角对真实代码核实的 29 条发现收口——拆 PR、补 `-uall`、None 守卫、grounding 改列表、porcelain 有状态解析、删除文件策略等(详见各节)。

## 目标(一句话)
在 vibetrace web 视图里加一棵项目文件树,用 `git status` 确定性高亮工作区新增/修改/未跟踪文件,**点变更文件 → 接地它的「当初为什么」**。定位为**通往 why 接地的导航入口**,不是 diff 查看器。

## 已定方向(brainstorm 决议,勿再翻)
- **高亮口径 = 工作区 `git status --porcelain`**(未提交的新增/修改/未跟踪/暂存/删除),不是历史窗口。
- **两个主机**:console(stdlib/`webserve`,零-LLM 历史面板)+ `vibetrace web`(FastAPI,LLM 接地对话),共享同一棵折叠树。
- **树可折叠**:默认折叠无变更后代的目录,自动展开通往变更文件的路径。
- **面板放右侧**:console 中树在左、零-LLM 接地面板在右(master/detail)。
- **可访问性**:状态用三重(人话 tooltip + 颜色 + 非颜色标记),绝不只靠颜色或只靠单字母(借 VS Code#123103 教训)。

## 拆 PR(对抗审 spec 决议)
web 主机不是「复用已有」——`web_chat.html` 无任何注入管线(`web.py:35` import 期 `read_text()` 读死、`index()` 原样吐出),且 `openChatWith` 仅存于 console.html(签名 `(sha,subject)`、commit 取向),web 端需**新写**文件点击处理器 + 给 web_chat.html 补 `string.Template` 注入管线 + 前端 fetch 接 `target`。故:
- **PR1 / Phase A(本 spec + 本期 plan)= console 文件树(零-LLM、纯 stdlib、离线可测,不碰 `.[web]`)。**
- **PR2 / Phase B(另起 spec)= web 文件树**:先补 web_chat.html 注入管线 + `target` 接线,再谈树渲染。本 spec 末节只锚定其范围,不展开详细设计。

---

# Phase A:console 文件树(本期实现)

## 组件与边界

### 新模块 `vibetrace/filetree.py`(~90 行,纯 stdlib)
gitlog.py 已 267 行近红线,且「工作区状态 + 树结构」与「历史」是不同关注点,故新建。

- `status(project_path) -> list[dict]`
  - 跑 `git -c core.quotepath=false status --porcelain=v1 -z --untracked-files=all`。**`-uall` 必加**:否则 git 把未跟踪目录折叠成单条 `?? newdir/`(尾斜杠),其内新增文件既不在 status 段又不在 `tracked_files`(`git ls-files` 只列已跟踪)→ 树里完全不可见,直接破坏「新增文件高亮」核心目标。
  - **有状态解析 NUL 段**(参照 gitlog.py:91/97/104 既有 `-z` 防御):按位置迭代;每段前 2 字符为 XY code、第 4 字符起为 path;**当 X∈{R,C}(重命名/复制)时,把紧跟的下一段作为 old/orig-path 一并消费(不单独成项),path 取当前段(new)**;显式跳过空段(`-z` 末尾终止符产生的 `''`);防御性丢弃任何以 `/` 结尾的条目(加 `-uall` 后不应出现,belt-and-suspenders)。
  - 返回 `[{"path": str(repo 相对), "code": str(2字符 XY), "label": str(人话)}]`。
  - **git 失败 / 非 git 仓 → 返回 `[]`**(降级,绝不崩)。
- `STATUS_LABELS` + `label(code)`:确定性映射。用**优先级总序 `U>D>R>C>A>M>?`**:取 XY 两位中映射优先级更高者定主 label(`"??"→未跟踪`、`D→已删除`、`R→重命名`、`C→复制`、`A→新增`、`M→已修改`、`U→冲突`);`X` 非空格(已暂存)时加「已暂存·」前缀,且仅当主 label 来源对应 X 语义,避免 `MD→「已暂存·已删除」`误标。未知 code → 原样 code 作 label(不崩)。组合码(`MM/MD/AM/AD/RM`)各有确定输出。
- `build_tree(paths, status_map) -> dict`(**纯函数**,不碰 git、不触磁盘)
  - `paths`:repo 相对路径可迭代;`status_map`:`{path: {"code","label"}}`。
  - 返回嵌套:`{"name":"", "type":"dir", "children":[...]}`;dir 节点 `{"name","type":"dir","changed":bool,"children":[...]}`;file 节点 `{"name","type":"file","path","code"?,"label"?}`。
  - `changed`(目录)= 任一**后代**有 status(向所有祖先冒泡),供前端默认折叠/自动展开。
  - 排序:目录在前、各自按名字典序;稳定、确定。空输入 → 空根。

### `vibetrace/console.py`(99 行 → 预估 ~155-165 行,<300)
- import 清单补 `from . import filetree`。
- 新增 `_file_grounding(changed_paths, commits, narratives) -> list`(**纯函数,可单测**):
  - `commits` = `_assemble` 已构建的 `collect_commit_files(pp)` 全史输出(每 commit 含 `files`/`sha`/`subject`/`date`)。
  - `narratives` = `_assemble` 已在 console.py:33 构建的 `{sha: get_narrative(sha)}` 子集——**不二次查 DB**:`relevant = {c["sha"] for c in commits if set(c["files"]) & set(changed_paths)}`,再 `{sha: narratives[sha] for sha in relevant}`。
  - 返回**列表**(非 dict,见下脱敏修正):`[{"path": p, "commits": [{"sha","subject","date","decisions":[...],"sources":[{"type":"commit","sha":...}]}]}]`,**只为 changed_paths 构建**(有界=你刚改的少数文件)。`decisions` 取该 SHA narrative 的 `decisions` 字段(确为 narrative 字段);`sources` 由 `_file_grounding` 据 SHA **确定性合成** `[{"type":"commit","sha":...}]`(SHA 永远可给,无叙事亦可)——**注意 `sources` 不是 narrative 字段**(narrative 只有 what/why/decisions/risks/open_loops/evidence/test_refs/pr_refs/degraded),勿读 `narrative["sources"]`。
- `_assemble()` 增 `data["tree"] = {"nodes": build_tree(paths, status_map), "grounding": _file_grounding(...)}`:
  - `tracked = gitlog.tracked_files(pp) or set()`(**None 守卫**:tracked_files 在 git 失败/非 git 仓返 `None` 非 `[]`,`None | set()` 会 TypeError;`or set()` 对齐 debt.py:51 范式)。
  - `st = filetree.status(pp)`;`paths = tracked | {s["path"] for s in st}`(**统一口径:含全部 status,含删除 D**)。
  - 经已有 `redact_data(...)` + `inline_json(...)` 注入(隐私收口复用)。**grounding 用列表(path 在 value 位)**:`redact_data` 对 dict 只递归 value、不脱 key(config.py:100),若 `{path:[...]}` 则路径键不脱敏 → 违「注入前脱敏」。

### `vibetrace/console.html`(656 行)— 文件树视图(树左 / 面板右)
第 5 个视图,机械接入 3 处(`buildNav()`/`show()` 由 VIEWS 数组驱动自动覆盖,无需手改;CSS:145-149 作用域限 `#v-overview`,新视图不受影响):
1. VIEWS 数组(console.html:260)加 `["filetree","文件树"]`;
2. `<main>` 内加 `<section class="view" id="v-filetree" role="tabpanel" tabindex="0">`;
3. 底部渲染链(653)加 `renderFiletree()` 调用并定义。
- 左:折叠树(渲染 `DATA.tree.nodes`)。目录可点开/收起,**默认折叠 `changed=false` 的目录、自动展开通往变更文件的路径**。文件节点状态:人话 tooltip(hover 出 label)+ 颜色 class + 非颜色标记(label 首字/符号)。**删除文件**:仍进树、`已删除` label + 置灰呈现、点击仍可接地。
- 右:接地面板。点文件 → 按 path 在 `DATA.tree.grounding`(列表)查 entry → 列其 commit(SHA+subject+日期,SHA 可点开核验)+ 有叙事处的 decisions;无记录(未提交/无历史/删除)→「暂无叙事」降级提示 + 一行「更深:`vibetrace blame <path>`」。**全零-LLM,静态(file://)也能用。**
- 复用已有 `esc()` 转义;**不得用 `${}` 模板字面量**(与 `$`-Template 冲突)。

## 数据流(全零-LLM)
`tracked_files() or set()` ∪ `status()` 路径 → `build_tree()` + `_file_grounding()`(吃 _assemble 已构建的 commits/narratives 子集)→ `redact_data` + `inline_json` 注入 → 前端渲染。`status()`/`collect_commit_files()` 是 git 读、其余纯映射,**无 LLM**。
- **console serve 走快照非 builder**:`console.py:99 serve_html` 仅 3 参(builder 默认 None)→ 走 `_build_html` 装配的 HTML 快照,`status()`/`tracked_files()`/`collect_commit_files()` 只装配时各跑一次、刷新不重跑、大仓无每请求放大;`status()` 复用 `gitlog._git` 的 `timeout=60` 防卡(区别于 briefing.py:271 传 builder 每请求重建)。

## 错误处理 / 红线
- `status()` git 失败/非 git 仓 → `[]`;`tracked_files()` → `None` 经 `or set()` 兜底 → 树仍渲染(仅 status 路径或无高亮),**两条降级路径都不崩**(M0 容错红线)。
- `build_tree` 纯路径构造、不触磁盘 → 删除/幽灵路径不崩;点击删除节点给降级提示而非死链。
- 路径经 `redact_data` 脱敏后注入:**path 中 key/token 形态段(sk-*/AKIA*/keyword=value)会被脱**;纯敏感目录名(无 secret 形态,如 `customer-acme/`)按项目既有口径(脱值非脱任意路径)不脱——已知边界、非本视图新增风险。
- 仅 stdlib(`subprocess`/`json`);`filetree.py`、`console.py` 均 <300。
- **CSP 按主机分面**:`connect-src 'self'` 仅在 `vibetrace web`(FastAPI middleware web.py:38-46)生效;console 静态(file://)与 `console --serve`(webserve.py 不设 CSP)面靠「树面板零-LLM、零 fetch、吃预注入 DATA」+ `scripts/check_static_no_external.py` 扫无外链守「不 phone home」。改动后跑该扫描。

## 测试(TDD)
- `filetree.status()`(合成 porcelain `-z` 输出,不依赖真实 git):`M `/` M`/`MM`/`A `/`??`/`D `/` D`/重命名 `R` 双段/复制 `C` 双段 → 正确解析;**新建目录含多文件**(`-uall`)→ 逐文件项、非折叠目录;裸 old-path 不被错解析成 code、空段被跳、尾斜杠条目被丢;git 失败 → `[]`。
- `filetree.label()`:`MM/MD/AM/AD/RM` 各断言确定 label(优先级总序)。
- `filetree.build_tree()`:纯函数。合成 paths+status_map → 嵌套正确、目录 `changed` 向祖先冒泡正确、排序确定、空输入边界;删除文件节点存在 + label 正确;**合成大 paths(~5k)** 断言线性可控、结构/排序/冒泡正确。
- `console._file_grounding()`:合成 commits+narratives → 每 changed path 的 commit 列表 + decisions + 合成 sources 正确;无叙事 SHA 只给 sha/subject/date;非 changed 文件不出现(有界);不二次查 DB(吃传入 narratives)。
- `console._assemble()`:mock `tracked_files` 返 `None` → 不抛、树仅含 status 路径。
- **改既有测试**:`tests/test_console.py:44 test_assemble_has_four_views` → 改名 `*_includes_tree`,断言扩为含 `"tree"` 键(或 `assertIn("tree", data)`)+ `data["tree"]` 含 `nodes`/`grounding`。其余 console 测试(test_renders_views_and_redacts 等断言稳定标记)不受新 section 影响、无需改。
- console.html:沿用 test_console.py 范式,断言注入 `data.tree.nodes`/`grounding` + 关键 DOM 标记(树容器、右面板、状态 tooltip)。
- 全量 `python3 -m unittest discover -s tests` 绿;各 Python 模块 `wc -l` <300。

## YAGNI / 非目标
- 不做全树逐文件 LLM 预热;console 深层 why 交给已有 `blame` CLI,不在面板重造。
- 不新增 REST 端点(数据渲染时预注入;console 走 stdlib `webserve` 不加路由)。
- 不抽象共享树组件(Phase A 仅 console 一个消费者;Phase B web 再看是否抽,「第三处才抽」)。
- 不做 diff 内容查看(纯 what 撞 GitLens/DeepWiki、off-mission)。
- **`_file_grounding` 必要、非 over-build**:已注入的 timeline(`tunnel._payload` 不透传 files)、graph(commit-keyed+SHA7+仅 ranked 子集、节点无文件字段)均无 file→commit 倒排,前端无法客户端复用;此索引只为 changed_paths 构建(有界),Phase B web 端不需它(点击走 LLM)。**勿在 plan 里当冗余砍掉。**
- **全树保留**(非收窄为仅变更文件):导航需周边上下文定位变更,且本仓全树 payload 仅 ~13KB(180 文件);`changed` 冒泡与默认折叠 UX 无论如何都保留。

## 开放问题 / Vibe-Watch
- **大仓规模退化**:全 tracked 整棵 inline_json 注入无上界(本仓 ~23KB;线性外推 1k≈129KB、5k≈0.6MB)。远超单人本地仓尾部才有压力,与既有全量注入惯例同类。`Vibe-Watch`:超 N 文件时退化为「仅注入含变更子树 + 其祖先路径,其余懒展开」——本期不做,留观察。

---

# Phase B:web 文件树(另起 spec,本期不实现)
锚定范围供 PR2:① `web.py` 把 `_CHAT_HTML` 改 `string.Template`、`index()` 按请求渲染(加 `project` 参 → `filetree.status`+`build_tree` → `redact_data` → `inline_json` → `.substitute()`,**web 注入同走脱敏单点收口**)、web_chat.html 加 `$tree_data` 占位 + DATA 变量;② web_chat.html **新写**文件点击处理器(把「这个文件当初为什么改」填进 `#q` textarea 并触发 `#f` 提交——与 console 的 `openChatWith(sha,subject)` commit 取向是两套不同语义);③ fetch body(web_chat.html:130-131)新增 `target: path` 字段(后端 web.py:93/133 `ChatReq.target` 已支持,无需改后端);④ web_chat 变 Template 后,新加树渲染 JS 里任何字面 `$` 都会破 `.substitute()`,同 console 禁 `${}`。web 端**不需** grounding 索引(点击走 LLM)。
