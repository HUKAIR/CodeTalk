# 跨项目总览(`brief --all`)设计

> 状态:已批准设计 + 已过对抗审查(15 raw → 12 confirmed,见末节),待落 plan。
> 日期:2026-06-19。作者:vibetrace dogfood。

## 背景与张力

vibetrace 现在是单项目工具:每条命令 `--project` 锁一个仓。多项目时缺一个横向视图——
"今天我在哪些项目欠了多少理解债、有哪些到期胶囊待验证"。

早期把它定为非目标,怕 vibetrace 退化成"又一个聚合 dashboard",越过护城河
(跨时间认知,而非又一个指标墙)。重新定位后做:**它是 `brief` 的横向延伸——
一个跨项目"注意力路由",只端出需要你动手的项目,而不是把所有项目的指标铺成墙。**

## 定位(三条已锁的支柱)

1. **注意力路由,不是 dashboard**:像 `brief` 一样只端"该看的",按紧迫度排序;
   **零 LLM**(与 brief/debt/graph 同档)。
2. **发现零配置**:从 cache.db 读所有项目路径,不需要用户登记。
3. **表面 = `brief --all`**:扩现有 `brief`;不加 `--all` 时单项目行为零改。

## 非目标(点名拒绝,守护城河)

- 不做指标 dashboard / 趋势图 / 跨项目排行榜娱乐。
- 不调 LLM、不生成叙事报告(那是 digest/course 的活)。
- 不做项目登记/配置文件(发现完全从 cache 派生)。
- 不在总览里复述单项目 brief 全文(路由指"去哪个项目",到那再 `brief --project X`)。

## 发现:`cache.distinct_projects()`

新增纯查询方法(零 LLM):

```sql
SELECT project FROM commit_narratives WHERE project LIKE '/%'
UNION SELECT project FROM daily_digests   WHERE project LIKE '/%'
UNION SELECT project FROM capsules        WHERE project LIKE '/%'
```

返回去重后的项目**绝对路径**列表(按字母序)。

**`project LIKE '/%'` 是必需的(对抗审查 F2/F3)**:`commit_narratives` 的 `project` 列**并非**
全是绝对路径——`graph` / `ask` / `course` 三条派生命令把项目 **basename** 写进了该列
(graph.py:116、ask.py:128、course.py:114 传 `pp.name`),#1 的统一只覆盖了
capsules/daily/reviewed。所以裸 `SELECT DISTINCT project` 会同时返回 `CodeTalk`(basename 幻影)
与 `/Users/.../CodeTalk`(真路径)两条。`LIKE '/%'` 只保留绝对路径(本机 darwin/linux 绝对路径
必以 `/` 开头),一刀滤掉所有 basename 幻影与历史测试残留(`cp2`、`tmp*` 等)。

> **根因(本 spec 范围外,记为后续小修)**:graph/ask/course 应把 `str(pp)` 而非 `pp.name`
> 传给 `put_narrative`,与 enrich 一致。即便修了,历史 basename 行仍在,故发现端的
> `LIKE '/%'` 守卫无论如何都必须有。根因修复另开小 PR,不混入本特性。

## 每项目的注意力信号(全部复用现成零-LLM 件)

| 信号 | 来源(已存在) | 取值 |
|---|---|---|
| 待验证预测 | `cache.pending_capsules(p)` | 到期未答胶囊数 + 最久一枚(sha/risk/sealed_date) |
| 理解债峰值 | `debt.debt_board(p, cache, today, top=1)` | 最高债模块文件名 + 债值;空 board → 0 |

`open_loops` **不进总览**(对抗审查 F7):它是 LLM 每次 commit 几乎必填的推断字段
(llm.py:31「允许合理推测」、schema 必填),不是离散的"你欠一次动作"信号,做触发会
和债一样把几乎所有活跃项目放进来。需要看未闭环时去 `brief --project X`。

## 相关性过滤与排序(对抗审查 F4/F6:去掉 DEBT_FLOOR 魔数,改"有界 top-K")

只有**两条**入选路径,二者都天然有界/稀缺:

1. **有到期待验证预测**:`pending_capsules(p) ≥ 1`。胶囊是真正"你欠一次动作"的信号
   (到期 + 未答 + 答了自动消失,cache.py:132-156),稀缺、自清。
2. **理解债最高的前 K 个项目**:把所有存活项目按理解债峰值降序,取前 `TOP_DEBT_PROJECTS = 5`。

`TOP_DEBT_PROJECTS = 5` 是**展示上限**(与 brief 现有 `top=3` / `[:5]` 同类),
不是对连续量设阈值——后者(原 `DEBT_FLOOR=5.0`)被审查证伪:债是常驻量,
非 serve 用户 `understand≈0`,债峰几乎恒 > 5,等于放行所有项目。改"取债最高的 K 个"
天然有界、无魔数,且和单项目 brief"理解债 top3 总在显示"的既有取舍一致——
直接回答用户"我在哪些项目欠了多少债"。

**展示集** = (有到期胶囊的项目) ∪ (债最高的 K 个项目)。
**排序**:字典序两键降序 `(待验证胶囊数, 理解债峰值)`——到期胶囊是真正"到点"的动作,优先。

## 输出格式(终端打印;`--vault` 另写一份**已脱敏** markdown)

```
# 跨项目总览 · 2 个项目待办

## CodeTalk  ~/Github/CodeTalk
- 待验证预测 2 枚(最久 28 天前):「serve 模式胶囊回写可能丢失」
- 理解债 top:`vibetrace/cli.py`(债 73.0)

## SuperSearch  ~/Github/SuperSearch
- 理解债 top:`crawler/fetch.py`(债 12.1)

_另有 3 个存活项目未入榜(债较低、无到期胶囊),已省略。_
```

- 项目标题 = basename + 缩写路径(`~` 替换 home)。
- 待验证预测行:`N 枚(最久 M 天前):「最久一枚 risk」`。`M 天前` = `(today - sealed_date).days`,
  用 `pending_capsules` 已返回的 `sealed_date`(不扩展返回值)。因密封→开启固定隔 21 天
  (cli.py:97),一枚 pending 胶囊必然 ≥21 天,示例数值取 28(对抗审查 F-minor:原 14 不可能)。
- 理解债行:仅在 board 非空时出现。
- footer:仅当有"存活但未入榜"的项目时出现,报其条数。**不报失效路径数**
  (对抗审查 F3:失效路径静默跳过,见下)。

## 失效路径:静默跳过(对抗审查 F3)

`build_overview` 对每个发现的绝对路径做 `Path(p).is_dir()`,为假者**静默跳过、不计数、不进 footer**。
因发现端已 `LIKE '/%'` 保证全是绝对路径,`is_dir(绝对路径)` 与 cwd 无关,也不会再有
basename 撞到同名兄弟目录(对抗审查 sibling F-minor 一并解决)。不再像旧设计把幻影/失效
混成一个"N 失效"计数误导用户。

## 脱敏:`build_overview` 自身脱敏(对抗审查 F1/F5)

旧设计声称"经 report 路径同款脱敏",但 `report.write_report`(report.py:98-103)逐字写盘、
**从不脱敏**——脱敏只在 `report.render`(report.py:95)里。故:

- `build_overview` 返回前对全文 `config.redact_secrets(...)`(镜像 report.render 的做法),
  终端打印与 vault 写入都经此脱敏,签名仍 `(cache, projects, today)`、无需 vault 形参。
- **顺手补红线漏洞(同文件、隐私红线,显式列为 in-scope)**:`build_brief` 今日的 vault 写
  (cli.py:165)同样未脱敏,违反 CLAUDE.md「落盘前脱敏」。本 PR 把 `build_brief` 返回前
  也包一层 `redact_secrets`(1 行),与 `build_overview` 对称、闭合同一红线。

> 实际泄漏风险本就低(capsule risk / overview 等字段在 enrich.py:82/128-129 入缓存时已脱敏),
> 但 spec 承诺"secret 不落盘"就必须有真实脱敏点,而非靠上游运气。

## 不做跨项目 `read_capsule_answers` 同步(对抗审查 YAGNI)

旧设计在 cli 里对每个项目跑 `report.read_capsule_answers` 同步 Obsidian 勾选——砍掉。
`brief --all` 是**对 cache.db 的纯读**:`distinct_projects → 聚合 → 打印`。胶囊答案已在
`digest`(cli.py:77)与 `brief --project X`(cli.py:160)时同步;万一某项目有刚勾选未同步的
胶囊,总览把你**路由到该项目**,你在那跑 `brief --project X` 即自愈。省一圈跨项目 vault 重扫。

## 落点与改动面(surgical)

- **`cache.py`**(215→~225):新增 `distinct_projects()`(上面的 `LIKE '/%'` UNION 查询)。
- **`brief.py`**(89→~155):新增模块级常量 `TOP_DEBT_PROJECTS = 5`;新增
  `build_overview(cache, projects, today)`(纯函数:逐存活项目算 pending+debt → 取并集 → 排序 →
  渲染 → 返回 `redact_secrets(全文)`)与 `_overview_row(...)`(单项目紧凑块)。
  复用 `debt.debt_board` / `cache.pending_capsules` / `config.redact_secrets`。
  另:`build_brief` 返回前包 `redact_secrets`(红线小修)。
- **`cli.py`**(275→~287):`brief` 加 `--all` 旗标;`brief_cmd` 中 `--all` 分支:
  `projects = cache.distinct_projects()` → `today = now().astimezone().date()` →
  `content = brief.build_overview(cache, projects, today)` → 打印 →(`--vault` 时 `write_report`,
  内容已脱敏)。`--all` 时忽略 `--project`,且不跑 `read_capsule_answers`。不加 `--all` 走原
  `build_brief`,行为零改(除返回值已脱敏)。
  > cli.py 接近 300:加旗标+小分支后约 287。若实现中越界,把 `brief` 分发抽到 `brief_cmd`/小函数。

全部模块仍 <300 行。

## 测试(stdlib unittest)

- `distinct_projects`:`LIKE '/%'` 滤掉 basename 行(造 `CodeTalk` + `/abs/CodeTalk` 两行,只回后者)
  与非绝对路径残留;三表并集去重;空库返回 []。
- `build_overview`:
  - 债最高的 K 个项目入榜、第 K+1 个被省略并计入 footer;
  - 无债但有到期胶囊的项目入榜;
  - 排序 `(pending, debt)` 降序正确;
  - 不存在的绝对路径静默跳过(不进输出、不计数、无 footer 失效数);
  - 无存活项目 → 单一空状态文案;
  - **脱敏**:往某胶囊 risk 塞假 secret(如 `sk-…`),断言输出含 `[REDACTED]`、不含原值。
- `cli`:`brief --all` 走 overview 分支且不调 `read_capsule_answers`;`brief`(无 `--all`)走原
  `build_brief` 不变。
- 沿用现有测试范式:临时 cache.db + 临时 git 仓 fixture。

## 验证

- `python3 -m unittest discover -s tests` 全量绿。
- `grep -n LLMClient vibetrace/brief.py vibetrace/cache.py` = 0(自证零 LLM)。
- 各模块 `wc -l` < 300。
- CodeTalk dogfood:`vibetrace brief --all` 真跑,产出合理、不崩、`grep -i 'sk-' 输出` 无明文。

## 对抗审查修正(12 confirmed,全部已折入)

| # | lens | 问题 | 处置 |
|---|---|---|---|
| F1/F5 | privacy/consistency | write_report 不脱敏,承诺落空 | build_overview 返回前 redact;build_brief 同补 |
| F2 | correctness | graph/ask/course 写 basename → distinct_projects 出幻影 | 发现端 `LIKE '/%'` 滤绝对路径;根因记后续小修 |
| F3 | correctness | 幻影被误计为"失效路径" | 失效路径静默跳过、不计数 |
| F4/F6 | simplicity/moat | `DEBT_FLOOR=5.0` 魔数 + 放行几乎所有项目 | 删 DEBT_FLOOR,改"债最高 top-K"有界展示 |
| F7 | moat | open_loops≥1 非动作信号,二次坍塌 | open_loops 移出总览(触发与展示都不要) |
| min | simplicity | 跨项目 read_capsule_answers 同步属 YAGNI | 砍,纯 cache 读,路由后自愈 |
| min | consistency | "14 天前"生命周期下不可能 | 按 sealed_date 计,示例改 28 |
| min | correctness | basename 撞兄弟目录算错 repo | `LIKE '/%'` + abspath is_dir 一并消除 |
| min | consistency | 空状态 case-b 无测试 | top-K 设计下 case-b 不再发生,合并为单一空状态 |
