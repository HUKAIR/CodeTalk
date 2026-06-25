# 文件树「接地入口」视图 — 设计(spec)

日期:2026-06-25 · 来源:第五轮外部对标想法 2(`docs/discovery/2026-06-25-外部对标-第五轮.md`)· 分支 `feat/filetree-grounding-entry`(off main)。

## 目标(一句话)
在 vibetrace web 视图里加一棵项目文件树,用 `git status` 确定性高亮工作区新增/修改/未跟踪文件,**点变更文件 → 接地它的「当初为什么」**——console 给零-LLM 决策历史面板,`vibetrace web` 给 LLM 接地对话。定位为**通往 why 接地的导航入口**,不是 diff 查看器。

## 已定方向(brainstorm 决议,勿再翻)
- **高亮口径 = 工作区 `git status --porcelain`**(未提交的新增/修改/未跟踪/暂存),不是历史窗口。
- **两个主机**:console(stdlib/`webserve`,零-LLM 历史面板)+ `vibetrace web`(FastAPI,LLM 接地对话),**共享同一棵树**。
- **树可折叠**:默认折叠无变更后代的目录,自动展开通往变更文件的路径(让变更立即可见)。
- **面板放右侧**:console 中树在左、零-LLM 接地面板在右(master/detail)。
- **可访问性**:状态用三重(人话 tooltip + 颜色 + 非颜色标记),绝不只靠颜色或只靠单字母(借 VS Code#123103 教训)。
- **红线**:仅 stdlib;单模块 <300;数据不出本机、落盘前脱敏;容错降级绝不崩;零-build 单文件 vanilla-JS;CSP `connect-src 'self'`;过 `scripts/check_static_no_external.py`。

## 架构与组件

### 新模块 `vibetrace/filetree.py`(~80 行,纯 stdlib)
gitlog.py 已 267 行近红线,且「工作区状态 + 树结构」是与「历史」不同的关注点,故新建。两个核心函数 + 一个标签映射:

- `status(project_path) -> list[dict]`
  - 跑 `git -c core.quotepath=false status --porcelain=v1 -z`(复用 gitlog 的 git 调用范式;`-z` 用 NUL 分隔避免空格/换行路径问题)。
  - 返回 `[{"path": str(repo 相对), "code": str(2字符 XY), "label": str(人话)}]`。
  - 重命名:porcelain `-z` 下 `R` 项是「new\0old」两段,取 new 为 path、code 记 `R`。
  - **git 失败 / 非 git 仓 → 返回 `[]`**(降级,绝不崩;M0 容错红线)。
- `STATUS_LABELS`:code → 人话标签的确定性映射。取 X/Y 中更显著者:`"??"→未跟踪`、`"A"→新增`、`"M"→已修改`、`"D"→已删除`、`"R"→重命名`、`"C"→复制`、`"U"→冲突`;暂存态(X 非空格)前缀「已暂存·」。未知 code → 原样 code 作 label(不崩)。
- `build_tree(paths, status_map) -> dict`(**纯函数**,不碰 git)
  - `paths`:repo 相对路径可迭代(跟踪文件 ∪ status 里的未跟踪项)。
  - `status_map`:`{path: {"code","label"}}`。
  - 返回嵌套:`{"name":"", "type":"dir", "children":[...]}`;dir 节点 `{"name","type":"dir","changed":bool,"children":[...]}`,file 节点 `{"name","type":"file","path","code"?,"label"?}`。
  - `changed`(目录)= 任一后代有 status(供前端默认折叠/展开)。
  - 排序:目录在前、各自按名字典序;稳定、确定。

### `vibetrace/console.py`(99 行,有空间)— 零-LLM 接地历史 + 注入
- 新增 `_file_grounding(changed_paths, commits, narratives) -> dict`(**纯函数,可单测**):
  - `commits`:`gitlog.collect_commit_files(pp)` 的全史输出(只含文件清单,廉价、零 diff)。
  - `narratives`:`{sha: narrative_dict}`(调用方从 cache 取,仅取相关 SHA)。
  - 返回 `{path: [{"sha","subject","date","decisions":[...],"sources":[{"sha":...}]}]}`,**只为 changed_paths 构建**(=你刚改的少数文件,有界)。`decisions`/`sources` 来自该 SHA 的 narrative(无叙事则只给 sha+subject+date,SHA 引用永远可给)。
- `_assemble()` 增 `data["tree"] = {"nodes": build_tree(...), "grounding": _file_grounding(...)}`:
  - `tracked = gitlog.tracked_files(pp)`;`st = filetree.status(pp)`;`paths = tracked ∪ {s.path for s in st}`;`status_map` 由 st 派生。
  - changed_paths = `[s["path"] for s in st]`;为其 commit 的 SHA 批量 `cache.get_narrative`。
  - 经已有 `redact_data(...)` + `inline_json(...)` 注入(隐私红线复用单点收口)。

### `vibetrace/console.html`(656 行)— 文件树视图(树左 / 面板右)
- 加第 5 个视图「文件树」(与开工概览/时光轴/决策图/理解债并列)。
- 左:折叠树。渲染 `DATA.tree.nodes`;目录可点开/收起,**默认折叠 `changed=false` 的目录、自动展开通往变更文件的路径**。文件节点状态:人话 tooltip(hover 出 label)+ 颜色 class + 一个非颜色标记(label 首字/符号)。
- 右:接地面板。点文件 → 读 `DATA.tree.grounding[path]`,列其 commit(SHA+subject+日期,SHA 可点开核验)+ 有叙事处的 why/决策;无记录 → 「暂无叙事(尚未提交或无历史)」;并给一行「更深:`vibetrace blame <path>`」。**全零-LLM,静态(file://)也能用。**
- 复用已有 `esc()` 转义;不得用 `${}` 模板字面量(与 `$`-Template 冲突)。

### `vibetrace/web.py` + `vibetrace/web_chat.html`(LLM 主机)
- `web.py`:渲染 web_chat 时注入 `tree`(同 `filetree.status`+`build_tree`;**web 端不需 grounding 索引**,点击走 LLM)。
- `web_chat.html`:同一棵折叠树渲染逻辑;点文件 → 复用已有 `openChatWith(path, '这个文件')` 预填「这个文件当初为什么改」→ 已有 `/api/chat/stream`(`target=path`)。
- **树渲染 JS 在 console.html / web_chat.html 各放一份**(2 个消费者,按项目「第三处消费者才抽」约定**不**抽象;点击处理各自不同:console→右面板,web→openChatWith)。

## 数据流(全零-LLM 到渲染)
`tracked_files()` ∪ `status()` 未跟踪项 → `build_tree()` →(console 另加 `_file_grounding()`)→ `redact_data` + `inline_json` 注入 HTML → 前端渲染。`status()`/`collect_commit_files()` 是 git 读、`_file_grounding` 是纯映射,**无 LLM**。

## 错误处理 / 红线
- `git status` 失败或非 git 仓 → `status()` 返回 `[]` → 树仍渲染(无高亮)或不显示树,**不崩**。
- 路径经 `redact_data` 脱敏后才注入(虽路径含 secret 罕见,统一走收口)。
- 仅 stdlib(`subprocess`/`json`);`filetree.py`、`console.py` 均 <300。
- 前端零外链;改动后跑 `python3 -m scripts.check_static_no_external`。

## 测试(TDD)
- `filetree.status()`:合成 porcelain `-z` 输出 → 正确解析 `M `/` M`/`MM`/`A `/`??`/`D `/重命名 `R` 双段;git 失败 → `[]`。
- `filetree.build_tree()`:纯函数。合成 paths+status_map → 嵌套结构正确、目录 `changed` 标志正确(含祖先冒泡)、排序确定、空输入边界。
- `console._file_grounding()`:合成 commits + narratives → 每个 changed path 的 commit 列表 + decisions/sources 正确;无叙事的 SHA 只给 sha/subject/date;非 changed 文件不出现在索引(有界)。
- console.html:沿用 `test_console.py` 范式,断言注入 `data.tree.nodes`/`grounding` 存在 + 关键 DOM/JS 标记(树容器、右面板、状态 tooltip)存在;CHAT 与非 CHAT 模式不破坏既有断言。
- 全量 `python3 -m unittest discover -s tests` 绿;各模块 `wc -l` <300。

## YAGNI / 非目标
- 不做全树逐文件 LLM 预热;console 深层 why 交给已有 `blame` CLI,不在面板内重造。
- 不新增 REST 端点(数据渲染时预注入;console 走 stdlib `webserve` 不加路由)。
- 不抽象共享树组件(2 消费者,按约定各放一份;第三处消费者再抽)。
- 不做 diff 内容查看(纯 what 撞 GitLens/DeepWiki、off-mission);本视图只「结构 + 状态高亮 + 点击接地 why」。
- `report` 视图本期不纳入(host 性质待核;console + web 已满足「两者都做」);如确为视图宿主可后续按同数据 + 同树 JS 加,不在本 spec。

## 开放问题
无(brainstorm 两处 fork 已定:工作区口径 + 两主机;树折叠 + 右面板已定)。
