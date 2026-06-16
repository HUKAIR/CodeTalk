# 演进课程(静态期)· 设计 spec

> 2026-06-16 · 经多轮 brainstorm 定稿(课程那轮 + 产品创新点那轮 + 本轮)。
> 本 spec 只做静态期;活课程(护城河)为第二期,缓存键已留接口。

## 背景:课程是入口,演进课程才守差异化

`codebase-to-course`(同作者 zarazhangrui)把代码库讲成单文件 HTML 课程,教"代码**是什么**"。但 vibetrace 从第一天就定位区别于此——回答"代码**怎么变成这样的**、AI 替我做了哪些决定"。

护城河判别("关掉大模型、只用一次调用还成立吗"):课程**是入口**(单一大模型一句 prompt 能干)。守差异化的方式是做**演进课程**(时间维度教学,而非静态架构)。课程要有护城河需做成**活课程**(随演进重修 + 版本对比)——那是第二期。**本 spec 是静态期:入口 + 验证 codebase-to-course 形态是否成立。**

## 已定决策(贯穿多轮)

1. 双课程,演进课程(A)先行;静态架构课程(B)更后。
2. 演进课程:**全史一门课 + 自动分章**(不是一 commit 一章,而是相关 commit 聚成一章)。
3. **静态先行,活课程第二期**。
4. **LLM 场景测验,与分章合并为 1 次调用**。
5. 复用 `tunnel.html` 像素视觉语言。
6. **接理解债**:课程优先讲"你欠理解最多的模块"的演进。

## 模块(最大化复用,均 <300 行)

| 件 | 职责 | 复用 |
|---|---|---|
| `course.py`(新,~170) | 装配数据 + 1 次 LLM(分章+导言+测验)+ 注入模板 + 缓存 | `gitlog.collect_commit_files`、`cache.get_narrative`、`debt.debt_board`、`llm.LLMClient.narrate(schema)` |
| `course.html`(新模板) | 滚动式章节课程页 | `tunnel.html` 620 行像素视觉语言(Fusion Pixel、黑白、像素渐隐) |
| `cli.py` +8 | `vibetrace course [--project] [--since]` | — |

## 数据流 + 1 次 LLM

```
collect_commit_files(全史)               # 轻量:sha/date/files,不取 diff
  + get_narrative(各 commit)             # what/why/decisions
  + debt_board(欠理解模块)               # 接认知循环:债高模块提示 LLM 优先成章/前置
  → 1 次 llm.narrate(COURSE_SCHEMA):
      {chapters: [{title, intro, commit_shas, quiz: [{q, options, answer, hint}]}]}
      (输入只给叙事,不给 diff,省 token)
  → 每章「代码↔讲解」:取该章 1-2 个代表 commit 的 diff 片段(少数 git show,不全量)
  → 注入 course.html → vault/<project>-course.html
```

COURSE_SCHEMA(传给 `llm.narrate` 的自定义 schema):
- `chapters[]`:`title`(章名)、`intro`(章导言:当时的决定/被否决的备选)、
  `commit_shas`(本章涵盖的短 sha)、`quiz[]`(`q` 题干、`options` 选项、
  `answer` 正确项索引、`hint` 答错提示)。

## 缓存

课程整体以 `course:HASH` 为键(`HASH` = 全史 SHA 集合的 sha256 前若干位)存入
`commit_narratives` 表(沿用 digest 概览的 `sha='digest:...'` 模式)→ **重跑 0
调用、<5s**。提交集合不变则命中缓存;新 commit 出现则 HASH 变、重算。

**为第二期埋点**:`course:HASH` 天然是版本快照。活课程只需保留历史 HASH 版本 +
加"这章上版 vs 现在变了什么"对比层,不改本期数据结构。

## course.html 形态(借 codebase-to-course 的形式)

- 滚动式章节导航 + 进度条
- 章首:当时的决定 / 被否决的备选(来自叙事 decisions)
- **代码↔讲解并排**:左 diff 片段 / 右人话(叙事 what)
- **场景测验**:选项式("要把霓虹改像素,会改哪些文件?"),答错给 hint
- 术语悬停提示
- 复用像素黑白视觉语言
- 纯 `file://` 单文件:课程是阅读 + 自测,**不回写 cache,无需 serve**(比隧道简单)

## 降级(绝不崩)

- 无 API key / LLM 失败 → **朴素课程**(按时间顺序、不智能分章、无测验),
  顶部标注"未智能编排,设置 key 后重跑可得完整课程"。
- 无叙事的 commit → 该段标"未叙事,跑 vibetrace digest"。
- 代码↔讲解的 diff 取不到(git show 失败)→ 该章仅显叙事,不崩。
- 债务榜为空(无信号)→ 课程按时间默认排序,不接债。

## 验证

1. 本项目自身跑 `vibetrace course`:产出 course.html,章节/代码对照/测验齐全,
   HTML 解析合法,`cache.py`/`cli.py`(理解债高)相关章节靠前
2. 缓存:连续两次运行,第二次 LLM 调用 0、<5s
3. 降级:无 API key → 朴素课程不崩、有标注
4. 行数:`course.py` < 300
5. 幻觉抽检:课程讲解随机抽 5 条,回溯 diff/叙事核对

## 分期 / 不做

- 本 spec 只做**静态演进课程**。
- **活课程**(版本对比 + 增量重修,护城河)= 第二期,缓存键已留接口。
- **静态架构课程(B)**= 更后期,同 `course.html` 模板、数据源换"当前模块结构"。
- 不做 Web 服务器(课程纯 file://);不做多媒体(音频/视频)。
