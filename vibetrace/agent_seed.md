<!-- vibetrace-agent-seed -->
## vibetrace 决策捕获(AI coding agent 必读)

每次 `git commit`,在 commit message 正文按下面格式留下这次改动的**关键决策与推导**,
供 vibetrace 长期分析(ask / graph / digest 据此接地,免得日后从 diff 反推)。保持精炼:
每条一行、总共几行即可,别写长文。**行首精确、区分大小写**。

- `Vibe-Decision: <做了什么决定;为什么这么选;否决了什么备选>` —— 一个关键决策一行,可多条
- `Vibe-Watch: <没把握、需日后验证的点>` —— 风险 / 待验证,可多条

例:

    Vibe-Decision: 用 --no-merges 跳合并而非 --first-parent —— 后者保留合并气泡、丢功能提交,叙事更差
    Vibe-Watch: 空提交尾部 NUL subject 未处理,罕见暂不管
