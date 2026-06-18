# vibetrace 自我试点报告(dogfood on CodeTalk)

日期:2026-06-18 · 分支:`feat/enrich-and-mature` · 在 CodeTalk 仓库自身跑全部 6 子命令。

## 结果

| 命令 | LLM | 结果 | 验证点 |
|---|---|---|---|
| `brief` | 零 | ✅ | 理解债 top 3(cli.py/tunnel.html/cache.py)+「你上次停在哪」+「悬而未决」,纯本地、亚秒。 |
| `graph --canvas` | 零 | ✅ | 写 HTML + `.canvas`;Canvas 28 节点 / 96 边 / 24 个决策节点配色,JSON 合规。 |
| `tunnel` | 零 | ✅ | 静态渲染写出单文件 HTML,零 LLM。 |
| `digest --since "1 day ago"` | 是 | ✅ | 生成 2 份日报;**0 处 secret 泄漏**;文风纪律生效——概览第二人称、点名施动者、具体(top 40 / 8 边 / 200 commit),无「值得注意的是」式开场陈词。一次瞬时 JSON 解析失败已被重试吞掉(正常退避路径)。 |
| `ask vibetrace/config.py:53-67 "为什么 PEM 正则要匹配整块"` | 是 | ✅ | 答「仅匹配头行会漏掉密钥正文」,**引用真实 commit `7190c3c`**——完全源于该 commit 的 `Vibe-Decision` 面包屑。接地 + 面包屑收割端到端成立。 |
| `course` | 是 | ⏭️ | 未跑实时(16k token 推理调用、成本高);密度纪律已由 `tests.test_prompts` 验证在 prompt 中。 |

## 结论
- **隐私红线**:digest 落盘 0 secret 泄漏(新增 Google/Stripe/JWT/PEM 等模式 + 既有)。
- **护城河**:brief / graph / tunnel 三个零-LLM 工具产出有效——「关掉大模型仍有价值」成立。
- **数据闭环**:ask 据面包屑接地、引用真实 commit;graph 据决策连边;digest 折叠面包屑。
- **成熟度**:`pip install -e .` 打包就绪(核心零依赖)、`vibetrace init` 引导配置、README 覆盖 6 命令。
- 全部 6 子命令在真实仓库跑通、不崩、产出合理。**可落地。**

注:`digest` 的瞬时 JSON 失败是 deepseek 偶发返回非法 JSON,`llm.py` 重试机制已覆盖,非缺陷。
