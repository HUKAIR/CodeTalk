# 决策影响图(`graph`)— 设计

日期:2026-06-17  ·  阶段:M0 扩展  ·  状态:已通过设计评审,待写实现计划

## 背景与目标

关系图谱的另一半(单代码 AI 提问是前一半)。回答 **"这个决定引发了哪些后续改动"**——决策影响,
不是代码调用图(后者看 IDE/logfile 也有,护城河弱)。

**纯本地、零 LLM**:节点/边全部由现成数据(决策面包屑 + 已缓存叙事 + 胶囊 + git 文件历史)装配。
和 `debt`/`brief` 一样是认知基础设施——"关掉 LLM 还在不在"测试 = 在。

按 Simplicity First 取最简可行:**文件级边 + 稀疏节点**。行级精度列为非目标(见下),
待简版证明太糙再上(`ask` 已备好 `line_log`,届时直接采用)。

## 形态
`vibetrace graph` → 写单文件 `<project>-graph.html` 到 vault;时间轴 DAG 主视图 + 点节点展开下游列表(v1;径向下钻列为后续);
复用 course/tunnel 的像素语言(B/W + #1783ff、硬边、像素字),纯 `file://`,**不引任何图库**(手写 SVG/CSS/JS,M0 零三方)。

## 数据与算法(全部现成函数,零 LLM)
- **扫描**:`collect_commit_files(project)` 取每 commit 的 `sha/date/subject/files`(返回全部、oldest-first;**它不做数量截断**)→ graph.py 自己 `commits[-200:]` 只算最近 200 封顶。
- **决策节点**:一个 commit 是决策节点当且仅当——有 `Vibe-Decision` 面包屑(`commit_body`+`parse_breadcrumbs`,**实线、高置信**),或其缓存叙事 `decisions` 非空(`cache.get_narrative`,**淡色、兜底**)。节点文案:面包屑优先,否则取叙事 `decisions` 首条。按**出度(影响力)top-N=40** 封顶,绝不糊。
- **影响边(文件级)**:决策节点 `C_d` → 较晚 commit `C_l`(`C_l.date > C_d.date` 且 `files(C_l) ∩ files(C_d) ≠ ∅`)。`C_l` 也成节点(纯改动节点=白,或它本身也是决策节点)。**排序与截断须确定**(评审 MED-3):决策的影响力 = 其**全部**下游计数,据此取 top-N=40;但每个决策**画出的边 ≤8 条,取其后时间上最近的 8 个**(nearest-downstream,因果更相关)。
- **胶囊徽标**:`cache.all_capsules(project)` 按 `sha` 匹配决策节点,给节点挂徽标 `预测 ✓/✗/待验证`。**不连边**——胶囊的"验证"是用户在日报里勾选的枚举,没有对应的"验证 commit",硬连边会是编造的。
- **缓存**:整图 JSON 以 `graph:<head_sha>` 为键(immutable),复用 `commit_narratives` 表(像 course/ask,不加表);重跑秒出。

## 组件 + 行数预算
- **`graph.py`(新建,~140)**:装配 nodes/edges/badges + top-N + 出边截断 + 注入模板。纯 git+cache,零 LLM,可像 `debt.py` 一样独立测。
- **`graph.html`(新建,~180)**:时间轴 DAG 主视图(x=commit 时间,边一律向右流);点决策节点 → **展开它的下游列表**(决策原文 + 下游改动 + 胶囊徽标)。手写 SVG/CSS/JS,`file://`,无图库。**v1 不做径向下钻**(评审 MED-2:径向 + DAG 手写易破 300 行;列表版稳妥且更 Simplicity First),径向作后续增强。
- **`cache.py`(+1 行)**:`recent_open_loops` 的 WHERE **再加第 4 个子句** `AND sha NOT LIKE 'graph:%'`(现已排除 `digest:/ask:/course:`;`graph:` 行无 `open_loops` 但会占 `LIMIT` 名额挤掉真未闭环)。
- **`cli.py`(+~8 → ~230)**:`graph` 子命令(`--project`、`--vault` 覆盖输出目录)。
- **`gitlog.py`**:无改动——复用现有 `collect_commit_files`/`commit_body`/`parse_breadcrumbs`。

## 隐私(红线)
- 注入 HTML 前,对所有文案(决策原文、叙事、徽标)一律 `redact_secrets`(沿用 course 的泄漏教训)。

## 降级与容错(CLAUDE.md:解析外部数据必须容错,绝不崩溃)
- 无决策 / 无 commit 历史 → 写一张"还没有可画的决策(去留 `Vibe-Decision`,或先 `digest`)"的空图,返回 `(path, None)` exit 0——**不要**学 course.py 把空 commit 当 error 返回(评审 LOW-3)。
- `collect_commit_files`/`commit_body`/缓存读失败 → 跳过该 commit 记警告,降级继续。
- 边集为空但有节点 → 画孤立节点,正常。

## 验收标准(goal-driven,纯本地可复现)
1. `vibetrace graph` 在本仓生成 HTML;打开见时间轴 DAG,`c60655f`("watch→risks"那条 `Vibe-Decision`)作为**实线**决策节点出现。
2. 文件级边正确:造一个改 `vibetrace/enrich.py` 的后续 commit → 它作为 `c60655f` 的下游节点、连一条影响边;只改无关文件的 commit 不连到它。
3. 点一个决策节点 → 展开下游列表,显示其下游改动 + 决策原文 +(若有)胶囊徽标。
4. 空仓 / 无决策分支 → 空图提示,exit 0,不崩。
5. 各模块改后 <300 行;`graph` 全程**零 LLM**(不构造 `LLMClient`)。
6. secret 不入 HTML;`test_cache_filter` 增一行 `graph:<x>`(无 open_loops),断言简报仍只返回真未闭环。

## 非目标(YAGNI)
- **不做行级边**(`git show --unified=0` 解 hunk + `line_log` 回溯):精度增强,待简版"图太糙"再上;`line_log` 已为 `ask` 备好,届时直接采用。
- 不做力导向 / 通用图布局;不引 d3 等任何三方图库。
- 胶囊不连边(无真实验证端点)→ 落成节点徽标。
- **v1 不做径向下钻交互**(评审 MED-2):先点击展开下游列表,证明不够再上径向。
- 不做实时服务 / 交互编辑;静态 HTML 一次性生成。

## 依赖与顺序(重要)
本功能复用 `commit_body` / `parse_breadcrumbs`(gitlog.py)与"面包屑折进叙事"(enrich.py)——
**这些只在 ask 分支(PR #8)上,main 还没有**。因此:
- **推荐顺序**:先评审/合并 PR #8 → 从更新后的 main 切 `feat/decision-impact-graph` 分支 → 在该分支提交本 spec+plan 并实现。依赖天然满足,PR 干净。
- 备选:把 graph 直接栈在 ask 分支上(耦合两个 PR、评审变脏)——不推荐。
- 现状:本 spec 暂以**未跟踪文件**留在工作区,**不提交进 PR #8**(避免污染其 diff);待 #8 合并、graph 分支建好后随首个 commit 落入。

## 风险与开放问题
- 文件级边在 vibetrace 自身(7 文件)会偏密;靠**稀疏节点**(仅决策性 commit + top-N=40 + 每决策出边 ≤8)压制。用户自己更大的项目里文件多、天然更稀。
- 早期面包屑少 → 节点多来自叙事 `decisions`(淡色);随 `Vibe-Decision` 积累,实线高置信节点变多、图变准——预期的渐进增强,不阻塞上线。
- (原"径向下钻撑破预算"风险已按评审 MED-2 解决:v1 改为点击展开下游列表,`graph.html` 预算降到 ~180。)
