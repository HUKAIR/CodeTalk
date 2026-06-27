# 去 AI 味 system-prompt 规则与实证 — 2026-06-27(deep-research)

**来源**:`/my-starred-repos` 扫出 `hardikpandya/stop-slop` 等 anti-slop skill → deep-research(6 角度、
23 源、25 claim 验证、17 confirmed)取证。**结论先行**:vibetrace 的「文风纪律(去 AI 腔)」**早已实现且
正是 research 认证最稳健的『结构性』做法**;本轮只补一条平衡护栏,**没有**也**不该**加词-banlist。

## 核验:vibetrace 现有文风纪律 = 最稳健做法

现有 `prompts.py` 三处 system prompt 的文风纪律已覆盖 research 命中的**高价值结构性 AI tell**(开源
5 skill + 学术共识):开场陈词、破折号堆从句(降密度非禁绝)、「不是 X 而是 Y」二元对照、凑数三项排比、
被动无施动者、空泛形容词换具体。research 明确:**结构性目标(具体性/密度/actor 化/句长方差)比词-banlist
更稳健**——词表会随模型迭代失效(2026 新模型已主动抑制 em-dash,「em-dash=#1 tell」前提正在过时),且
**词-banlist 会误伤**(见下)。故现有实现方向正确,无需照搬 stop-slop 的词表。

## 本轮唯一增量:平衡护栏(防过度去味伤准确)

`prompts.py` SYSTEM/ASK/CHAT 文风纪律各加一条:
> 去味是降密度非清零;技术术语/文件名/SHA/逐字引用照原样,**准确高于文风**,绝不为去味改写或「优化」。

依据(两条 high 证据 + 一条 vibetrace 专属):① Thoughtworks + Antislop(arXiv 2510.15061)+ LLM-Guard:
**粗暴 substring 禁词会误杀**(禁 `indigestible` 连带禁 `in`/`digest`)→ 管整词/语境/密度,别绝对禁字;
② The Ringer + WaPo:**em-dash 当 AI 探针有假阳性**,真人含破折号被误判 → 按密度非零容忍;③ **vibetrace 专属**:
中文工程术语(复杂度/框架/复杂性)是准确术语、非 AI 腔(deep-research open Q),de-slop 误删会伤准确;
且 vibetrace 护城河是**逐字真实记录**,LLM 综合产出绝不能为文风改写引用/SHA/术语。

## 实证地基(引学术,别引 skill 自述)

- **Kobak et al., Science Advances 2025**(DOI 10.1126/sciadv.adt3813):1500 万+ PubMed 摘要,2024 年
  LLM 驱动「风格词」激增,`delve` 超额比 r=28.0 居首(`underscores` 13.8、`showcasing` 10.7)。词表的数据地基。
- **Wang et al., arXiv 2502.11614**:**少有的对照实测**——prompt 里要求「加具体细节/引用、避开模板化结构与
  bullet/Markdown、变化长度结构情感」后,人类辨识率 **87.6%→72.5%**、26 检测器中 19 个准确率下降。
  **证明注入 prompt 有效但只是部分**(仍远高于随机,文化/多样性缺口在)。
- **stop-slop 等 skill 可信但零自证**:规则逐字可复制、覆盖全,但仓库无任何 A/B/实测,有效性只靠自定义
  1-10 评分。**「注入即去味」的真证据全在学术论文侧,别引 skill 自述。**

## 诚实边界 / 待办

- **时效**:banlist 半衰期短(模型在抑制这些 tell)→ 坚持**结构性目标**而非禁特定词/符号;定期重校。
- **证据不对称**:覆盖最全的规则来自单源社区 skill;唯一对照实测是 Wang 一篇,结论是「部分弥合」非「彻底去味」。
- **被驳回、不写进 prompt**:「backfire effect(禁词反致多用)」(1-2 驳)、「slop 定义为聚集故只禁密度不禁存在」
  (0-3 驳)未过验证,不作定论;但「管密度优于绝对零容忍」由 substring 误杀 + em-dash 假阳两条 high 证据间接支撑。
- **开放问**(未做,留记录):技术叙事的去味阈值(em-dash 每 N 词、tricolon 密度)未在工程文本验证;缺
  Claude 专项 + vibetrace digest 前后 A/B;中文 AI 腔缺 Kobak 式频率数据(哪些是真信号、哪些误伤术语)。
