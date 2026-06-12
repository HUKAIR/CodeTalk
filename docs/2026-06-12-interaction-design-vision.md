# vibetrace 交互层产品设计:从"日报工具"到"开发者回忆录"

> 2026-06-12 · 产品视角设计文档(M1 输入)。参照系不取自开发者工具,
> 取自数据人文主义、个人数据叙事艺术与慢科技设计——因为 vibetrace
> 要解决的"理解债"本质不是信息问题,是**记忆与作者身份**问题。

## 一、重新定位:产品到底在卖什么

M0 的措辞是"日报/digest"——这是审计语言,把用户放在"被汇报者"的位置。
但真实的情感任务(emotional job-to-be-done)是:

> **AI 时代,代码还是你的,但"写它的记忆"不再是你的。
> vibetrace 把作者身份还给你。**

对照艺术界最有力的先例:Nicholas Felton 在父亲去世后,用他留下的
4,348 条个人记录做了一份"年报"——只用数据拼出一个人的肖像(Feltron
2010 Annual Report,被 MoMA 收藏)。vibetrace 做的是同构的事:
**用 commit 与会话的痕迹,为"正在和 AI 共同写码的你"持续作传。**

定位语:~~开发日报工具~~ → **本地优先的开发者回忆录(memoir engine)**。

## 二、三条设计原则(各有艺术界出处)

1. **数据人文主义,而非仪表盘**(Giorgia Lupi《Data Humanism 宣言》/
   Dear Data 项目)
   - 拥抱不完美与近似:叙事允许"材料不足",置信度 high/low 直接呈现
     为视觉语言(实线/虚线),不假装全知
   - 数据要连回故事与人:每条叙事必须引用"你当时的原话"
   - 反面清单:不做生产力图表、不做 streak 打卡、不做效率评分——
     这是慢科技(Slow Technology, Hallnäs & Redström)的立场:
     **为反思而设计,不为效率而设计**

2. **仪式,而非功能**(Spotify Wrapped / Day One "On This Day")
   - Wrapped 的成功公式:数据 → 身份 → 可分享的叙事,一年一次的
     期待感。功能没有期待感,仪式有
   - Day One 用户续订的头号理由是 On This Day(记忆回流),
     不是写日记本身——**回看才是黏性,记录只是手段**

3. **诗意计算,而非报表语言**(School for Poetic Computation)
   - 叙事用第二人称信件体:"这周你否决了 LangGraph,因为……"
   - AI 是合著者不是审计员;文案口吻 = 一位与你结对过的同事
     在帮你回忆,而非系统在汇报

## 三、产品形态:三种节奏的仪式(取代"一种报告")

| 节奏 | 仪式 | 形态 | 艺术参照 |
|---|---|---|---|
| **日** | 晚祷(evening recall) | 纯 markdown 信件,≤3 句 + 1 个"今日决定" | 慢科技:一杯茶的长度 |
| **周** | 给自己的明信片 | 单文件 HTML/SVG 卡片:一周只选**一个**手绘风度量(如"本周你说'不'的 5 次")+ 一段手写体叙事 | Dear Data:一周一题,一张明信片 |
| **月/年** | Code Wrapped 个人年报 | 单文件交互 HTML,scrollytelling:身份卡("本月你是守门人/拓荒者")、决策地图、被否决方案陈列馆 | Feltron 年报 + Spotify Wrapped |

贯穿机制(产品的灵魂,M0 已埋点):

- **时间胶囊**:risks 字段本来就是"供日后验证的预测"。产品化为:
  写下时密封,N 天后的日报自动开启——"三周前你担心缓存会变成孤儿
  数据,验证了吗?[还在担心 / 已解决 / 想多了]"。一键回填,形成
  预测-验证闭环的**仪式化**呈现
- **去年今日**(On This Day):日报头部回流一年/一月前同日的决定
- **生长阶段**(Maggie Appleton 数字花园):每条叙事带状态
  种子(risk 未验证)→ 抽芽(部分验证)→ 常青(决策已固化为架构事实);
  open_loops 是"未发芽的种子",在周明信片上以枯萎提醒

## 四、媒介决策(承接 06-10 的 HTML 结论,但理由升级)

依旧是**生成式单文件 HTML + markdown 数据层**,不做 app/插件/仪表盘。
但媒介服务于仪式而非"交互炫技":

- 日报保持纯 markdown——晚祷要"calm",点开即读,无 JS
- 周明信片与月年报才用 HTML:手绘感 SVG(rough.js 风格视觉语言,
  但内联实现、零运行时依赖)、scrollytelling、时间胶囊开启动效
- 远期北极星(M3+,只立意不排期):Refik Anadol 式"项目记忆宫殿"——
  把整个项目的 commit/会话史渲染为一件可漫游的数据雕塑。
  他的话适合放在 README 扉页:"数据不是数字,数据是记忆"

## 五、成功度量(人文产品要用人文指标)

- 北极星:**回看率**——7 天后仍被打开的日报占比(Day One 逻辑)
- 仪式完成度:时间胶囊的回填率(预测-验证闭环真的闭上了吗)
- 反指标(明确不优化):打开时长、日活、连续打卡天数——
  优化这些等于背叛"慢"的立场
- 隐私即人文:数据不出本机不只是合规约束,是产品的伦理表达

## 六、M1 最小切片(两周量级,沿用 M0 架构)

1. `report.py` 文案改信件体 + 头部"去年今日/上月今日"回流(纯 markdown,~+40 行)
2. 时间胶囊:cache.db 加 `capsules` 表(risk、密封日、开启日、回填状态),
   日报尾部渲染"今日开启的胶囊"(~+80 行)
3. `postcard.py`:周明信片单文件 HTML 模板,先做"一周一度量 + 手绘 SVG
   折线"一种(~+150 行)
4. Code Wrapped 月报推 M2

## 引用

- Giorgia Lupi, [Data Humanism Manifesto](http://giorgialupi.com/data-humanism-my-manifesto-for-a-new-data-wold) / [Dear Data](https://en.wikipedia.org/wiki/Giorgia_Lupi)
- Nicholas Felton, [Feltron Annual Reports](http://feltron.com/)(2006–2011 入藏 [MoMA](https://www.moma.org/collection/works/145531))
- [School for Poetic Computation](https://sfpc.study/)
- [Spotify Wrapped 案例研究](https://thebrandhopper.com/2025/06/10/a-case-study-on-spotify-wrapped-the-storytelling-phenomenon/)
- Day One, [On This Day](https://dayoneapp.com/features/on-this-day/)
- Maggie Appleton, [A Brief History of Digital Gardens](https://maggieappleton.com/garden/)
- [Refik Anadol](https://refikanadol.com/works/machine-hallucinations-nature-dreams/),"数据即记忆"
- Hallnäs & Redström, [Slow Technology — Designing for Reflection](https://www.researchgate.net/publication/220141933_Slow_Technology_-_Designing_For_Reflection)
