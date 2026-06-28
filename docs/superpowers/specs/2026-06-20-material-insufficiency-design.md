# 解决"材料不足"源头治理设计(Level 1 + E1)

> 状态:已批准设计(两处经 AskUserQuestion 锁定),待落地。
> 日期:2026-06-20。作者:vibetrace dogfood。
> 背景:另一本地仓试点 + 终审发现 `材料不足` 填充会污染叙事/胶囊。PR #16 已做**下游过滤**
> (`report._drop_filler` 展示防御 + `enrich._normalize` 源头滤已缓存数据)。本 spec 做**上游根治**。

## 诊断(为什么会有"材料不足")

LLM 写出字面串 `材料不足` 是被 prompt 主动教的(`llm.py:32`:「材料不足以回答某字段时,直说"材料不足"」),
而非自发。`risks`/`open_loops` 是数组,空 `[]` 本就合法。两种情况被混为一谈:
- **(a) 字段本就该空**:这条 commit 没有未闭环/值得记的风险(常见,如做完整的功能提交)。正解 = `[]`。
- **(b) 输入真薄**:无会话匹配 + diff 很小。但若 commit 琐碎(改 typo/lockfile),正解**仍是**`[]`。

故根治分两刀:让 LLM 对空字段**返回空数组而非占位**(Level 1);对**机械提交根本不调 LLM**(E1)。

---

## Level 1:prompt 让推断字段无依据时返回空

**唯一改动**:`llm.py` 的 `SYSTEM_PROMPT` 字符串。

- **删**:`- 材料不足以回答某字段时,直说"材料不足"`
- **加**:`- 列表字段(decisions/risks/open_loops)若确无依据,返回空数组 []，不要用"材料不足"之类占位凑数;what/why 必填且只据材料,why 无会话依据时标"(推测)"`
- **保留不动**:`- risks/open_loops 是你的推断,允许合理推测,但推断的前提必须与材料一致`

**关键平衡**:只改"无依据时怎么表示"(占位串 → `[]`),**不动**"鼓励合理推测"那句——否则模型变懒、连真实风险也省了。要的是"没有就留空",不是"少推断"。

**与 PR #16 关系**:Level 1 是上游(新叙事根本不含占位);`_normalize`/`_drop_filler` 退化为只防**旧缓存叙事**(SHA 不可变)。互补,都留。

**验证(诚实说明)**:prompt 改动无法单测模型行为,只能——
1. prompt 内容测(沿用 `test_prompts.py` 套路):断言 `SYSTEM_PROMPT` **不再含** `直说"材料不足"`、**且含**"空数组"指令;
2. dogfood:重跑一次 digest,肉眼确认新叙事 risks/open_loops 不再冒"材料不足"。

---

## E1:跳过机械提交,不为它花叙事

**触发点**:`enrich.enrich_commits` 在调 `llm.narrate` 前加闸——`if _is_trivial(commit):` 写稀疏 stub、`put_narrative` 缓存、`continue`,**不调 LLM**。commit 仍进时间线(稀疏一行),不冒"材料不足"、省一次调用。

**判定 `_is_trivial(commit)`(零-LLM,保守)**:
> trivial ⇔ `commit["files"]` 非空 **且** 每个文件都命中 `TRIVIAL_GLOBS`。
只要有**一个真实源码文件**就照常叙事(宁可少跳、不错杀有料小改)。**经 AskUserQuestion 锁定:保守版,仅全 lockfile/生成产物;不含 tiny-diff / chore: 前缀**(那些误判风险高)。

**`TRIVIAL_GLOBS`(`enrich.py` 模块常量)**:
`package-lock.json` `yarn.lock` `pnpm-lock.yaml` `poetry.lock` `Pipfile.lock` `Cargo.lock` `go.sum` `composer.lock` `*.lock` `*.min.js` `*.min.css`
匹配:对每个文件取 **basename** 用 `fnmatch`(stdlib)逐 glob 试配(basename 同时覆盖根目录与嵌套路径,如 `frontend/package-lock.json`,无 `/`-通配边界问题)。

**stub 内容**:
```python
{"what": commit["subject"], "why": "机械改动(lockfile/生成文件),未叙事",
 "decisions": [], "risks": [], "open_loops": []}
```
照常 `put_narrative` 缓存(再跑命中)。**不改 `report`**——空列表段落本就不渲染,稀疏显示即可(YAGNI)。空 risks → 不封胶囊(胶囊源自 risks),自然不污染。

**统计**:`enrich_commits` 的 stats dict 加 `"trivial"` 计数。页脚是否显示"跳过 N 个机械提交"为可选小增强(不阻断)。

**验证**:
- `_is_trivial` 真值表:全 lockfile→True;含 `a.py`→False;`["poetry.lock","a.py"]`混合→False;空 `files`→False。
- `enrich_commits` 遇 trivial commit **不调 LLM**(fake LLM 记录是否被调用,断言未调)+ 缓存了 stub(`why` 含"机械改动")。

---

## 落点与改动面(surgical)

- **`llm.py`**(175→~177):`SYSTEM_PROMPT` 改 2 行(删 1 加 1)。
- **`enrich.py`**(140→~157):新增 `TRIVIAL_GLOBS` 常量 + `_is_trivial(commit)` + `enrich_commits` 入口闸 + stats `trivial` 计数。`import fnmatch`。
- 各模块仍 <300;全程零新依赖。

## PR 组织

- **Level 1** → 并进 **PR #16**(它已是"材料不足 + 合并"综合治理 PR,prompt 源头修是其上游补全)。
- **E1** → **独立新 PR**(新特性,与 #16 解耦)。

## 验证(端到端)

- `python3 -m unittest discover -s tests` 全绿;各模块 <300;`grep LLMClient enrich.py` 仍只在叙事路径。
- dogfood:对另一本地仓重跑 digest,确认(a)新叙事无"材料不足"占位;(b)若有纯 lockfile 提交则被跳过且 LLM 调用数下降。

## 非目标(YAGNI)

- 不做 Level 2(补料:改动文件上下文/相邻提交/更深会话)——另案。
- E1 不做 tiny-diff/chore 前缀/重命名检测(误判风险,保守优先)。
- 不把 `TRIVIAL_GLOBS` 做成可配置(speculative)。
- 不改 `report` 渲染(稀疏即可)。
