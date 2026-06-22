# Spec: ask/blame 全文召回(sqlite3 FTS5)

**Goal:** 给 `ask`/`blame` 的检索补一条**内容召回**路径——当前只走 git line-log/file-log(文件:行→SHA),对"跨文件主题问题"或"行级 log 命中过宽"召回差。用 SQLite 内置 FTS5 对已缓存叙事做全文检索,与现有 line-log 路径取并集。**零新依赖**(sqlite3 已是 stdlib,本机 `ENABLE_FTS5` 已核实)。

**Architecture:** `cache.py` 加一张 FTS5 虚拟表索引 `commit_narratives` 的可读文本(why / evidence 原话 / pr 片段 / 决策 / 风险),以 SHA 关联;`put_narrative` 落盘时同步;新增 `Cache.search_narratives(query, limit)`。`ask._retrieve` / `blame.collect_segments` 增加内容召回路径,与 line-log 结果**并集去重**(line-log 优先)。FTS5 不可用时整条路径降级为空,行为回退到现状。

**Tech:** stdlib `sqlite3`(FTS5 + 内置 `bm25()`);中文用 **`trigram` tokenizer**(SQLite 3.34+,子串匹配,适配无空格的 CJK——`unicode61` 默认会把整段中文当一个 token,召回失效)。

## Global Constraints (M0)
- 仅 stdlib + anthropic;`cache.py` 改后 <300 行(现 236,余量足);新检索方法纯 SQL。
- **容错降级绝不崩**:FTS5 缺失(非官方 CPython/旧 SQLite 未编译)→ 探测失败则禁用全文路径,`ask`/`blame` 回退到纯 line-log,不报错。
- **脱敏**:FTS body 取自 `narrative_json`(已在 `put_narrative` 脱敏),不引入新落盘文本;FTS 表与主表同库本地,数据不出本机。
- 内容寻址不变:叙事仍以 SHA immutable 为键;FTS 是派生索引,可随时重建。

## 设计决策(已定,评审可挑)
1. **standalone FTS5 表**(非 external-content),`body` 字段存拼接文本。理由:external-content 需触发器同步、复杂度高;叙事量是项目级 commit 数,standalone 重复存储成本可忽略,且重建简单。`sha UNINDEXED` 作回连键。
2. **tokenize='trigram'**:中文子串召回必需;英文亦可用。代价:query 须 ≥3 字符(<3 字符 query 降级走 line-log,合理)。
3. **body 内容** = `why` + evidence 的 prompts/excerpts + pr_refs 的 snippet/title + decisions + risks 拼接(都是已脱敏可读文本)。不索引代码/diff(噪声大、且 ask 的价值是 why 不是 grep)。
4. **并集策略**:line-log 结果在前(行级精确),FTS 结果补充其后,按 SHA 去重;不重排 line-log。FTS limit 默认 8。
5. **同步点**:仅 `put_narrative`(单点收口,与脱敏同处)。`get_narrative` 不动。删除/失效:`INSERT OR REPLACE` 语义靠"先 DELETE 同 sha 再 INSERT"实现(FTS5 无 PRIMARY KEY)。

## Components / Interfaces
- `cache.py`
  - `__init__`:`SCHEMA` 执行后,`try` 建 `narrative_fts`(`CREATE VIRTUAL TABLE IF NOT EXISTS narrative_fts USING fts5(sha UNINDEXED, body, tokenize='trigram')`);捕获 `sqlite3.OperationalError` → `self.fts_ok=False`(否则 True)。
  - `put_narrative(...)`:现有逻辑后,若 `self.fts_ok`:`DELETE FROM narrative_fts WHERE sha=?` + `INSERT INTO narrative_fts(sha, body) VALUES(?,?)`,body 由内部 `_fts_body(narrative)` 拼接;FTS 写失败只 `log.warning` 不拖垮主写(容错)。
  - 新增 `search_narratives(query, limit=8) -> list[sha]`:`self.fts_ok` 且 `len(query)>=3` 才查;`SELECT sha FROM narrative_fts WHERE narrative_fts MATCH ? ORDER BY bm25(narrative_fts) LIMIT ?`;MATCH 参数对 query 做 FTS5 转义(包成 `"..."` 词组或按空格分词);任何 `sqlite3.Error` → 返回 `[]`。
  - 旧库迁移:首次启用时 `narrative_fts` 为空 → 新叙事增量进表;**提供 `reindex_fts()`**(从 `commit_narratives` 全量重建),供一次性回填(可由 `ask`/`digest` 首次发现空表时惰性触发,或 CLI `vibetrace reindex`——评审定是否要 CLI)。
- `ask.py::_retrieve`:取 line-log shas 后,`fts_shas = cache.search_narratives(question)`;`shas = line_shas + [s for s in fts_shas if s not in set(line_shas)]`;其余流程(narrative 拼装/evidence)不变。`code_state` 仍取 line-log 最新(FTS 命中不改代码态键)。
- `blame.py::collect_segments`:行级/文件级 shas 为空或叙事缺失时,用 `search_narratives` 补;保持"旧→新"展示顺序。

## Testing
- FTS5 present:put 两条叙事(why 含不同关键词)→ `search_narratives("乐观锁")` 命中对应 sha、不命中另一条。
- **中文 trigram**:why 为中文 → 中文 query 子串命中(验证 tokenizer 选对)。
- degrade:mock `fts_ok=False` → `search_narratives` 返回 `[]`,`ask._retrieve` 仅返回 line-log 结果(回退正确)。
- 并集去重:line-log 与 FTS 命中同一 sha → 结果不重复;line-log 优先序保留。
- 脱敏:put 含 secret 的 narrative → FTS body 中已 `[REDACTED]`(继承 put_narrative 脱敏)。
- <3 字符 query → 不查 FTS、走 line-log。

## 非目标
向量库/embedding(needs_dep,出局);重排序/语义检索;索引代码或 diff;external-content 触发器同步。

---

## 评审修订(对抗审 wksn06gfj 后)

**裁决:DEFER 到 Phase 2,先不实现。** 对抗审两位评审一致指出:`ask`/`blame` 当前**都是 file-targeted**(`_parse_target`→file:line,CLI target 必填),**根本没有"跨文件主题提问"的入口**——FTS5 想解决的召回问题当前 CLI 表面提不出,属"为不存在的用例造能力"(karpathy §2)。冷启动/分发的真正解法是 **MCP(先做)**,不是 FTS。

**重新定义 Phase 2 的前置条件(满足才实现):**
1. **先有一个 topic-query 入口**才让 FTS 有落点:候选 = MCP 新增 `vibetrace_search(question)` 工具(不带 file target)或 `ask --topic`。**FTS 与该入口同一特性一起做**,不单独上。
2. **N=1 召回失败证据**:用一个真实查询证明 line-log 已召回的 SHA 集合不够、且 FTS 能补上正确 SHA;无此证据不进 M0。

**若 Phase 2 实现,以下 blocking 修订已定(覆盖上文):**
- **MATCH 转义(唯一确定方案,实测)**:strip FTS5 特殊字符(`" * ( ) : - ^` 及 `AND/OR/NOT/NEAR`)→ 按空白/标点切 term → 每个 term 双引号包成 phrase(内部 `"`→`""`)→ 用 ` OR ` 连接 → `"t1" OR "t2"`;0 有效 term→返回 `[]`。**OR 连接**(非隐式 AND)才能"命中任一关键词即召回";崩溃用例(`?`、裸引号、括号、冒号、减号、纯标点)入测试。
- **code_state 不被污染**:union 前 `code_state = line_shas[-1] if line_shas else ""`;FTS 命中放独立变量,**绝不进** 派生 code_state 的列表。并明确 FTS 命中是否进 LLM context——若进则缓存键须纳入 FTS 命中集,否则陈旧;倾向"FTS 命中只补 SHA 检索、context 仍走命中 narrative"。
- **砍 reindex_fts + CLI reindex(YAGNI)**:put_narrative 的 `DELETE+INSERT` 幂等即增量;一次性回填用"删表重建"文档说明或 digest 重算覆盖,不暴露命令。
- **探测升级**:`create 虚拟表 + 一次最小 MATCH 自检`(防 fts5 编进但 trigram 没编);`<3 字符**有效 term**`(非整句)才查;主表先 commit 再单独 try FTS 写(异常只 warning);body 先窄(why+decisions)再按证据加宽。
- blame 复用时,FTS 补充段需标注"[主题相关,非本行直接改动]"以不稀释 blame 确定性语义。
