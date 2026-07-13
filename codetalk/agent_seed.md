<!-- codetalk-agent-seed -->
## codetalk 决策捕获(AI coding agent 必读)

每次 `git commit`,在 commit message 正文按下面格式留下这次改动的**关键决策与推导**,
供 codetalk 作为决策记录长期分析(ask / graph / digest 据此接地,免得日后从 diff 反推)。保持精炼:
每条一行、总共几行即可,别写长文。**行首精确、区分大小写**。

- `Vibe-Decision: <做了什么决定;为什么这么选>` —— 一个关键决策一行,可多条
- `Vibe-Rejected: <认真考虑过但放弃的备选 + 为何弃>` —— 被否决方案一条一行,可多条;
  这是 diff 结构性取不到的 **why-NOT**,`blame` 会在你日后改到该处时独立标出「否决备选(曾放弃)」,
  防你/AI **重引入**已否决方案(codetalk 护城河:对抗 AI 反推式编造被否决备选)
- `Vibe-Watch: <没把握、需日后验证的点>` —— 风险 / 待验证,可多条

例:

    Vibe-Decision: 用 --no-merges 跳合并 —— 叙事只要功能提交
    Vibe-Rejected: --first-parent —— 保留合并气泡、丢功能提交,叙事更差
    Vibe-Watch: 空提交尾部 NUL subject 未处理,罕见暂不管
