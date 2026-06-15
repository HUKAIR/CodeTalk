# vibetrace 产品端构思建议:基于 10 个 AI 产品流的拆解

> 立场前提:vibetrace 是本地优先的开发者编码认知层。下文所有建议都已过一遍"慢科技 / 隐私不出本机 / 数据人文主义"三道红线。能本地算的绝不出网,LLM 调用走统一 `llm.py`,缓存前对 secret 脱敏。

---

## 1. 跨产品模式总结

### 日常化(让人每天回来)
- **把"回看"做成被动到达,而非主动想起。** 不靠用户自律,靠定时推送把"过去的自己"端到面前。出自:Day One(On This Day 每日回流)、Limitless(每晚 briefing 邮件)、Oura(晨间 Readiness 通知)、Readwise(Daily Review 邮件)。
- **寄生在一个已有的高频固定动作上。** Onboarding/触发不新增动作,而是绑死在用户本来就会做的事上。出自:Granola(绑在"会议开始")、Oura(绑在"睡觉")、Granola Briefs(绑在"下一场会前")。
- **用"反向激励/隐性反馈环"让日常行为本身变得有意义。** 今天的每个动作都在为未来的一次高光回报投票。出自:Spotify Wrapped(多听=更好年报)、Duolingo(streak 损失厌恶,但要警惕其虚荣化)。

### 便捷化(降低进入摩擦 / 零等待)
- **零配置、数据已就绪、点开即成品。** 没有 onboarding 表单,后台静默采集,首屏即产品本体。出自:Spotify Wrapped(全年静默采集)、Perplexity(首屏即搜索框)、Granola(纯设备端后台收音)。
- **产出顺着既有工作流流出去,而非困在工具里。** 一键发 Slack / 同步 CRM / 导出 Obsidian / 暴露 MCP·CLI 给外部 agent。出自:Readwise(MCP+CLI 进终端)、Granola(一键 Share/CRM)、Limitless(开放 API + Obsidian 增量同步)、Perplexity(Comet/Slack/本地文件)。
- **统一入口 + 命令面板,把"功能发现 + 执行 + 教学"压成一个无摩擦交互。** 出自:Linear(Cmd+K 旁标快捷键的渐进教学)、Readwise(全键盘 j/k 流)。

### 互动化(从单向消费到双向对话)
- **被动产出可被"打断追问"。** 把单向看/听改造成随时 Join 进去问。出自:NotebookLM(Audio Overview Interactive Mode 点 Join 点名你)、Granola(会中 CMD+J Ask)、Perplexity(Thread 内 follow-up 不重述背景)。
- **"追问链":系统替你预生成下一个问题,点一下就深入。** 出自:Perplexity(Related questions)、NotebookLM(Mind Map 节点内追问)、Readwise(Ghostreader 连续追问)。
- **对话式脚手架对抗"空白页/流水账"——AI 先抛追问,你答完它再合成。** 出自:Day One(Daily Chat / Go Deeper "那让你感觉如何")、Duolingo(Explain my Answer)、Oura Advisor(给小步骤而非统计)。

### 可视化(把数据翻译成可读叙事)
- **单一压缩指标 + 一句行动叙事,30 秒给决断,而非数据墙。** 出自:Oura(0-100 Readiness 圆环 + "该冲还是该歇")、Spotify(Listening Age/Clubs 把数字变身份)。
- **渐进式披露(Stories 范式):全屏竖卡逐张 swipe,靠悬念维持注意。** 出自:Spotify Wrapped、Duolingo Year in Review、Day One。
- **信任分层可视化:区分"确凿事实"与"AI 推断"。** 出自:Granola(黑字人写/灰字 AI 补的双色合成)、NotebookLM/Perplexity(行内引用角标)。
- **可下钻、可操作的可视化,而非只读报表。** 图表点进去看底层数据并就地改状态/钉为洞察。出自:Linear(Insights 下钻到 issue)、Readwise(Highlight-Graph 概念图)。

### 深度化(从浅表记录到洞察沉淀)
- **每句生成内容可一键跳回原始证据(source-grounding 契约)。** 这是 10 个产品里出现频率最高的"signature 级"原则。出自:NotebookLM(行内引用定位原文)、Perplexity(结构性预分配引用)、Limitless(sourced answer with timestamps)、Granola(🔍跳回转写)。
- **纵向综合:把跨时间的零散记录合成一段"长期故事线",而非逐条并排。** 出自:Day One(AI Multi-Entry Summary 跨年同一天)、Granola(agentic Chat 跨数月综合)、Spotify(全时段 Recall)。
- **间隔重复 / 主动召回把"被动消费"逼成"主动记忆"。** 出自:Readwise(Daily Review + Master 闪卡半衰期 + Quiz)。
- **persona 文件做下游个性化的统一锚。** 出自:Readwise(`reader_persona.md` 喂所有 skill)、Oura/Day One(Memories 跨会话记住偏好)。

---

## 2. vibetrace 的五维诊断

| 维度 | 现状位置 | 判断依据 |
|---|---|---|
| **日常化** | **弱(最大短板)** | 有 markdown 日报写入 Obsidian,但属于"写完即沉底"的被动资产。没有任何"被动到达"机制把用户拉回来——用户得自己想起来去看。这正是记忆层产品最致命的留存漏洞:"生成了但没人回看"。 |
| **便捷化** | **中等偏强** | 本地优先天然有零延迟、零等待、零配置优势。读 git+会话是后台寄生在既有动作上。但产出目前只落地 Obsidian 单通道,缺统一入口(命令面板)和对外接口(MCP/CLI 让 Claude Code 反查自己的记忆)。 |
| **互动化** | **弱** | 3D 时光隧道是纯被动回看,localStorage 只记已读/胶囊答案。没有"在某节点 Join 进去追问"的能力。这是与"认知层"定位差距最大的一环——叙事是单向播出的,不能被追问。 |
| **可视化** | **强(差异化优势)** | 五幕体验链 + 像素终端 3D 隧道已经是 10 个产品里少有的、把回看做成"空间化仪式"的实现,远超 Linear 在"长期叙事回看"上的留白。但缺两样:信任分层(事实 vs AI 推断不分色)、节点可下钻(点节点看底层 diff/会话原文)。 |
| **深度化** | **中等** | 已有"做了什么/为什么/决策/风险/未闭环"五字段叙事,risks 字段=预测-验证埋点,理念上已触及深度。但缺三块:(a) 每句叙事的可点击溯源(source-grounding 契约);(b) 跨时间的纵向综合(同模块演进史);(c) 把回看时的人工批注/决策理由回写进记忆层。 |

**一句话诊断:** vibetrace 的"可视化"已是壁垒,"深度化"理念领先但工程未落地;真正拖后腿的是**日常化(没人被拉回来)和互动化(回看不能被追问)**——这两条不补,再好的隧道也只是个会被遗忘的精美摆设。

---

## 3. 建议路线图

> 排序原则:先补致命短板(日常化),再补与"认知层"定位差距最大的(互动化),最后在已有优势上加深(可视化/深度化)。便捷化的几项作为底层基建穿插。

### 日常化

**[路线图 #1 — 下一步该做的 1/3] 开工简报(Boot Brief)**
- **做什么:** 检测到 git/Claude Code 会话恢复(或每天首次打开编辑器/隧道)时,主动推一份本地通知 + 写入当日 Obsidian 笔记:"你上次停在哪——改了哪些文件、有哪些未提交的意图、上次会话留下的 TODO/疑问、建议的下一步"。
- **借鉴谁:** Granola Briefs(会前主动喂)+ Limitless(每晚 briefing 被动到达)。
- **为什么适合 vibetrace:** 把日报从"回头看"翻转成"开工前喂"——这是把日记型工具变成日常习惯型工具的唯一关键翻转,直接补上最大短板。且全是本地数据重组,不出网。
- **落地代价:小。** 复用现有叙事生成 + 一个本地通知/Obsidian 写入钩子。

**[路线图 #2 — 下一步该做的 2/3] On This Day for code(往年今天回流)**
- **做什么:** 每天本地推送"N 周前/上个迭代/半年前同一天你在做什么",回流当时的变更叙事,并在 3D 隧道里把这段过去高亮"端到面前"。
- **借鉴谁:** Day One(On This Day + AI Multi-Entry Summary)、Spotify(全时段 Recall)。
- **为什么适合 vibetrace:** 100% 本地数据重组,完美契合"回看仪式 + 慢科技"理念,把日报从"写完即沉底"变成"持续返还价值"。是数据人文主义最纯正的表达。
- **落地代价:小。** 纯本地查询既有叙事缓存,按日期检索即可,无需 LLM。

**[路线图 #6] 编码 streak 的空间化损失厌恶(克制版)**
- **做什么:** 在 3D 隧道里把"有意义叙事的日子"渲染成发光段、"空白日"渲染成暗区/缺口。**不**奖励"每天提交"(避免垃圾 commit),只可视化连续性,不做内疚式 push、不做 Energy 式稀缺。
- **借鉴谁:** Duolingo(streak 视觉化)——但**只取视觉、剔除其虚荣化与胁迫机制**。
- **为什么适合 vibetrace:** 空白会本能地想被填补,是温和的隐性激励,符合慢科技。
- **落地代价:小。** 纯前端渲染,复用已有隧道引擎。

### 便捷化

**[路线图 #5] Cmd+K 命令面板 + Search/Ask 两档分流**
- **做什么:** 统一入口模糊搜索跨"commit 叙事 / 日报 / 某天 / 某文件 / 某 session",每条结果旁标快捷键。检索分两档:"我记得改过 auth 逻辑"走**纯本地关键词/路径检索**(零 LLM、零 token、即时跳转);只有"上周为什么放弃那个方案"才调 Claude。
- **借鉴谁:** Linear(Cmd+K 渐进教学)、Limitless(Search vs Ask AI 两档)。
- **为什么适合 vibetrace:** 两档分流既省 token 又快,贴合 M0 标准库红线;命令面板用标准库即可实现,无需引入框架。
- **落地代价:中。** 命令面板小;关键词检索小;Ask 档复用 llm.py。

**[路线图 #8] 暴露 vibetrace MCP/CLI(让 Claude Code 反查自己的记忆)**
- **做什么:** 把编码记忆暴露成 MCP server / CLI,让 Claude Code 在编码时反过来查询"这个 bug 上次怎么引入的""这个模块的决策史"。
- **借鉴谁:** Readwise(MCP+CLI 进终端)、Limitless/Granola(开放 API/MCP)。
- **为什么适合 vibetrace:** 本地数据红线下形成闭环——记忆既是给人看的,也是给 agent 用的底座。已读 Claude Code 会话,天然契合。
- **落地代价:中。** M0 仅标准库+SDK,MCP 可放 M1。

### 互动化

**[路线图 #3 — 下一步该做的 3/3] 3D 时光隧道里的 Interactive Mode(节点追问)**
- **做什么:** 在隧道任一时间节点"点 Join",用自然语言追问"我当时为什么这么改""这次重构动了哪些模块",系统基于该时段的 commit+会话即时作答后回到回看流。同时每个节点旁预生成 3 条"相关追问"(追问链),点一下即深入。
- **借鉴谁:** NotebookLM(Audio Overview Interactive Mode 点 Join)、Perplexity(Related questions 追问链)、Granola(agentic Chat 跨时间提问)。
- **为什么适合 vibetrace:** 把单向回看变双向对话,这是从"回看工具"升级为名副其实"认知层"的决定性一步,补齐与定位差距最大的短板。
- **落地代价:中。** 追问走 llm.py;隧道前端加交互层;上下文是已有的 commit+会话切片。

**[路线图 #7] 收工对话式脚手架(Daily Chat for code)**
- **做什么:** 收工时不直接生成日报,AI 先基于今天 git diff + 会话抛 2-3 个 Go Deeper 式追问("为什么放弃了 X 方案?""这个 bug 的根因你确认了吗?"),开发者简短回答后再合成叙事——把 **diff 里没有的"决策与权衡"**沉淀进记忆层。
- **借鉴谁:** Day One(Daily Chat / Go Deeper)、Oura Advisor(给小步骤)。
- **为什么适合 vibetrace:** "为什么"是开发者记忆最该捕获却最易丢失的部分,diff 永远捕获不到。这正是 vibetrace"决策"字段的真正活水来源,且回写形成认知复利。
- **落地代价:中。** 追问+合成走 llm.py;回写按 session_id+last_msg_ts 增量。

### 可视化

**[路线图 #4] 叙事信任分层(事实 vs AI 推断双色 + 每句可溯源)**
- **做什么:** 生成变更叙事时把"确凿事实(diff/commit 实际发生的)"与"AI 推断的意图/why"用视觉区分(类比 Granola 黑/灰);**每段叙事挂可点击证据角标**,一键跳回对应 commit SHA / diff hunk / Claude 会话消息。
- **借鉴谁:** Granola(黑灰双色)、NotebookLM/Perplexity/Limitless(source-grounding + sourced answer)。
- **为什么适合 vibetrace:** 这是 10 个产品里出现频率最高的 signature 原则,直接对抗 LLM 幻觉、建立信任,完美契合"SHA 为键"缓存约定和容错红线。隧道节点也因此天然变成"可下钻锚点"。
- **落地代价:中。** 双色是 prompt 工程 + 前端样式;溯源需在生成时记录证据指针(SHA/行号/消息 ID),与现有缓存键天然对齐。

**[路线图 #9] 隧道节点可下钻**
- **做什么:** 每个隧道节点可点进去看底层 diff/会话原文,并就地"标记为洞察/钉到沉淀"。
- **借鉴谁:** Linear(Insights 下钻 + 就地操作)。
- **为什么适合 vibetrace:** 把只读回看升级为可操作的认知沉淀,正是 Linear 在"长期叙事回看"上的留白,vibetrace 的差异化主打。
- **落地代价:小。** 依赖 #4 的证据指针,前端展开即可。

### 深度化

**[路线图 #10] 模块演进史(AI Multi-Entry Summary for code)**
- **做什么:** 把"同一模块/功能在多个时间点的变更叙事"用 Claude 合成一段纵向故事线——"你在 auth 模块这三个月的演进:快速原型→加测试→重构出抽象"。缓存按 `module+时间窗` 为键增量算。
- **借鉴谁:** Day One(signature move:Multi-Entry Summary)、Granola(跨月综合)。
- **为什么适合 vibetrace:** 比逐条日报有用得多,直接产出"认知层"而非流水账,是 vibetrace 深度化最该落地的一招。
- **落地代价:中。** 合成走 llm.py;纵向数据是已有叙事的重组。

**[路线图 #11] dev_persona.md + 间隔重复式决策召回**
- **做什么:** (a) 从 git+会话推断 `dev_persona.md`(常踩的坑/偏好架构/正在攻坚的模块),下游日报/回看据此个性化;(b) Daily Recall——用间隔重复推送"你 N 天前定下的关键设计决策/踩过的坑",可"discard / master(钉成长期决策卡)"。
- **借鉴谁:** Readwise(`reader_persona.md` + Daily Review 半衰期 + Quiz)。
- **为什么适合 vibetrace:** persona 全本地计算;间隔重复天然适配"哪些旧决策该被提醒",把记忆层升级为主动召回的认知层。
- **落地代价:中。**

### 优先级总览

| 优先级 | 路线图项 | 维度 | 代价 |
|---|---|---|---|
| **下一步 #1** | 开工简报 Boot Brief | 日常化 | 小 |
| **下一步 #2** | On This Day for code | 日常化 | 小 |
| **下一步 #3** | 隧道 Interactive Mode 节点追问 | 互动化 | 中 |
| P1 | 叙事信任分层 + 每句可溯源 | 可视化/深度化 | 中 |
| P1 | Cmd+K 命令面板 + Search/Ask 两档 | 便捷化 | 中 |
| P2 | 收工对话式脚手架 | 互动化/深度化 | 中 |
| P2 | 模块演进史综合 | 深度化 | 中 |
| P2 | 隧道节点可下钻 | 可视化 | 小 |
| P3 | streak 空间化(克制版) | 日常化 | 小 |
| P3 | dev_persona + 决策召回 | 深度化 | 中 |
| P3 | vibetrace MCP/CLI | 便捷化 | 中 |

**为什么是这 3 件:** #1/#2 用最小代价(纯本地、复用现有叙事)直接堵住最大短板"没人被拉回来";#3 用中等代价补上与"认知层"定位差距最大的"回看不能被追问"。三件做完,vibetrace 就从"会被遗忘的精美隧道"变成"每天被拉回来、能对话追问的认知层"。

---

## 4. 要警惕的反模式(不能抄)

1. **内疚式 / 胁迫式 push 通知(Duolingo 绿猫头鹰"Don't let Duo down")。** 违背慢科技。vibetrace 的触发应是"帮你回忆今天写了什么",而非"逼你回来"。通知要可一键静音、默认低频。

2. **反向稀缺设计(Duolingo Energy 系统:答对也扣、逼向付费)。** 这是把摩擦故意造出来的反人文设计,与"数据人文主义"和"为开发者服务"直接冲突。明确作为反面教材。

3. **streak 的虚荣化陷阱——奖励"每天提交"。** 会诱导垃圾 commit 污染记忆质量。只奖励"连续产生有意义的叙事",且 streak 仅作温和视觉提示,不作沉没成本胁迫。

4. **"为分享而生的病毒工件"凌驾于真实价值(Spotify Wrapped 把因果倒过来:先定要发 Instagram 的卡再造体验)。** vibetrace 可以做"Dev Wrapped"身份卡,但**不能为了可炫耀性牺牲真实性**——开发者身份标签必须诚实,不能为传播做夸大归类。且分享必须用户显式触发,默认数据不出本机。

5. **任何"数据出本机"的便捷化(Limitless/NotebookLM 的云端处理、公开 notebook、可分享链接默认上传)。** 这是硬红线。云端处理一律不抄。即使做分享卡片,也必须本地渲染、用户显式导出,并在产出上明示"全部本地生成,数据未离开你的机器"——把隐私本身做成卖点(Granola"不打扰、后台干活"的更强版本)。

6. **黑箱式 AI 总结(无溯源的"可能编造的助手")。** 凡是自动生成的叙事都必须能跳回原始证据(#4),且事实与推断分色。这既是反幻觉,也契合容错红线——AI 推断部分即使错了,用户一眼可辨,不会盲信。

7. **过度产出 / 信息墙(NotebookLM 的 Studio 十几种产出、Oura 的数据墙反面)。** 违背 Simplicity First 和单模块<300 行。不要一上来铺十几种卡片;用 Oura"one big thing"哲学——每个时段只给一张最重要的卡。多产出格式(播客/视频)在 M0 一律不做。

8. **引入重型依赖追求"全量捕获"(Rewind 全屏录制)。** vibetrace 只读 git + Claude Code 会话,不抄"录一切"——既是隐私考量,也是 M0 标准库红线。全量屏幕/音频捕获是范围蔓延,出现即违反 Simplicity First。