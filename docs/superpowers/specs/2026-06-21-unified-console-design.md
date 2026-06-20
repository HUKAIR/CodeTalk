# 统一控制台 `vibetrace console` 设计

> 状态:已批准设计(经 brainstorm 两次 AskUserQuestion 锁定:统一控制台 · 全四视图),待落地。
> 日期:2026-06-21。

## 背景与目标

现在的 web 产物(tunnel/graph/course)各自"一整页 dump 全部内容",无统一入口、无渐进披露。
**做一个单文件 web 控制台**:进页先看"开工概览",顶部导航切四视图,每视图概览优先、按需钻取。
全程**零 LLM**(吃已缓存数据),守 M0(单文件、零构建、离线、零依赖、普通字体)。

## 命令

`vibetrace console [--project] [--serve] [--no-open] [--vault]`
- 默认:生成静态 `<vault>/<project>-console.html`,只读(file:// 胶囊按钮禁用)。
- `--serve`:起 127.0.0.1 本地服务,胶囊回答 + 回看写回 cache.db(`/capsule`、`/reviewed`)。

## 信息架构(四视图,顶部导航,落地=概览)

1. **开工概览(landing)** = brief 的 web 版:你上次停在哪(latest daily)+ 理解债 top3 +
   到期待验证胶囊(serve 可现场答)+ 面包屑覆盖率;每块带"→ 去对应视图"入口。
2. **时光轴** = 线性时间线(最新在顶、按天分组、点开展开叙事)。
3. **决策图** = 时间轴 DAG(点决策节点 → 下游影响列表)。
4. **理解债** = 全量榜(债条形 + 点文件 → churn/回看/上次决定详情)。

每视图概览优先、点击钻取,不再一次铺全部。

## 数据装配(`console.py`,零 LLM,复用现成件)

`_assemble(project_path, cache) -> (data, err)`:`collect_commit_files(pp)` **一次**取
(sha/date/subject/files,无 diff、轻),喂给:
- `tunnel._payload(commits, narratives, capsules_by_sha, today)` → `timeline`
- `graph._assemble(commits[-SCAN_LIMIT:], pp, project, cache)` → `graph`
- `debt.debt_board(pp, cache, today)` → `debt`(top3 进概览)
- `cache.latest_daily` / `cache.pending_capsules` / `brief._breadcrumb_coverage` → `overview`

返回单一 JSON `{overview, timeline, graph, debt}`,注入 `console.html` 的 `$data`(另
`$project`/`$generated`/`$serve`)。`</ ` 转义同既有(`.replace("</","<\\/")`)。落盘前 `redact_secrets`。

## `console.html`(单文件四视图 app)

- 顶部:VIBETRACE 控制台 · project · generated + 四标签导航;客户端切视图(show/hide,零构建)。
- 四视图渲染从 `DATA.overview/timeline/graph/debt`;延续时光轴的深色编辑式 + 普通字体(系统无衬线 + SF Mono)。
- `$` 纪律:只用 4 个模板变量,JS 不用 `${}` 模板字面量,文本无裸 `$`。
- 安全:所有注入文本经 `esc()`。

## 共享 web 服务 `webserve.py`(DRY)

抽 `serve_html(html_text, project_path, open_browser=True) -> error_or_None`:127.0.0.1 http.server +
`POST /capsule {capsule_id, outcome}`(校验 outcome ∈ 枚举)+ `POST /reviewed {sha}` 写回 cache;
绑 127.0.0.1(数据不出本机)。`tunnel.serve_tunnel` 重构为复用它;`console.serve_console` 同用。
**避免把这段非平凡的服务逻辑在 console 重复一遍**(渲染可重复,服务器不该重复)。

## 与现有命令关系

`console` 是统一入口;`tunnel`/`graph`/`course` **保留**作聚焦单视图导出(不删、不破坏 CLI)。

## 取舍(诚实)

- **渲染重复**:M0 零构建 → 无法跨文件共享 JS,console 的时光轴/图渲染会与独立 tunnel/graph
  有重复代码。本轮接受(独立命令保留);长期可让 tunnel/graph 退化成"打开 console 定位视图",另议。
- console.html 会较大(四视图 + 导航 + serve JS);这是单文件 app 的固有体量,与既有 HTML 一致。

## 增量实现(每步可测/可看)

1. `webserve.serve_html` 抽取 + `tunnel` 改用它(重构,既有 tunnel 测+dogfood 保绿)。
2. `console.py` `_assemble`(TDD:四视图数据齐全 + 脱敏)。
3. `console.html` 壳 + 导航 + 概览视图。
4. + 时光轴视图。
5. + 理解债视图。
6. + 决策图视图。
7. `cli console` 子命令(render + serve)+ dogfood 打开。

## 测试

- `console._assemble`:返回含 overview/timeline/graph/debt 四键;空仓不崩;脱敏(塞假 secret 进叙事 → 输出 [REDACTED])。
- `webserve.serve_html`:抽取后 tunnel 既有 serve 行为不变(若有测);outcome 枚举校验。
- `cli console`:子命令注册、render 产出含四视图标记。
- HTML 视觉靠 dogfood。

## M0 / 验证

- `python3 -m unittest discover -s tests` 全绿;各模块 <300;`grep LLMClient console.py webserve.py` = 0。
- dogfood:CodeTalk 真跑 `console`,四视图都有内容、导航可切、概览先行、secret 不落盘。
