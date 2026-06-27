# `vibetrace commands` —— 终端命令历史接地源(零-LLM,只读,opt-in)设计

> **⛔ 搁置(2026-06-27,brainstorming 后、实现前)——不实现。** 此 spec 作「为什么没做/为什么先缓」的决策记录保留(正是 README 吹的 why-NOT / defer 维度)。
>
> **搁置依据 = 对抗审 spec(4 视角×验证×合成,19 条存活 finding)的 4 个根本性问题(非可修 bug):**
> 1. **无 cwd → 隐私归因闸两难不可解(3×HIGH CONFIRMED)**:shell history 全局、不记 cwd,故 basename 闸误中常用词仓名(`tests`/`docs`/`core`→ 别仓命令)、tracked 路径子串闸误中其他仓同名文件(`tests/test_drift.py`)。收紧只能权衡,**核心张力不可消除:无 cwd 时,闸非低召回(安全但近无用)即高假阳(有用但泄露)**。
> 2. **脱敏漏 shell history 最密的 secret(HIGH CONFIRMED)**:`redact_secrets` 只抓已知 token 模式,**漏** DB 连接串 `scheme://user:pw@host`、`-p<pw>`/`-a` 短 flag 密码、内网主机名、暴露身份的 home 路径(法定姓名/客户目录);spec 却把整套隐私押在它上。
> 3. **「接地源/grounding source」是超声明(HIGH CONFIRMED)**:§2 明确不进 ask/blame,故它**不接地任何东西**——是命令「回看」非接地;借用了护城河术语。
> 4. **off-moat 且未验证(MED CONFIRMED)**:是「敲了什么(what)」非「为什么(why)」,落在 roadmap 自己标了 `验证后做`/`N=1 不为记录付费` 的线上,无任何已验证需求。findings 3+4 实质**印证了 roadmap 自己的「验证后做」flag**(本特性是我从 Later 拉前来的)。
>
> 技术 bug(tz-naive 崩、bash `#epoch` 误判、zsh metafy 中文路径乱码、MAX_COMMANDS 截旧、env 极性、TIME_SLACK/_rel 复用名不副实、<300 偏紧)**全可修**;但根本性问题让「修完也是个 off-moat、隐私难净、价值偏弱的 what-捕获工具」。
>
> **裁决(用户 2026-06-27):搁置 + 换方向。** 完整原始设计见下(保留以备将来若拿到 cwd 信号 / 验证到真实需求再评估;真要做则按对抗审的保守重构:重命名「命令回看」、abspath+区分度多段路径闸丢 basename、硬脱敏、披露假阳假阴、exploratory opt-in 不上 README)。
>
> ---
>
> *(以下为搁置前的原始设计,存档)* 原状态:已过 brainstorming,MVP 形态=独立命令(用户拍板)。分支:`feat/command-history-grounding`。对位 ROADMAP「只读收割命令历史/会话作接地素材(红线内版)」[Next · R5]

## 1. 目标 / 痛点对位

Claude Code / Cursor 会话只捕获 **AI 在会话内用工具**做的事。开发者**自己在终端手敲**的命令——`pytest -k X`(调试焦点)、`pip install Y`(依赖决策)、`git revert Z`(回滚动作)、`python repro.py`(复现)——是「我当时在这仓干了什么」的真实活动证据,**完全没被捕获**。本特性把这块盲区收割成一个零-LLM 的接地/回看素材。

**一句话**:`vibetrace commands` 按时间线列出**显式引用本仓的**终端命令,并就近「软对齐」到 commit;纯本地、零 LLM、只读、落盘/显示前脱敏、opt-in 默认关。

## 2. 非目标(明确不做)

- **不**执行任何命令、**不**写 history、**不**内嵌可执行终端(Cursor 一串 RCE/注入 CVE,红线)。
- **不**做 OS 级全量行为捕获(撞 Pieces 腹地;捕获是手段、接地 why 才是目的)。
- **不**碰 `scan_sessions` / `digest` / `ask` / `cache`(MVP 是独立命令;先证明这源有价值,再谈 fold 进 ask 接地——对位 roadmap「验证后做」flag)。YAGNI。
- **不**判「这条命令导致了这次提交」(因果);只作时间+文本软对齐,显式标「可能不准」,沿用 `prompts` 红线。
- **不**用 LLM、**不**触网、**不**引第三方依赖。

## 3. 核心难题与解法(诚实摆出)

shell history 是**全局**的(`~/.zsh_history` / `~/.bash_history`),**不记 cwd**,bash 默认**不记时间戳**。无法天真把一条命令归因到「这个仓」——直接倒进某仓 = 泄露其他项目/个人命令(隐私灾难)+ 满屏噪声。

**解法 = 双闸归因(保守、低召回、诚实)**

1. **文本归因闸(主 + 隐私闸)** —— 只保留命令文本**显式引用本仓**的条目。命令 `c` 引用本仓 ⟺ `c` 文本包含以下任一:
   - (a) 仓**绝对路径**(`Path(project).resolve()` 的字符串),如 `cd /Users/gavin/Github/CodeTalk`;
   - (b) 仓 **basename 作词边界 token**(仅当 `len(basename) >= 4`,避免 `cd src` 类误中),如 `cd CodeTalk`;
   - (c) 任一**含 `/` 的 tracked 相对路径**作子串(多段路径,低碰撞),如 `pytest tests/test_drift.py`、`vim vibetrace/cli.py`。
   **故意排除**裸顶层文件名(`README.md`/`pyproject.toml` 满世界都是,误中其他仓)。**不引用本仓的命令直接丢弃,永不入缓存/不进任何输出/不落 vault。**
   - tracked 列表取 `gitlog.tracked_files(project)`;返回 `None`(git 失败/非仓)时**降级为仅用 (a)(b)**(路径/basename),绝不崩。

2. **时间软对齐闸(辅)** —— 有时间戳的条目就近软对齐到 commit 时间窗(复用 `align.TIME_SLACK = ±30min` 口径):命令时间落在某 commit `date ± 30min` 内 → 标注「可能对应 commit(软对齐,可能不准)」。无时间戳条目标「时间未知」,只列不软对齐。**绝不渲染「✓ 已提交 / 导致此提交」**。

## 4. 架构 / 文件

新增**单模块** `vibetrace/cmd_history.py`(<300 行),内含纯函数 + `commands_cmd`(命令逻辑放本模块,**因 `commands.py` 已 297 行逼近 <300 红线**;沿用 `drift.py` / `adr_export.py` 把 `*_cmd` 放各自模块、`cli.py` 直接 import 的既有范式)。

- `cli.py`:加 `commands` 子命令(`--project` / `--since`),`from .cmd_history import commands_cmd`,`_DISPATCH["commands"] = commands_cmd`。
- 复用:`config.redact_secrets`、`gitlog.collect_commit_files`(取 sha/date/subject)、`gitlog.tracked_files`、`digest._since_to_dt`、`prompts_view` 的 markdown/软对齐范式与 `_rel` 不泄绝对路径思路。

**不**新增任何依赖、**不**改 `cache` schema、**不**改 `scan_sessions`。

## 5. 数据模型 & 纯函数签名

```
entry = {"cmd": str, "ts": datetime | None}      # 一条命令历史

HISTORY_PATHS = [~/.zsh_history, ~/.bash_history]  # 标准位;按存在与否读
MAX_COMMANDS  = 300                                # 输出/解析硬上限,degrade-never-crash(防超大 history 卡死)

parse_zsh(text)  -> [entry]      # zsh:`: <epoch>:<elapsed>;<cmd>`(EXTENDED_HISTORY)或裸行(ts=None);
                                 #     行尾未转义反斜杠 → 续行拼接;errors="replace"
parse_bash(text) -> [entry]      # bash:`#<epoch>` 注释行给**下一条**命令打时间戳;其余为裸命令
parse_history(paths) -> [entry]  # 按后缀/文件名分派到 zsh/bash 解析;单文件异常仅记 warning 跳过

repo_tokens(project_root, tracked) -> {"abspath": str, "basename": str|None, "paths": [str]}
                                 # basename 仅当 len>=4 给出;paths = 含「/」的 tracked 路径
references_repo(cmd, tokens) -> bool          # §3 闸 1
repo_commands(entries, tokens) -> [entry]     # 过滤 references_repo;对 cmd 做 redact_secrets;截到 MAX_COMMANDS

soft_commit(ts, commits) -> [(sha7, subject)] # ts 在某 commit date ±30min 内的 commit(去重,最多 3 条);ts=None → []
build_commands_view(filtered, commits, project_path) -> str   # markdown,零 LLM,绝不崩

commands_cmd(args) -> int                     # 读 config flag;关→友好开启指引;开→组装并 print
```

## 6. opt-in 机制(隐私第二道闸)

读**全局** history 是敏感面,故除「显式运行该命令」外再加一道显式开关:

- `config.py` `DEFAULTS` 加 `"capture_command_history": False`。
- `commands_cmd`:读 `cfg["capture_command_history"]`(或环境变量 `VIBETRACE_CAPTURE_COMMAND_HISTORY` 一次性覆盖,镜像 `VIBETRACE_NO_LLM` 范式);为假 → **不读任何 history**,打印**可操作的知情同意提示**:说明将读 `~/.zsh_history`/`~/.bash_history`、隐私姿态(只读 / 落盘前脱敏 / 仅留引用本仓的命令 / 数据不出本机),给出开启方式(config 一行 或 env 一行),返回 0。
- `load_config` 已逐键覆盖,新键零改其逻辑。

## 7. 输出格式(markdown,镜像 `prompts_view`)

```
# 终端命令回看 · <repo>(零 LLM,本地,只读)

## 2026-06-27
- 14:03  pytest tests/test_drift.py
  → 可能对应 commit(软对齐,可能不准):[ea8c404] feat(drift): …
- 14:20  pip install -e ".[anthropic]"

## 时间未知
- vim vibetrace/cli.py

> 注:命令是「敲了什么」非「为什么」;按文本+时间软对齐、可能不准;
> 只收录显式引用本仓的命令(保守、必漏)。补会话捕获盲区的活动证据,非因果归因。
```

- 无可收录命令 → 友好提示(可能没在终端碰过本仓 / history 已清 / 未开启 EXTENDED_HISTORY),绝不崩。
- 命令文本经 `redact_secrets`;不泄绝对路径(命令本身可能含,但脱敏只管 secret——绝对路径是用户自己敲的、属其本机命令,保留原样以可读;这是与「会话文件路径」不同的取舍:此处命令即用户原话)。

## 8. 红线核对

| 红线 | 本设计 |
|---|---|
| 仅 stdlib + anthropic | 仅 `pathlib`/`re`/`datetime` 等 stdlib;零 LLM、零三方 |
| 数据不出本机 | 纯本地读 + 本地 print;不触网、不调 LLM |
| 落盘/出网前脱敏 | 每条 cmd `redact_secrets`(history 常含 `curl -H "Authorization:…"`/`export X_API_KEY=…`) |
| 只读 / 不破坏 | `open(..., 'r')`,绝不执行/写 history |
| 拒内嵌终端 / OS 全量捕获 | 只解析已存在的 history 文件,无执行面、无 OS hook |
| degrade-never-crash | 单文件/单行解析异常仅 warning 跳过;git/tracked 失败降级;MAX_COMMANDS 上限 |
| 模块 <300 | `cmd_history.py` 预估 ~210 行;`commands.py` 不增(逻辑入本模块) |
| opt-in 默认关 | `capture_command_history: False` + 知情同意提示 |

## 9. 测试策略(TDD,stdlib unittest,合成 fixture 不依赖真实 history)

- `parse_zsh`:EXTENDED_HISTORY 带 ts / 裸行无 ts / 续行拼接 / 脏行(乱码字节,`errors="replace"`)/ 空文件。
- `parse_bash`:`#epoch` 给下一条打 ts / 连续裸命令 / `#epoch` 后无命令 / 孤立裸命令。
- `references_repo`:命中绝对路径 / 命中 basename(len≥4)/ 不命中短 basename(`src`)/ 命中含「/」tracked 路径 / 不命中裸 `README.md` / tracked=None 时仅靠路径。
- `repo_commands`:过滤 + 脱敏(含 secret 的命令被打码)+ MAX_COMMANDS 截断。
- `soft_commit`:ts 在窗内命中 / 窗外不命中 / ts=None 返 [] / 去重 / 上限 3。
- `build_commands_view`:有命令出时间线 + 软对齐行 + 脚注;无命令友好提示;含「时间未知」分组;绝不抛(脏输入)。
- `commands_cmd`:flag 关 → 不读 history + 出知情同意提示(返回 0,patch config);flag 开(env 覆盖)→ 正常路径(patch history 路径指向 fixture)。
- 验收:`python3 -m unittest discover -s tests` 全绿;`wc -l vibetrace/cmd_history.py` < 300;`grep -c LLMClient vibetrace/cmd_history.py` == 0(零 LLM)。

## 10. 诚实边界(写进输出脚注 + README,不可越界宣称)

命令是「敲了什么」非「为什么」;文本+时间软对齐**可能不准**;只收录**显式引用本仓**的命令(保守、必漏)。它是会话捕获盲区的**补充活动证据**,**不是**因果归因、**不是**完整命令日志、**不**保证捕全。
