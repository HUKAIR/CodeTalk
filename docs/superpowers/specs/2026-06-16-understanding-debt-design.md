# 理解债量化 · 设计 spec

> 2026-06-16 · 经多轮 brainstorm 定稿。补齐"认知循环"的唯一缺口。

## 背景:为什么是这个功能

vibetrace 的护城河不在"LLM 能生成什么"(那些单一大模型都能干),而在 **LLM 之外的跨时间认知基础设施**。判别工具:**「关掉 cache.db、只用一次大模型调用,这功能还成立吗?」** 还成立 = 入口(谁都能抄);不成立 = 护城河。

护城河是一个**地基 + 三步认知循环**:
- 地基:稳定记忆(SHA 不可变缓存)— 已有
- 循环:主动简报(brief)→ 时间胶囊(预测-验证)→ **理解债量化** → 回喂简报
- 前两步已实现(PR #3 brief、PR #1/#3/#5 胶囊)。**理解债量化是唯一缺口**,也是产品同名核心("理解债"却还没有"债务计")。

补上它,前三步从开环变闭环。**且它纯本地、零 LLM** —— 正好自证"换个大模型也复现不了"(需长期累积的行为状态)。

## 定义:落差视角(可定位到模块)

```
churn(m)      = Σ(涉及模块 m 的 commit 的 decisions 数 + 1)   # AI 替你做的决定越多,欠越多
understand(m) = (visited 的相关 commit 数 + 回填的胶囊数)
              / (相关 commit 总数 + 相关胶囊总数)            # 0~1
decay(m)      = 1 + 距最近一次回看 m 的天数 / 30              # 越久没看,利息越高
债(m)         = churn(m) × decay(m) × (1 − understand(m))
```
模块单位 = 文件路径(一个 commit 改多文件,churn 摊到每个)。

## 信号采集

| 信号 | 来源 | 强弱 |
|---|---|---|
| churn(欠债) | gitlog commit→files + cache 叙事 decisions | 强、现成 |
| understand 之 胶囊回填 | cache `capsules.outcome` | 中(只覆盖有 risk 的 commit) |
| understand 之 visited(回看) | **新:cache `reviewed` 表**,隧道 serve 模式 openFocus 时 POST 回写 | 见降级 |
| decay 之 最近回看 | `reviewed.reviewed_at` 最大值 | — |

**visited 收敛**:接上 PR #5 的 serve 基础设施——隧道 serve 模式点开某 commit → `POST /reviewed {sha}` → `cache.mark_reviewed`。这把"回看"信号从浏览器 localStorage 收敛进 cache,Python 端算债才读得到。

## 呈现 + 闭环

债务榜 top 3 进**开工简报**:
```
## 理解债 top 3
  1. cache.py  改12·回看2·胶囊0/3  █████  上次决定:迁移 DROP 重建… 〔回看〕
  2. report.py 改6·回看0           ███
```
闭环:`债量 → brief 端到面前 → 你回看 → 隧道 serve 写 reviewed → understand↑ → 下次债↓`

## 模块改动

| 件 | 改动 | 估行 |
|---|---|---|
| `cache.py` | 加 `reviewed` 表(全新表,CREATE IF NOT EXISTS 即可,无需 migrate)+ `mark_reviewed(project, sha)` / `reviewed_shas(project)` | +18 |
| `debt.py`(新) | 读 gitlog+cache,纯本地算每模块债,出榜 top N。零 LLM | ~120 |
| `tunnel.py`(serve handler) | 加 `POST /reviewed` 端点 → `mark_reviewed` | +12 |
| `tunnel.html` | openFocus 时 serve 模式 `POST /reviewed {sha}` | +6 |
| `brief.py` | 加"理解债 top 3"节,调 `debt.py` | +15 |

均 <300 行红线内。

## 降级(诚实标注)

- **file:// 隧道的 visited 收不回 cache**(无服务器)→ 回看信号主要来自 **serve 模式隧道 + 胶囊回填**;brief 的债务榜标注"回看信号仅含 serve 模式"。
- 无任何 visited → understand 退化为只含胶囊回填;再无胶囊 → 债 = `churn × decay`(纯"改得多又久没碰"),仍可用、不崩。
- 无叙事 commit → churn 用 commit 数兜底。

## 验证

1. 本项目跑 brief:理解债 top 3 出现,`cache.py`(改最多回看少)居首,排序合理
2. serve 模式隧道点开某 commit → cache.reviewed 有记录 → 该模块债下降
3. 纯本地零 LLM:无 API key 也出榜
4. 行数 <300
5. 降级:无 visited/无叙事 不崩

## 分期 / 不做

- 本 spec 只做理解债量化。**课程功能搁置**(用户未否定,待理解债量化后另起)。
- 不做单一健康分(需可靠还债信号,我们没有)、不做 tunnel 热力图(第二期可选)。
