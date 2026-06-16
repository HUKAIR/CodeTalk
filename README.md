# vibetrace

本地优先的个人 AI 编码认知层(M0)。把 `git log` 与 Claude Code 会话记录
合成为"做了什么 / 为什么 / 替你做了哪些决定"的中文日报,写入 Obsidian vault,
偿还 AI 高速写码欠下的**理解债**。

DeepWiki 类工具回答"代码是什么";vibetrace 回答"代码是怎么变成这样的"。

## 安装

无需安装依赖(标准库 + 可选 anthropic SDK):

```bash
git clone <repo> && cd CodeTalk
python3 -m vibetrace digest --help      # 或 ./vibetrace-cli digest --help
```

要求 Python ≥ 3.11。仅当使用 anthropic provider 时需要 `pip install anthropic`。

## 配置

`~/.vibetrace/config.json`(建议 `chmod 600`):

```json
{
  "vault_path": "/path/to/obsidian/vault/folder",
  "provider": "deepseek",
  "model": "deepseek-v4-pro",
  "diff_token_budget": 3000,
  "providers": {
    "deepseek":  {"base_url": "https://api.deepseek.com/v1", "api_key": "sk-..."},
    "openai":    {"base_url": "https://api.openai.com/v1", "api_key": ""},
    "qwen":      {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key": ""},
    "anthropic": {"api_key": ""}
  }
}
```

API key 也可用环境变量提供:`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` /
`QWEN_API_KEY` / `ANTHROPIC_API_KEY`。deepseek / openai / qwen 走 OpenAI
兼容协议(标准库 urllib,零额外依赖;DeepSeek 上下文缓存自动生效);
anthropic 走官方 SDK(json_schema 结构化输出;系统提示设有 cache_control,
但低于模型最小可缓存前缀时缓存不生效——M0 的提示规模即属此类)。

## 用法

```bash
python3 -m vibetrace digest --project ~/Github/MyApp --since "3 days ago"
# 覆盖项:--vault DIR --provider NAME --model ID
```

产物:`<vault>/YYYY-MM-DD-<project>.md` —— 去年今日 / 上月今日回流(若有)
→ 今日概览(信件体)+ 今日决定 → 今日开启的时间胶囊(到期的旧 risk,供回填)
→ 按 commit 的叙事(改了什么 / 为什么 / 关键决策 / 风险 / 未闭环)→ 未闭环汇总
→ 运行统计页脚。时间胶囊把每条 risk 密封 21 天,到期在日报里端回面前。

## 缓存与隐私

- commit 叙事以 SHA 为键缓存于 `~/.vibetrace/cache.db`,**永不重算**;
  重跑同一天 digest 为 0 次 LLM 调用、亚秒级返回
- 会话解析以 (session_id, mtime, size) 增量缓存
- 每次运行参数追加到 `~/.vibetrace/usage.log`(仅记录,不分析)
- 数据不出本机(LLM API 调用除外);常见 secret 模式(API key / token)
  在写缓存与日报前脱敏

## 已知限制(M0)

- 只解析主会话转写(`<sessionId>.jsonl`);subagent / workflow 子转写中的
  文件改动对齐不可见
- 会话-commit 对齐是软关联(±30 分钟时间窗 + 文件交集),目标准确率 80%,
  结果带 high/low 置信度标注,**不保证全对**
- commit 被 amend / rebase 后 SHA 变化即视为新 commit;旧 SHA 缓存成为死数据
- diff 截断用字符数近似 token(×4),非精确计数
- 日报按天覆盖写入;同日多次运行以最后一次为准
- 会话 JSONL 是 Claude Code 非官方内部格式(实测规格见
  `docs/claude-jsonl-schema.md`,基于 2.1.143–2.1.170);版本升级可能破坏解析,
  解析器对未知字段忽略、缺字段降级,最坏退化为纯 git 模式

## 架构

```
cli → gitlog(commit+diff) ─┐
      sessions(JSONL 容错) ─┼→ align(软关联) → enrich(LLM,SHA 缓存) → report → vault
      cache(SQLite)        ─┘                    llm(多 provider 统一封装)
```
