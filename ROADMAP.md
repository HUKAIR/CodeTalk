# ROADMAP

三层愿景;M0(变更叙事层)已交付,以下仅记录方向,不代表排期承诺。

## 外部对标驱动的缺口与排期(2026-06-25,两轮 deep-research)

来源:`docs/discovery/2026-06-25-外部对标-codereview与UX.md`(第一轮)+ `2026-06-25-外部对标-第二轮.md`(第二轮)。
按 Now/Next/Later 排,标红线。**本会话已落地**(PR #51/#52):FTS 回填、2 字中文 LIKE 召回、接地覆盖徽标(粗)、
MCP review-time 描述、console 内嵌接地对话 dock + 行/决策节点原地追问、enrich 覆盖补全命令、**MCP 参数对齐(Top3-①)、
`vibetrace review` 零-LLM review 入口(Top3-②)、引用 hover 预览+PR 跳源(Top3-③)**。以下是**仍缺的**。

**Now(低成本 / 红线内 / 高 ROI)**
- **「AI 声称 vs git 实际」偏差报告 ✅ 已落地**(PR #69,`vibetrace drift`):零 LLM,`sessions.files_written`(AI 工具动作)对 git 全史提交 + `align` → 报「工具改了却没落进对齐提交的文件」(写了未提交);`_ignored` 滤 `.git/`+gitignore 噪声;全史提交对齐避免 --since 截断误判。**诚实边界**:「声称」=工具动作非散文计划、只报字面文件缺口、**禁完成度 %/设计可行性**(语义需模型 + vibetrace 无 oracle)。本仓实测 163 改/158 提交/5 真未提交。**Vibe-Watch**:未跟踪非-gitignore 环境文件仍列入,可加 tracked-only 档收窄。[R7]
- **引用核验 hover 预览 + 点击跳真实源 ✅ 已落地**(PR #52,Top3-③):引用悬浮预览 + 点击跳真实 commit/PR/会话源(对齐 GitLens hover-card 范式)。[R2 · UX]
- **文件树「接地入口」视图 ✅ 已落地**(PR #62 console / #63 web):`git status --porcelain` 确定性 XY 码零-LLM 高亮新增/修改/未跟踪,**定位为导航入口**(点变更文件 → 接地追问「这文件当初为什么改」)非 diff 查看器;状态三重标记(tooltip + 非颜色文字 + 颜色,可访问性,借 VS Code#123103 教训);零-build 单文件 vanilla-JS,红线内。[R5 · UX]
- **定位文案收窄 ✅ 已落地**(PR #61 + README 首屏重写):复合护城河(零-LLM 确定性 + 逐字真实原话 + 自动挖掘非手写 + 本地)+ 一句话「别人要你手写 why,vibetrace 自动从真实记录挖」已上 README 首屏;泛「接地对抗幻觉」(已被 GitKraken/Context7/GitHub MCP 占用)弃用为主卖点。[R2 · 定位]
- **MCP 对齐参数词表 + 集成层定位**(✅ 已落地 PR #52):保留独占 `vibetrace_*` 工具名,blame/ask 加可选入参别名 **path/startLine/endLine**(owner/repo 等收下即忽略),定位「GitHub MCP 之上的零-LLM why 增强层」。⚠ 不可改名成 get_diff/get_commits(GitHub MCP 真名是 get_commit/list_commits/pull_request_read,改名会撞名+丢 why 护城河)。注:实读仅 path/startLine/endLine,未收 sha/pullNumber(不映射 blame 的 file:line 口径,避免静默给错答案)。[R2 · 集成,对抗复跑核实]
- **接地命中率自证**(dogfood)✅ 已跑(`scripts/grounding_hitrate.py`,`docs/discovery/2026-06-25-接地命中率自证.md`):CodeTalk 覆盖上限 **92.3%**(72/78,叙事+面包屑)→ green-light review-entry 扩面/grounding-eval。**诚实缺口:evidence 会话原话锚点 0%**(enrich 用空会话对齐、早期 digest 未留 evidence)→ 文案暂不讲「引真实会话原话」;补法见下 Next。[R1 open Q · 数据]
- **补 evidence 会话原话覆盖 ✅ 已修复**:`enrich` 改为扫真实会话对齐 + 新增零-LLM `backfill_evidence`(`cache.set_narrative_evidence` 只加 evidence、不动 LLM why/decisions,守 immutable)。`vibetrace enrich --no-llm` 实测 **evidence 0→68**(覆盖全部 68 条有叙事 commit;接地覆盖上限以 `grounding_hitrate.py` 复跑为准)。护城河第三支柱「引真实会话原话」立起。

**Next(需设计 / 验证)**
- **review 工作流入口 ✅ 已落地**(PR #52 入口 + #75 溯源精度):粘 PR/diff → 逐改动块 blame「历史决策 + 真实引用 + **溯源精度**」(交互链 B)。置信度落点=**确定性溯源准度**(行级精确/文件级降级/无据),**非**答对率(语义需模型,R6 不判)。⚠ 撞 CodeRabbit/Greptile 腹地,差异化靠逐字 + 本地 + 诚实不判对错。[R1 链B + R2 MSR2026 · 能力] **[2026-06-27 命中率已量]** `scripts/grounding_recall.py`(零 LLM,复用真实 blame 引擎)行级实测**可达率 99.5%**(本仓抽样;`docs/discovery/2026-06-27-接地召回自证.md`)→ **检索 reach 不是瓶颈,该项可启动**;但 **99.5% 是「可达上限」非「答对率」**(R6:够到的 why 是否对这一行正确=语义需模型,不做),故卖点须落「逐字引真实记录」非「判对错」。饱和源于本仓面包屑纪律,不外推。
- **接地质量可验收(已对抗复跑改 scope)**:⚠ 原「字符串 n-gram 逐句归因 + τ 三标签」经三视角 + 本仓 fixture 实测**证伪**(对 LLM 忠实释义假阴、对因果错配幻觉失明;字符串恒等 ≠ Trust-Score 语义蕴含)。改做:答案里**逐字命中材料的片段**高亮 + 链回确定来源(字符串恒等只在逐字子串处成立)+ 保留粗徽标 + 点开核验;**不打 grounded/inferred/unsupported、不设 τ**。文案不可宣称「答案满足 Trust-Score / 零幻觉」,只讲「引用是可核验真实逐字记录」。[R1 SO/Uber + R2 Trust-Score · 对抗复跑修正] **[R6 收紧]**:外部对标证实「忠实 groundedness 本质=语义蕴含(NLI/LLM-judge),纯词法重叠系统性失效(HANS 0.28)」——故本项**只做逐字引用保真**(dev-only:校验展示的引用 SHA/PR/会话片段逐字真实存在,出可复算「X% 引用逐字可验」),诚实边界=「标出逐字无据(高精度低召回零成本)」,**绝不宣称检出所有幻觉/语义忠实**;语义召回的本地小 NLI(HALT-RAG 式)= Later/可选。[R6] **[dev-only 逐字引用保真自检 ✅ 已落地]** `scripts/citation_audit.py`(PR #65,零 LLM:面包屑对 commit body + evidence 对当下重扫会话逐字核;本仓 111/111 + 459/459 = 100% 逐字可验)。**答案内逐字命中高亮 ✅ 已落地**(PR #67,仅 web:`highlight.segments` 后端切段 → `<mark>`+legend+chip 锚点,匹配纯原话 `verbatim` 非脚手架,后端切段消灭 Python 码位 vs JS UTF-16 错位;ask 砍——其管线不经 chat.answer)。**仍开放**:语义召回本地 NLI(Later/可选)。
- **面包屑 schema 扩:`Vibe-Rejected` 一等公民 ✅ 已落地**(PR #78):被否决备选(diff 取不到的 why-NOT)提成可解析、`blame`/`ask`/`search`/`adr` 全路径独立标「否决备选(曾放弃)」。**是踩坑拦截 dogfood 协议(`docs/discovery/2026-06-27-北极星-踩坑拦截-dogfood协议.md`)的使能器**:重引入已否决方案时 blame 确定性告警。原列的「agent 指令 / 验证元数据」**砍**(已被 evidence/test_refs 覆盖,加=重复)。[R2 · 能力,红线内]
- **ADR 导出(MADR/Nygard)✅ 已落地**:`vibetrace adr-export <文件[:行]> [--format madr|nygard]`(`adr_export.py`,零 LLM,复用 blame.collect_segments,「来源」段逐字引真实 commit SHA+原话)。填手写 ADR 生态(adr-tools/Log4brains 全手写、无自动 git 提取)的空位——「别人手写 ADR,vibetrace 自动导出且逐字接地」。对抗复跑判定为 Block B 纯加分。
- **叙事覆盖收尾提示 ✅ 已落地**:`digest` 收尾零-LLM 自检全史叙事覆盖,有未叙事 commit 即提示跑 `vibetrace enrich`(不自动调 LLM、不偷花 token)。口径=「有无叙事」,严于 `grounding_hitrate.py` 的接地覆盖上限(叙事 OR 面包屑),故名「叙事覆盖」不混用,避免重演指标打架。原 [本会话 Vibe-Watch] 闭合。
- **只读收割命令历史/会话作接地素材(红线内版)** —— **⛔ 已评估后搁置(2026-06-27)**:出过 brainstorming + spec,**对抗审 spec 否决**(见 `docs/superpowers/specs/2026-06-27-command-history-grounding-source-design.md` 顶部裁决)。4 个根本性问题:① 无 cwd → 隐私归因闸低召回/高假阳两难不可解;② 脱敏漏 DB 连接串/内网主机/身份路径;③「接地源」是超声明(不进 ask/blame);④ off-moat 且未验证——**实质印证本线自己的「验证后做」flag**。原范围(只读 shell `~/.*_history` + Cursor 会话,本地+脱敏+可关;⚠ 拒可执行内嵌终端/OS 级全量捕获)存档备查;**将来拿到 cwd 信号或验证到真实需求再按保守重构评估**。[R5 · 能力/隐私]

**Later / 待评估(成本高或须红线权衡)**
- **IDE 扩展(VS Code:gutter blame + CodeLens「为什么这么写」+ hover 真实原话)** 作第二分发面,最贴 review 现场。⚠ 须权衡 M0 红线(禁重前端构建链)+ 维护成本。[R2 · UX/分发]
- **本地 on-device LLM provider(Ollama 等)✅ 已落地**(`config.py` 内置 `ollama` provider:`http://localhost:11434/v1`、`local:True` 免 key;`llm.py` 经 base_url/local 标记自动识别本机端点 → 连综合答也可全本机)。**诚实边界**:本地 LLM = 便利非对等(第三/四轮:接地条件下本地-云仍差 5-6 分、agentic 只云吃红利),护城河钉「零-LLM 逐字接地**模型无关**」非「本地追平云端」。[R1/R2 缺口]
- **chat 流式 JS 抽共享**:console/web_chat 现两处重复;按「第三处消费者才抽」阈值,未触发即不抽(避免不可验证的浏览器重构)。[本会话 #2]

**红线警示(守 / 拒)**
- MCP provenance 赛道拥挤(GitHub MCP / codebase-memory-mcp 14.2k★)→ **确定集成**(第四轮证有中间件/聚合先例 MetaMCP / mcp-proxy `wrapWithProxy`:vibetrace 作 provenance 中间件,可插聚合器、与 GitHub MCP 共存),不竞争、不自建协议、不拼结构化代码图谱(撞 codebase-memory-mcp 腹地)。[R2/R4]
- local-first 与「接地对抗幻觉」**非护城河 / 已被占用**,不当主卖点。[R1/R2]
- **多模型对抗审查作付费产品 = 撞 CodeRabbit/Greptile 腹地 + 偏离「找回 why」护城河 → 拒**;多模型对抗模式留作 **dev-only 接地质量验证手段**(judge-panel 验真),面向用户仍是 `review` 给 why 而非判对错;付费墙在 dogfood 证明「真拦一次理由丢失型踩坑」前不启动。[R5]
- **「完备幻觉检测 / 多模型对抗辩论」= 拒**(R6):MAD 经 ICML24/ICLR25 实证无可靠增益且贵 ~1.6×;忠实无据检测本质需语义蕴含模型(撞满地 LLM-judge 腹地)。vibetrace 守「零-LLM 确定性逐字 provenance」这条空白缝、不比语义检出率;任何幻觉/无据 claim 必须限定「逐字无法溯源(高精度低召回)」、**禁「检出所有幻觉/保证语义忠实」**。[R6]

**第三轮已补(verified,见 `docs/discovery/2026-06-25-外部对标-第三轮.md`)**:① 变现(**2026-06-29 自我修正**:原「open-core 按席位 + 团队治理/SSO 付费闸门、重心团队治理」与 M0 红线「禁团队功能 / 跨用户飞轮 / 数据出本机 / 账号体系」+ 门4 撞 Repowise 腹地**自相矛盾,已废弃**——非待实现,是伪方案):**寄生的是分发不是产品**——分发路径(MCP/CLI/本地 web)+ 全部记录·接地核心**永久免费零阉割**,墙绝不加在分发路径上(加登录/额度即削零-CAC 杠杆);付费层加在分发路径**之外**,红线内候选两条(均 NEED-EVIDENCE):**(a) 商用/企业 on-prem 授权**=AGPL 双授权商用豁免 + 优先支持,把「绝不 phone home / 127.0.0.1 / air-gapped 合规」反当卖点(卖许可+支持非 SaaS、离线诚信制;**on-prem 绝不塞跨成员图,一塞即退化撞 Repowise**);**(b) 价值兑现凭证**=本机生成的拦截/工时/合规报告(挂「拦下的事故 / 省回考古工时」非功能数)。prosumer 自服务薄利档被头部放弃(Cody Free/Pro 已停、Tabnine 起步 $39)、**不做个人薄利档**;air-gapped 合规反成 on-prem 卖点(local-first 本身非护城河)。**付费墙时序闸(MUST,AND 三门)**:G1 dogfood 真拦≥1 次理由丢失型踩坑(`interceptions.md` 现 0)、G2「引真实记录 vs AI 反推」信任差值在 ≥3 人复现(纠偏:『只信 6 分』仅问卷1 N=1、非人群锚,验差值方向非「破天花板」;问卷见 `2026-06-29-G2验证问卷-信任位移+主力工具.md`)、G3 寄生分发零-CAC 飞轮成形——三门同绿前 NEVER 启;**GitHub Sponsors/赞助非付费墙、不受此闸、可即上**。**永不做:团队 SSO / 跨成员决策图 / 托管云。**② 本地模型 Qwen2.5-Coder 32B 生成≈GPT-4o,但 **agentic/检索仍逊、「RAG 追平云端」被否** → 本地 LLM 定位「接地后润色/解释」。③ 接地 eval 用 **DeepEval ExactMatch/非-LLM BaseMetric**(校引用逐字真实性,dev-only,不入核心依赖),**不接 Ragas**(LLM-judge)。**④ MCP 分层 → 第四轮已答(见下)。**

**第四轮已补(verified,`docs/discovery/2026-06-25-外部对标-第四轮.md`)· 研究弧收口**:① **MCP 路线 = 集成**——「在 MCP 之上做中间件/增强层」有现成先例(MetaMCP namespace 中间件、mcp-proxy `wrapWithProxy`),vibetrace 作 provenance 中间件与 GitHub MCP 共存,不竞争/不自建协议;新竞品 GitMCP 是 retrieval-into-context(LLM 生成、无 provenance 工具、远程)→ 留出「零-LLM 逐字 provenance + 本地」差异化。② **修正第三轮「32B≈云」**:接地条件下本地-云差距反被拉大(SWE-QA:Claude +7.10 vs Qwen32B +2.06,残 5-6 分;agentic 只云吃红利)→ 本地 LLM = 便利非对等,护城河钉「零-LLM 逐字接地**模型无关**」。③ **变现仍盲**(单人本地工具营收公开不可得 → 需一手 indie 数据)。**明确停止加轮**:四轮边际递减,剩余开放问(多 server 路由精确机制、共存 vs 赢家通吃、润色子任务实测、营收基准)需权威 spec / 一手数据。

**第五轮已补(verified,`docs/discovery/2026-06-25-外部对标-第五轮.md`)· 5 个新功能想法**(非战略弧续轮,另起功能对标):① **文件树 git-status 高亮可做**(VS Code gitDecoration + porcelain XY 确定性零-LLM,红线契合),须定位「接地入口」非 diff 查看器,默认 tooltip(可访问性)。② **只读收割命令历史/会话**有成熟先例(Pieces/SpecStory/Continue/Warp Block),作接地素材验证后做;**拒可执行内嵌终端**(Cursor 一串 CVE)+ **拒 OS 级全量捕获**(撞 Pieces;外部强 local-first 宣称被对抗验证否决 → vibetrace 脱敏+127.0.0.1 反成差异化)。③ **多模型对抗审查拒为付费产品**(撞 CodeRabbit/Greptile + 偏离护城河),留作 dev-only 验真手段。④ **code-to-course 已有(`course`)不重复立项**(DeepWiki 准确性受质疑、N=1 消费证据缺)。⚠ 想法 4/5 本轮 0 条过对抗验证(证据缺口非证伪),硬结论须另调研。

**第六轮已补(verified,`docs/discovery/2026-06-26-外部对标-第六轮-幻觉检测.md`)· 对抗式幻觉检测能否成优势 → 裁决=不力造功能**:① **多模型对抗辩论 + 完备幻觉检测 = 拒**(MAD 无可靠增益且贵、忠实检测本质需语义蕴含模型、撞 LLM-judge 满地腹地)。② 零-LLM 可守那块**本质已是现有护城河**(`ask`/`blame` 引真实 SHA/原话);唯一红线内新增 = **dev-only 逐字引用保真自检**,**并入 line 21**(本研究只收紧其诚实边界:限「逐字无据/高精度低召回」、禁「检出所有幻觉」)。③ 语义召回的**本地小 NLI(HALT-RAG ~300M)= Later/可选**(M0 允许但「有模型」、零-LLM-only 版用户价值弱证据)。⚠「零-LLM provenance flag 有用户价值」无外部直证(空白角度=未找到先例,弱证据),先验证再立项。

**第七轮已补(verified,`docs/discovery/2026-06-27-外部对标-第七轮-计划执行一致性.md`)· 计划-执行一致性评估 → 裁决=有可建功能**:① 部分完成度是成熟 peer-reviewed 概念(AgentBoard Progress Rate / OctoBench CSR / SWE-EVO Fix Rate),别宣称「没人测部分完成」。② 确定性零-LLM 部分打分先例都靠**预置 oracle**(golden patch / curated tests / 人写断言),**vibetrace 无 oracle** → 不能直接移植;语义「完成度 70%」需模型(OctoBench 也回退 3 模型 LLM-judge,R6 回声)。③ **可守空白缝 = 「AI 声称 vs git 实际」确定性偏差报告**(复用 `sessions.files_written`+git+align,报字面可数缺口,**禁**语义完成度%);竞品 Agentplane 存 intent+changed-files 但**不算偏差**=空白。直击「AI 说了没做」原始痛点。→ 见 Now。

## M1 —— 心智模型层:活架构文档

随变更增量更新的项目架构文档:每次 digest 后,用当日叙事增量修订一份
`ARCHITECTURE.md`(模块职责、数据流、关键不变量),而非全量重生成。

呈现模式借鉴 codebase-to-course:

- **代码 ↔ 人话对照**:逐模块的"这段代码在干什么"双栏视图
- **场景化测验**:从 risks / open_loops 自动生成"你还记得为什么这么改吗"
  的自检问题——把日报里埋的预测-验证闭环(risks 字段)接上验证端
- 输出仍是本地 markdown(Obsidian 原生可渲染);此处指 M1 架构文档本体走
  markdown,不另起 web 视图(M0 已有的本地优先 web 层见下文「已做」)

数据基础已埋点:M0 的 risks 字段(预测)+ usage.log(行为)。

## M2 —— 对话分析层:基于前两层的问答

"上周为什么把重试逻辑从装饰器改成显式循环?"——用叙事层(时间维度)+
心智模型层(结构维度)作为检索语料回答。明确不做向量数据库:语料是
结构化 markdown + SQLite,优先尝试关键词 + 时间 + 文件路径的确定性检索,
不够用再考虑其他方案。

## 其他候选(未排序)

- subagent / workflow 子转写纳入文件触达对齐(M0 已知限制)
- 多项目日报汇总视图(单用户,不做团队功能)
- usage.log 的自我分析:digest 行为本身的周报(数据飞轮第一圈)

## 已做 —— 本地优先 web 层(原列「明确不做」,已转向)

最初把 "Web UI / HTML 交互课程" 列为不做;实际落地时这条转了向,如实记录:

- `course`:HTML 演进课程(项目怎么长成的)
- `console` / `tunnel --serve`:本地单页 web,胶囊回答即时写回 cache.db

取舍:仍守"数据不出本机"——只绑 127.0.0.1(不 0.0.0.0),零构建单文件 HTML
(无打包、无外部依赖),且数据的单一真相源仍是本地 cache.db + Obsidian 原生
markdown(digest/brief/ask)与 JSON Canvas(graph)。web 层只是叠在同一份本地
数据上的可选视图,不是唯一入口,也不引入服务端/账号。

## 已做 —— 指令回看 `vibetrace prompts`(零 LLM)

对位「vibecoding 健忘」场景:今天让 AI 实现了一堆功能,忘了当初具体提了什么,想回看。
- `vibetrace prompts [--since "1 day ago"] [--source claude|cursor|both]`:按天/会话时间线
  列出你发给 AI 的原始指令 + 这会话改过的文件。复用 sessions/cursor_sessions 已抓的 prompts
  (采集即脱敏),零 LLM、不触网(本地 git only)、双重脱敏、degrade-never-raise;新增
  `prompts_view.py`(<100 行)。
- **commit 关联仅作「软对齐」弱提示**(align 时间窗 ±30min + 文件交集),显式标注「可能不准」,
  绝不渲染「✓已提交」—— 软对齐冒充因果会砸「对抗反推式幻觉」招牌(对抗审查定的红线)。
- 待办(v2):接 evidence 锚点做「指令→AI 当时怎么回应→落成哪个 commit」三段接地;console 第五视图。

## 决策:零-LLM 边界 + `--no-llm` 缺口(2026-06-23 多 agent 分析)

纯零-LLM **不能「完全解决」三问卷**:它守住护城河本体(确定性接地/对抗编造/隐私无 egress),
但 ask 综合答 / 周报叙事 / course 结构上需 LLM,无 key 只降级为「带 SHA 原始材料自己读」;
旗舰痛「找回 why」的高质量接地隐含依赖 enrich(要 LLM)+ 面包屑覆盖(常为 0)。
安全性:零-LLM ≠ 零风险(cache.db/vault 明文聚合、误配回退、脱敏只防 secret 模式不防业务语义、
usage.log 漏项目绝对路径)。**建设缺口:无 `--no-llm`/本地 provider 硬开关**(providers 现 4 家全云端)。
详见 `docs/discovery/2026-06-23-产品技术问答.md`。

## 发现驱动的方向修正(问卷1 · N=1 暂定)

来源:`docs/discovery/gap-analysis-问卷1.md`(已过 4 视角对抗复审,minor-revision)+
`docs/discovery/修正意见-问卷1.md`。**均为单样本暂定**,升为排期前须过三道门:
① 后续问卷统计「主力 AI 工具 + 占比」 ② 同一痛点 ≥3 人复现才升人群结论
③ dogfood 拦截实验,以「真拦下一次理由丢失型踩坑」(对位积分 `floor→round` 超发)为最硬指标。

- **入口 wedge** 用「理解旧代码 / 这段当初为什么这么写」(已上线 ask/graph,用户有 pull);
  决策捕获 / 留痕做「用着自然沉淀」的后端,不要求用户先认同「记录决策」的价值。
- **接地语料权重**:PR 讨论 + 测试用例 + 需求文档是用户「找回为什么」最强、跨问卷复现的来源
  → 列为待评估的接地语料(超出当前 commit + 会话);Cursor 源是单人偏好 + 已在 PR#29 实现,
  定位「验证占比 + 评审合并」,非新建。
- **核心叙事**主打零-LLM `blame` / 接地引真实 SHA「对抗反推式幻觉」——用户对 LLM 重解释 why
  只信约 6 分(问卷1·N=1 真实打分,非人群锚;问卷2/3 查无打分,待 ≥3 人复现)、警惕「反推式编造」;不承诺「AI 帮你找回 why」。
- **功能边界**:不与 Cursor 抢「生成 / 检索」(用户认可),只补「why / 决策接地」缝隙。
- **胶囊回面**解决可发现性 ≠ 解决优先级博弈;指标用「回面后实际处理率」而非「回面率」;
  到期时附「风险已 / 即将成事故」的证据才撬得动。
- **本地优先的诚实边界**:存储 / 缓存 / 产物本地 + 脱敏,但富集 / ask / 叙事仍把(脱敏后的)
  会话与 diff 发往云端 LLM(默认 deepseek),非本地推理;定位为「零摩擦被动加分项」而非
  无条件卖点;补「读了哪些会话 / 脱敏命中」的可审计视图。
- **范围取舍**:用户自排最痛是 需求变更 > 环境问题 >(代码理解);vibetrace 聚焦其第三痛
  属合理取舍但**非最痛项** —— 需求变更 / 环境问题列入下方「明确不做」。
- **候选补充**:「挖地雷」连锁改动的**回溯式影响清单**(graph / 全局引用,已有接地能力,可做;
  区别于超 M0 红线的预测式影响分析)。

## 发现驱动的方向修正(问卷2 · N=2 暂定)

来源:`docs/discovery/gap-analysis-问卷2.md`(已过 4 视角对抗复审,minor-revision)+
`docs/discovery/修正意见-问卷2.md`。**N=2 仍非人群**;凡「2/2 复现」读作「双样本复现、待 ≥3 升级」。
升排期前须过三道门:① 后续问卷统计「主力 AI 工具+占比」 ② 同痛 ≥3 人复现才升人群结论
③ dogfood 拦截/命中实验(以「真拦下一次理由丢失型踩坑」+「ask/blame 对真实案例实际命中」为最硬指标)。

- **头号发现:主力工具反转**。问卷2 主力 = Claude Code,问卷1 = Cursor → N=2 各 1,**出现 1 个反例,
  提示不能默认单一主力,但不足以证伪人群分布**。主力工具占比为待 N≥3 验证的头号开放问题;
  问卷3 必抽「主力 AI 工具+占比」。
- **多项痛点由 N=1 升 N=2(仍 <3,不升人群)**:why>what、手工留痕必崩、TODO 沦噪声、量化返工、
  周报考古、挖地雷、隐患成真、主动找 decision-memory 工具并弃用 —— 均双样本复现、暂定 N=2。
- **护城河:实测被坑事件(行为层 N=1)+ 态度警惕(N=2)**。问卷2 贡献「贴回 Claude 重解释编『内存优化』、
  真因『流式响应不断连』、损失 2h、方向走偏」的具体事件 → 做「blame/ask 引真实原话 vs LLM 重解释」对位演示;
  对外不可暗示「两人都被坑过」(硬实证仍是 N=1)。
- **护城河诚实边界(新增)**:四条接地人证均以「接地源仍存在」为前提;会话被清理时(问卷2 Flask 那段已发生、
  花近 3h 放弃重写)零-LLM 接地同样无源可接 → 验证项:接地源留存率/会话过期对命中率的影响。
- **agent-seed 写时捕获**:痛点(手写留痕必崩)有证据 N=2;**解法(写时捕获被接受)是 N=0 假设**,
  且他对「需额外动作的工具」弃用率 100%(ADR/Notion/脚本)→ 不标强项,入 dogfood 验证。
- **commit-trailer 落点**:用户认可「人写的注释+commit 正文」持久(方向弱支持),
  **未直接背书产品「自动写入 trailer / SHA 为键缓存」机制** → 机制接受度待验证。
- **新机制(N=1):AI 跨语言搬运丢 why 注释**(2048 真因在 Python 原型注释、AI 翻 Go 丢失)。
  注意:真因在原型注释 = 出 vibetrace 摄取源,会话仅能定位「注释被丢」非给出真因。
- **capture-source 对「不分版」工作假设的影响**(注:仓内无成文 doctrine,系工作假设):双源都做实但
  ① Cursor 源 **opt-in 默认关闭**(`config.py` sources=["claude"]),非「开箱对等覆盖」,主力 Cursor 用户需手动启用;
  ② **接地质量非对称、与样本量无关**(Cursor 上下文文件漂白风险、对齐更松、composerData schema 非官方;
  #30 已部分缓解)→ Cursor 源需更强置信度护栏,**不可读成「统一就行」**。N=2 不构成分版触发(仍需 N≥3)。
- **回溯式改动影响面**:graph 是**决策影响图**(决策 commit→下游碰同一文件的 commit),
  **≠ 调用面引用回溯**;后者由现有 IDE/LSP find-references/ripgrep/go test 覆盖,**vibetrace 不新建**;
  预测式影响超 M0 红线不做。
- **付费/隐私收敛**:问卷2「会认真考虑」= 条件式弱意向 N=1(非实付),挂尚未对位的周报形态 → 待验证变现假设;
  隐私 N=2 未复现但其无顾虑可能源于主力本地 Claude Code 未触发出网,**不与问卷1 强顾虑对消为人群中性**,列开放项。
- **明确不做(他排第一最痛也不做)**:相机固件变更(硬件不可模拟)、IDE 输出截断、Helm 配置、
  AI 生成时保注释(生成域),均超 M0 红线/非本品域。vibetrace 服务其排第三的「代码理解/为什么这么写」(合理取舍,非最痛项)。
- **产品事实已推进(勿当新机会)**:Cursor 源(merged,opt-in)、会话原话接地(#30)、本地测试接地(#34)、
  PR 讨论接地(#32 opt-in)、纯 stdlib MCP server 均已落地;对问卷2 此人 why 真源现有能力已基本覆盖
  (除原型注释出域、会话被清理无源两类)。

## 发现驱动的方向修正(问卷3 · N=3 关键里程碑 · freelancer/外包 · 主力 Claude Code)

**里程碑:N=3 首次跨越人群门槛。** 10 条核心痛点真 3/3 复现、升「人群结论」——vibetrace 核心命题在人群层成立。**全部附代价分层口径锁**:问卷3 是低后果 freelancer(踩坑代价分钟级/客户反馈),商业影响远小于问卷1(¥3万)/问卷2(产线/OOM),三者不可等同;升排期须各自可复算成本证据。

- **可升人群(3/3 population-now)**:① 决策 why > 代码 what;② 手工留痕靠意志力必崩(问卷3 独有根因=载体随栈失效 Java Javadoc→Python 无);③ TODO 沦噪声、回头处理约 1/3(根因=优先级博弈);④ 因来由不清返工(仅机制升,代价 ¥3万/3h/分钟级分层不可等同);⑤ 主动找过 decision-memory 工具并弃用(弃用原因=不准/编造/隐私/麻烦);⑥ 竞品/AI 反推式重解释会编造(**竞品/态度层 3/3;编造致可量化损失硬实证仍 N=1 仅问卷2**);⑦ 周报/汇报考古最难拼「为什么」(问卷3 新增跨项目易混维度);⑧ 改动连锁挖地雷(**群体结论=回溯式引用查找属 IDE/grep/test 覆盖,vibetrace 不新建**);⑨ 隐患预感成真;⑩ 明知单决策该记却赶时间没记(单决策一次性遗漏,不同于持续习惯崩塌)。
- **仍 2/3 双样本暂定**:隐私本地优先(问卷1+问卷3,机制异质但同强,不可与问卷2 弱对消成中性)、隐私在 Deadline 失守(原误升 3/3 已降回)、多项目切换上下文丢失。**1/3 不升**:读对话≫读代码(divergent)、AI 跨语言搬运丢注释、拥有感低。
- **主力工具 = Claude Code 2 : Cursor 1 → 维持双源并行不分版**。默认 sources=['claude'] 对当前 2/3 零配置命中;Cursor 主力(问卷1)需 opt-in。
- **ICP 分层(不收窄/不盲拓)**:命题跨 ICP 普适(3/3),故服务全体;定位/变现按后果分层(高后果生产挂防事故 / 低后果 freelancer 防事故话术无力,只可能挂客户代码隐私)。freelancer 细分仍 N=1、**付费触发查无**,须 ≥3 freelancer + 真实付费信号才升。
- **产品事实修正**:跨项目聚合已 merged(distinct_projects/build_overview/watch/self_report)= 增量非从零;本地/可关 LLM 选项是真建设缺口(config 仅 deepseek/openai/qwen 云端)。
- **超域不做**:文件编码乱码(问卷3 自排第一头号痛,但属 IO 域)、Swing 布局、回溯式引用查找、AI 截断/硬件、本地备份缺失。

## 明确不做

- RAG / 向量检索 / 嵌入
- 团队功能、跨用户数据飞轮
- 需求变更管理、环境/配置排障(用户更痛但超产品范围;只做「代码理解」这块可被工具改善的)
