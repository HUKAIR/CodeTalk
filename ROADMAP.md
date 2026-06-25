# ROADMAP

三层愿景;M0(变更叙事层)已交付,以下仅记录方向,不代表排期承诺。

## 外部对标驱动的缺口与排期(2026-06-25,两轮 deep-research)

来源:`docs/discovery/2026-06-25-外部对标-codereview与UX.md`(第一轮)+ `2026-06-25-外部对标-第二轮.md`(第二轮)。
按 Now/Next/Later 排,标红线。**本会话已落地**(PR #51/#52):FTS 回填、2 字中文 LIKE 召回、接地覆盖徽标(粗)、
MCP review-time 描述、console 内嵌接地对话 dock + 行/决策节点原地追问、enrich 覆盖补全命令、**MCP 参数对齐(Top3-①)、
`vibetrace review` 零-LLM review 入口(Top3-②)、引用 hover 预览+PR 跳源(Top3-③)**。以下是**仍缺的**。

**Now(低成本 / 红线内 / 高 ROI)**
- **引用核验加 hover 预览 + 点击跳真实源**(对齐 GitLens hover-card 范式;现仅可点开)。[R2 · UX]
- **定位文案收窄**:复合护城河(零-LLM 确定性 + 逐字真实原话 + 自动挖掘非手写 + 本地);一句话「别人要你手写 why,vibetrace 自动从真实记录挖」。弃用泛「接地对抗幻觉」(已被 GitKraken/Context7/GitHub MCP 占用)。[R2 · 定位]
- **MCP 对齐参数词表 + 集成层定位**(✅ 已落地 PR #52):保留独占 `vibetrace_*` 工具名,blame/ask 加可选入参别名 **path/startLine/endLine**(owner/repo 等收下即忽略),定位「GitHub MCP 之上的零-LLM why 增强层」。⚠ 不可改名成 get_diff/get_commits(GitHub MCP 真名是 get_commit/list_commits/pull_request_read,改名会撞名+丢 why 护城河)。注:实读仅 path/startLine/endLine,未收 sha/pullNumber(不映射 blame 的 file:line 口径,避免静默给错答案)。[R2 · 集成,对抗复跑核实]
- **接地命中率自证**(dogfood)✅ 已跑(`scripts/grounding_hitrate.py`,`docs/discovery/2026-06-25-接地命中率自证.md`):CodeTalk 覆盖上限 **92.3%**(72/78,叙事+面包屑)→ green-light review-entry 扩面/grounding-eval。**诚实缺口:evidence 会话原话锚点 0%**(enrich 用空会话对齐、早期 digest 未留 evidence)→ 文案暂不讲「引真实会话原话」;补法见下 Next。[R1 open Q · 数据]
- **(Next)补 evidence 会话原话覆盖**:会话在场时跑 digest 富集让 `_evidence` 收割原话锚点,或给 `enrich` 加可选会话对齐(当前 align([]));复跑 grounding_hitrate 看 evidence 列转非零。

**Next(需设计 / 验证)**
- **review 工作流入口**:粘 PR/diff → 对每个改动块自动 blame「这些行历史决策 + 真实引用 + 置信度」(交互链 B)。⚠ 撞 CodeRabbit/Greptile 腹地,先验证确定性引原话命中率;差异化靠逐字 + 本地。[R1 链B + R2 MSR2026 · 能力]
- **接地质量可验收(已对抗复跑改 scope)**:⚠ 原「字符串 n-gram 逐句归因 + τ 三标签」经三视角 + 本仓 fixture 实测**证伪**(对 LLM 忠实释义假阴、对因果错配幻觉失明;字符串恒等 ≠ Trust-Score 语义蕴含)。改做:答案里**逐字命中材料的片段**高亮 + 链回确定来源(字符串恒等只在逐字子串处成立)+ 保留粗徽标 + 点开核验;**不打 grounded/inferred/unsupported、不设 τ**。文案不可宣称「答案满足 Trust-Score / 零幻觉」,只讲「引用是可核验真实逐字记录」。[R1 SO/Uber + R2 Trust-Score · 对抗复跑修正]
- **面包屑 schema 借 Lore 扩**:加「被否决的备选 / agent 指令 / 验证元数据」+ git-adr 式 commit-link 行级锚定;加 MADR/Nygard 导出降团队迁移摩擦。[R2 · 能力,红线内]
- **富集覆盖自动维护**:enrich 现为一次性,新 commit 仍只在 digest 窗口富集;考虑 digest 收尾自动补未覆盖项。[本会话 Vibe-Watch]

**Later / 待评估(成本高或须红线权衡)**
- **IDE 扩展(VS Code:gutter blame + CodeLens「为什么这么写」+ hover 真实原话)** 作第二分发面,最贴 review 现场。⚠ 须权衡 M0 红线(禁重前端构建链)+ 维护成本。[R2 · UX/分发]
- **本地 on-device LLM provider(Ollama 等)**:让「可选本地 LLM」从口号变能力(数据不出本机更彻底);⚠ 能力上限待第三轮基准。[R1/R2 缺口]
- **chat 流式 JS 抽共享**:console/web_chat 现两处重复;按「第三处消费者才抽」阈值,未触发即不抽(避免不可验证的浏览器重构)。[本会话 #2]

**红线警示(守 / 拒)**
- MCP provenance 赛道拥挤(GitHub MCP / codebase-memory-mcp 14.2k★)→ **倾向集成**(做其上的 why-provenance 增强层),不拼结构化代码图谱(撞 codebase-memory-mcp 腹地)。[R2]
- local-first 与「接地对抗幻觉」**非护城河 / 已被占用**,不当主卖点。[R1/R2]

**第三轮已补(verified,见 `docs/discovery/2026-06-25-外部对标-第三轮.md`)**:① 变现=**open-core 按席位 + 私有库/团队治理(SSO)作付费闸门、核心免费 OSS**;prosumer 自服务薄利档被头部放弃(Cody Free/Pro 已停、Tabnine 起步 $39)、air-gapped 已入门标配(local-first 再证非护城河);**不做个人薄利档**,重心团队治理/企业 on-prem。② 本地模型 Qwen2.5-Coder 32B 生成≈GPT-4o,但 **agentic/检索仍逊、「RAG 追平云端」被否** → 本地 LLM 定位「接地后润色/解释」。③ 接地 eval 用 **DeepEval ExactMatch/非-LLM BaseMetric**(校引用逐字真实性,dev-only,不入核心依赖),**不接 Ragas**(LLM-judge)。**④ MCP 分层/「在 GitHub MCP 之上做增强层」先例仍盲 → 留第四轮。**

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
  只信 6 分、警惕「反推式编造」;不承诺「AI 帮你找回 why」。
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
