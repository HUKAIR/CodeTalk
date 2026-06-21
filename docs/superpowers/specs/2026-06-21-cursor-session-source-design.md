# Cursor 会话源 — 设计 spec

**状态**:已批准设计,待写实现计划。
**日期**:2026-06-21
**作者**:vibetrace(dogfood)

## 背景与动机
问卷1 差距分析(`docs/discovery/gap-analysis-问卷1.md`)的头号错位:vibetrace 只解析 Claude Code 会话(`~/.claude/projects/`),而大量目标用户**主力是 Cursor**;他们反复找不回的 AI 决策对话(选型、为什么这么改)全在 Cursor 里"会话太多找不到/被新会话覆盖/没导出"。按现状,vibetrace 对 Cursor 用户核心价值几乎落空。

只读 spike(`spikes/cursor_session_spike.py`)已实证:Cursor 把 AI 会话存在本地 SQLite,可用 stdlib `sqlite3` 解析、映射成 vibetrace 的 session 形状、文件+时间可对齐。本特性把它工程化为正式会话源。

**已锁定的设计决策**(brainstorm 确认):
1. 启用模型 = **显式 opt-in**(默认不读 Cursor)。
2. 项目归属 = **workspace 优先 + 文件兜底**。
3. 入库深度 = **同 Claude:用户提问 + AI 摘录**(脱敏 + 首尾截断)。
4. 集成架构 = **方案 A**:新 `cursor_sessions.py` 输出与 `sessions.py` 同一 session 契约,在 digest 的会话汇集点合并;`sessions.py`/`align.py`/`enrich.py` 不改其消费逻辑。

## 目标 / 非目标
**目标**:opt-in 开启后,`digest` 富集 commit 叙事时把**本仓相关的 Cursor 会话**与 Claude 会话一并纳入软关联,使 ask/graph 等下游(吃缓存叙事)自然受益。
**非目标(YAGNI)**:旧 `aiService.prompts/generations` 存储;全量对话入库;回写 Cursor;实时 watch;Cursor 之外的 IDE;为 Cursor 单独做 UI。

## 已验证的 Cursor 数据模型(实测,免实现者重新 spike)
- macOS 路径:`~/Library/Application Support/Cursor/User/`;Linux `~/.config/Cursor/User/`;Win `%APPDATA%/Cursor/User/`(后两者**未实测**,见开放问题)。
- **全局库** `globalStorage/state.vscdb`(SQLite),表 `cursorDiskKV`:
  - `composerData:<composerId>` → 会话元数据:`createdAt`(epoch ms)、`fullConversationHeadersOnly`、`context`、`totalLinesAdded/Removed`、`text`(草稿)。
  - `bubbleId:<composerId>:<bubbleId>` → 单条消息:`type`(**1=用户, 2=AI**,启发式)、`text`/`richText`(正文)、`createdAt`、`relevantFiles`/`recentlyViewedFiles`(str 列表)、`attachedCodeChunks`/`attachedFileCodeChunksMetadataOnly`(dict,含 `uri`/`relativeWorkspacePath`/`fsPath`)、`commits`(常空)。
- **工作区库** `workspaceStorage/<hash>/`:
  - `workspace.json` → `folder`: `file:///abs/path`(**URL 编码**,需 `urllib.parse.unquote`)。
  - `state.vscdb` 表 `ItemTable` 键 `composer.composerData` → `{"allComposers":[{"composerId":...}, ...]}` = **该工作区的 composerIds**。
- 归属链:`workspace.json.folder == 本仓` → 该 workspace db 取 composerIds → 全局 db 取这些 composer 的内容。

## 组件:`vibetrace/cursor_sessions.py`(<300 行)
对外唯一入口,**契约与 `sessions.scan_sessions` 完全一致**,使 digest 可无差别合并:

```
def scan_sessions(project_path, since_dt, cache=None) -> (summaries, error_or_None)
```
- 永不抛异常,容错降级(同 sessions.py 契约)。
- `since_dt` 截断:跳过末条消息早于窗口的会话。
- 返回的每个 summary 必须含 `align`/`enrich` 消费的字段(契约):
  - `session_id`: str —— 用 composerId。
  - `title`: str —— 首条用户提问前 ~60 字(无则 composer `text` 草稿)。
  - `prompts`: list[str] —— 用户提问(脱敏 + `head_tail` 截断)。
  - `excerpts`: list[str] —— AI 摘录(脱敏 + `head_tail` 截断)。
  - `files_written`: list[str] —— **绝对路径**(align 会 `relative_to(project_root)`);Cursor 文件多为相对/URI,需还原成绝对(基于归属到的仓根)。
  - `start`, `end`: tz-aware datetime —— 首/末条 bubble 的 `createdAt`(epoch ms → UTC)。
  - 缓存 freeze/thaw:**优先复用 `sessions._freeze/_thaw`**(若 summary 形状一致);形状有差异则本模块自带等价 freeze/thaw,保持 digest/cache 不感知差异。

## 数据流 / 项目归属
1. 定位 Cursor `User/` 目录(跨平台候选,取首个存在者);无 → 返回 `([], "未找到 Cursor 数据目录")`。
2. **workspace 优先**:遍历 `workspaceStorage/*/workspace.json`,`unquote(folder)` 的路径 == `project_path`(`resolve()` 后比较)→ 命中的 workspace db 读 `composer.composerData.allComposers` 得 composerIds。
3. **文件兜底**:无命中 workspace 时,扫全局所有 composer,凡会话内文件路径能 `relative_to(project_root)` 的(至少 1 个)即归属本仓。
4. 对归属到的每个 composerId:全局 db 取 `composerData` + 全部 `bubbleId:<id>:%`,按 bubble `createdAt` 排序 → 映射成 summary。

## 会话映射规则
- 角色:`type==1`→prompts、`type==2`→excerpts;其它/缺失 → 跳过该 bubble。
- 文件:并 `relevantFiles`/`recentlyViewedFiles`(str)+ `attachedCodeChunks`/`attachedFileCodeChunksMetadataOnly` 里的 `uri|relativeWorkspacePath|fsPath`;相对路径基于归属仓根拼成绝对。
- 文本:`redact_secrets(text)` 后用 `sessions.head_tail` 按 sessions.py 同款上限(`PROMPT_CAP` 截提问、`EXCERPT_CAP` 截 AI 摘录)截断,与 Claude 一致;空文本跳过。
- 时间:`datetime.fromtimestamp(createdAt/1000, tz=utc)`。

## 启用 / 隐私(opt-in)
- config 新增 `sources`(默认 `["claude"]`);含 `"cursor"` 即启用;命令行 `--source {claude,cursor,both}` 可覆盖(digest/ask 等用会话的命令)。
- **首次启用一次性提示**(stderr/stdout):"将读取本地 Cursor 会话(只读、不出本机),可在 ~/.vibetrace/config.json 的 sources 关闭";用 config 里一个 `cursor_notice_shown` 标记保证只提示一次。
- 只读打开:`sqlite3.connect("file:...?mode=ro&immutable=1", uri=True)`(immutable 避开 Cursor 正在运行的写锁)。
- 落盘前 redact:summary 文本在本模块即脱敏;且 `put_narrative` 入口已统一脱敏(双保险)。

## 缓存 / 增量
复用现有 `session_enrichments` 表与 `cache.get_session/put_session`,**映射**:
- `session_id` ← composerId;`last_msg_ts` ← 末条 bubble ISO 时间;
- `mtime` ← 末条 bubble `createdAt`(float);`size` ← bubble 数量。
- 命中(mtime==且 size==)→ 复用缓存 summary;否则重解析。会话新增消息 → mtime/size 变 → 自动重算(符合"session_id+last_msg_ts 增量"约定)。
- 注意:composerId 与 Claude 的 sessionId 同表共键空间,UUID 不会撞,无需新表。

## 集成(确切改动点)
`digest.py`(当前 line 66-70):
```
session_list, session_err = sessions.scan_sessions(project_path, since_dt, cache)
# 新增:opt-in 时合并 Cursor 会话
if "cursor" in sources(cfg, args):
    cur_list, cur_err = cursor_sessions.scan_sessions(project_path, since_dt, cache)
    session_list = session_list + cur_list
align.align(commits, session_list, project_path)
```
- `sources(cfg, args)` 小工具解析 config.sources + `--source` 覆盖。
- ask 走缓存叙事 + git,不直接 scan 会话 → 一旦 digest 用 Cursor 富集过,ask/graph 自然受益,**ask 无需改**(确认:ask._retrieve 不调 scan_sessions)。
- cli/commands 加 `--source` 旗标到 digest(必要时 ask)。

## 错误处理(M0 红线)
- 库锁/缺失/损坏 → 警告 + 返回空列表(digest 降级回 Claude-only),**绝不崩**。
- 单 composer/bubble 解析失败 → 跳过该会话/该条 + 警告,不影响其余。
- schema 漂移 → 全程 `.get()` 防御;`type`/字段缺失按"跳过"处理。
- 明确声明:不同 Cursor 版本 schema 可能变;Linux/Win 路径未实测。

## 测试(stdlib unittest,合成 SQLite fixture)
不依赖真实 Cursor。`tests/` 内建临时 `state.vscdb`(建 `cursorDiskKV`/`ItemTable` 表 + 样例行):
1. workspace 归属:workspace.json folder==仓 → 取到正确 composerIds → 只纳入本仓会话。
2. 文件兜底:无 workspace 命中时,按文件路径重叠归属。
3. composer→session 映射:bubbles 按 createdAt 排序;type1→prompts、type2→excerpts;files 抽取(三来源)。
4. 时间窗:since_dt 截断早于窗口的会话。
5. 脱敏:含 secret 的 bubble 文本 → summary 内 `[REDACTED]`。
6. 容错:坏 json 行、缺 `type`、缺键、库不存在 → 不崩、降级。
7. 缓存增量:同 (composerId, ts, count) 命中缓存;消息增多 → 重算。
8. 契约:summary 含 align/enrich 所需全部字段(start/end/files_written/session_id/title/prompts/excerpts),且能跑通 `align.align`。
9. digest 合并:opt-in 时 Cursor 会话进 session_list;未开启时不读 Cursor。

## 红线合规
`sqlite3` 标准库(零新依赖)✓ · 新模块 <300 行 ✓ · 本地只读、数据不出本机 ✓ · 落盘前脱敏 ✓ · 解析容错降级绝不崩 ✓ · 缓存 SHA/会话增量约定 ✓。

## 开放问题 / 无法验证项
- Linux/Windows 的 Cursor 路径与库结构**未实测**(macOS 已证);实现按候选路径兜底,实测留待有环境时。
- Cursor `composerData`/`bubble` 为**非官方 schema**,跨版本可能变;靠防御式解析 + 版本无关字段。
- `type` 1/2→用户/AI 为启发式(spike 观测);实现时对少量样本二次核验,必要时加兜底(按是否有用户输入特征判定)。
- `commits` 字段实测常空 → 对齐以文件+时间为主(align 已如此),不依赖 Cursor 自带 commit 引用。
