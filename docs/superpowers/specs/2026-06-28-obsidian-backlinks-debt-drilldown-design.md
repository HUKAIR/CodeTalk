# 回面路径接地化:两个独立 spec(Obsidian 自动反链 · 债下钻子视图)

> 状态:DRAFT v2(已过对抗审 spec wf_92328485,4 透镜 approve-with-fixes,本稿折入全部修正)。日期 2026-06-28。
> **对抗审关键裁决:Track A 与 Track B 零代码/数据/风险耦合,「共用回面路径」只是共享原则,
> 应作两个独立 spec / 独立 plan / 独立 PR。** 本文件按用户「合并」请求收在一处,但下面是**两份独立 spec**,
> 分开实现、分开回滚;北极星埋点只归 Track B。只写设计,不含实现代码。

## 共享前提(两 Track 都遵守,非耦合)
- 只做**机器自动产出 + 逐字接地 + 用户只确认**;不开任何「请你写/维护笔记或链」的入口(3/3 证据反对手写留痕)。
- 北极星=回面后实际处理率;**可发现性 ≠ 价值兑现**。反链/下钻确定性提升的只是可发现性,能否撬动处理率
  是未验证假设(根因优先级博弈)→ 当北极星实验、达标才扩面,与 `accident-prevention-reaudit` 的 2026-07-01
  验证窗同源对账。**严禁**用链数/节点数/项数背书。
- M0:仅 stdlib;零-LLM;数据不出本机;单模块 <300(`cache.py` 已 299、`commands.py` 296,新逻辑不得落这两处);
  落盘前脱敏;零-build vanilla-JS。

---

# Spec A — Obsidian 自动反链(写侧)

## A.0 目标
vibetrace 自动产出的 vault 产物之间**自动发射 `[[wikilink]]`**(机器挖、复用 `graph._assemble` 已算的
决策→下游边 + 真实 SHA;现状 `*.py` 中 `[[`=0,融合停在文件层),让你在 Obsidian 一跳到真源。

## A.1 范围
- **A1 产物子目录隔离**:新产物写入 `vault/vibetrace/<slug>/`,与用户笔记物理分离。
- **A2 发射 `[[wikilink]]`**,最小语义 4 类:日报 ↔ 当日 commit、commit ↔ 决策(复用 graph 边)、
  ask 笔记 ↔ 被问文件、胶囊 ↔ 来源 SHA。
- **非目标(本 spec)**:A3 canvas 节点 `type:text→type:file`(与 A1 强耦合、断链风险高、是「第二跳」锦上添花)
  → **Track A v2**;`migrate-vault` 迁旧日报 → v2;Obsidian 插件;读用户笔记当接地(证据双向)。

## A.2 已定决策(对抗审修正版)
- **DA1 子目录命名用 pkey 派生、非裸 basename**:`<slug>` = 绝对路径的确定性哈希/sanitize(对齐 cache 用绝对
  路径 pkey 防串),**避免同名 basename 两项目在 `vault/vibetrace/<同名>/` 物理混写、回读串答案**。
- **DA2 回读闭环兼容(阻塞性验收)**:`read_capsule_answers`(`report.py:127` 现 `vault.glob("*-{name}.md")`
  非递归)改为**显式扫两路**:旧根 `vault/*-{name}.md` + 新 `vault/vibetrace/<slug>/*-{name}.md`;
  **禁用全量 `rglob`**(会扫进用户笔记,违反「绝不解析用户笔记」)——只递归 vibetrace 自有子目录。
- **DA3 反链锚点只用「确定安全」的标识,脱敏交给显示文本**:wikilink **锚点 = 短 SHA(7 位 hex,永非 secret)
  + 项目内相对路径**(非绝对路径、**不含分支名/PR 文本**);决策/subject 等**显示文本**过 `redact_secrets`。
  **诚实边界**:`redact_secrets` 只脱 secret-**值**、不脱路径/分支名(实测 `feature/sk-...`、`src/auth/...`
  原样放行)——故**不把分支名/绝对路径放进链文本**是真解法,「过 redact_data」不是(它治不了路径)。
  另:若决策显示文本含 secret 被脱成 `[REDACTED]`,锚点仍是 SHA/相对路径(不受影响,无死链)。
- **DA4 flag 原子化**:`config.backlinks`(默认关)**同时**门控 A1 子目录落盘 + DA2 双路回读 + A2 发射——
  **不得半开**(目录搬了/链没发/回读没改 = 回读静默断裂)。开 flag 前置:DA2 双路回读已落地且通过冒烟。

## A.3 红线 / 隐私
- 纯字符串拼接、零-LLM、数据不出本机。
- **路径名本身是隐私维度**:链文本只用项目内相对路径(不泄露绝对目录结构);**提示**用户若把 vault 同步到云,
  相对路径仍会随之出网(文档注明,非本工具 phone home)。
- 落点模块行数:A 改 `report.py(157)`/`ask.py(261)`/`graph.py(174)`——逐 PR 控 <300。

## A.4 验收(TDD)
- A1+DA1:产物落 `vault/vibetrace/<slug>/`;两个同名 basename、不同绝对路径的项目不混写。
- DA2:**对真实结构冒烟**——旧根日报 + 新子目录日报,`read_capsule_answers` 都命中(闭环不断);确认不扫用户笔记目录。
- A2+DA3:日报含 `[[<sha7>]]`、commit↔决策链;锚点不含分支名/绝对路径;含 secret 的显示文本脱敏且不产生死链。
- DA4:flag 关 → 不搬目录、不发链、回读走旧根;flag 开 → 三者一致生效。
- 全量 unittest 绿;`check_static_no_external`(若动 graph.html/console 资产)通过。

## A.5 北极星归属
**Track A 验收只挂「可发现性 / 一跳到真源」**,并**显式声明不进处理率分子**(反链数永不背书)——
避免拆开后 A、B 抢北极星、复活「记录功能换皮」。

---

# Spec B — 债下钻子视图(读侧,console)

## B.0 目标
console 债视图每文件可**下钻**成真实构成(未回看的 AI 决策 commit + 未填风险胶囊),每项链到
blame/接地追问/去填胶囊——把「债分数」变「可一跳处理的真源清单」。

## B.1 范围
- **B1 下钻数据**:console `_assemble` 给债视图补 `drilldown`(每文件:未回看决策 commit[sha,subject] +
  未填胶囊[risk,capsule_id])。console.html 债视图渲染可展开,每项 `data-go` 到 blame / 接地 dock / 胶囊。
- **B2 降债信号收口**:下钻里「真处理 = 填胶囊『已解决』」为主信号;`reviewed`(点开即记账)显式标**护栏弱信号**。
- **非目标**:把下钻-触发的填充做成可归因的转化率埋点(需给 outcome 加 source 字段)→ **Track B v2**(见 B.4)。

## B.2 已定决策(对抗审修正版)
- **DB1 数据来源 = 重新派生,不是「复用 debt_board 行/不二次查 DB」**:核实 `debt_board`(`debt.py:72-77`)
  只回**计数**(reviewed/commits/caps_filled/caps_total),内部 `m["shas"]`/`capsule_id` 算完即丢。
  故下钻必须**重算**:在 `debt.py` 扩 `debt_board` 行 schema(加 `unreviewed_shas`、`pending_caps`),
  或加一个并行派生函数。**落 `debt.py`(79 行有余量),不落 `cache.py`(299)/`commands.py`(296)**。
  仍零-LLM、确定性、复用 `_assemble` 已在内存的 narratives/capsules_by_sha/reviewed,不新增 DB 往返(派生自现成内存)。
- **DB2 下钻只展开高价值项、防分母污染**:默认只对**有未回看决策或未填胶囊**的文件出下钻(不对全部文件铺),
  避免低价值项稀释。

## B.3 北极星(对抗审重写——原 D4 不可复算,本节是修正)
- **分子只认「已解决」**:胶囊 outcome ∈ {想多了, 已解决, 还在担心}(`report.py:114`)。处理率分子=**仅「已解决」**;
  「想多了/还在担心」计入分母不计分子;**`mark_reviewed` 永不进分子**(它是点开即记账的护栏弱信号,与 B2 一致)。
- **分母**:到期开启的胶囊数(`capsule_fill_stats` 的 opened,`cache.py:211`)——既有口径,确定性可复算。
- **v1 不宣称「下钻→处理」可归因转化率**:set_capsule_outcome/mark_reviewed 现**无 source 字段**,无法区分
  下钻触发 vs 时光轴/日报回读触发的填充。故 v1 验收用**既有 `capsule_fill_stats`(已解决-only 口径)在真实
  2026-07-01 数据上**度量;若要「下钻-归因」转化率,须先给动作加 source 埋点(经 `report.append_usage` 旁路
  或 outcome source 字段)+ 记基线 → **Track B v2**,flag 门控、埋点未落地不得开。
- **严禁**用下钻项数/链数背书(门 5);「接地问答有用性」若用作判据须先给可复算定义(锚到「据此真改了代码/
  填了胶囊/关了风险」),否则不作逃生口。

## B.4 红线 / 验收(TDD)
- 仅 stdlib;零-LLM;派生逻辑落 `debt.py`(<300);console.html 改后过 `check_static_no_external`。
- B1:`_assemble` 债项含 `drilldown`(未回看 SHA + 未填胶囊),有界、派生自现成内存;console.html DOM 标记 + `data-go`。
- B2:下钻里「已解决」为主信号、reviewed 标护栏(渲染断言);处理率分子只数「已解决」(单测口径)。
- 全量 unittest 绿。

## B.5 风险
- R-B1 下钻沦「更精致的 TODO 墓地」:DB2 只出高价值项 + B3 分子只认已解决(不被点开/链数充数);
  若 7-01 后处理率仍 <1/3 且多为「想多了」→ 下钻只对高严重度/可确定触发(重引入被否方案)的项,而非全文件。
- R-B2 「下钻→处理」归因诱惑:v1 显式不做(无 source 埋点),防止用不可复算指标自我背书。

---

## 跨文件备注(对抗审 missed 项收口)
- 拆开后:A 的验收挂可发现性、B 的验收挂处理率(已解决-only),**两 spec 都不得抢对方的北极星口径**。
- 即便图谱双向连通(用户笔记反链到 vibetrace 产物),**接地答案素材来源永远只限 vibetrace 自有子目录产物 +
  git/session 真实记录;链入侧用户笔记内容永不进 LLM prompt / 答案合成**(守逐字引真实记录护城河,堵证据双向破口)。
- feature-flag 基础设施现不存在(config/commands 无)→ A 的第一个 PR 须先建 `config.backlinks` 默认关。
