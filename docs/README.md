# docs 目录索引

vibetrace 的文档地图。策略/发现类集中在 `discovery/`,设计规格/计划在 `superpowers/`,顶层放产品介绍、试点报告与参考规格。

## 顶层
- [产品介绍与功能链条](产品介绍与功能链条.md) — 产品定位 + 功能链条(对外介绍)
- [claude-jsonl-schema](claude-jsonl-schema.md) — Claude Code 会话 JSONL 非官方格式实测规格(解析器的依据)
- [mcp-install](mcp-install.md) — MCP 各客户端一键装 + 自检 + 排错
- [2026-06-12 交互设计愿景](2026-06-12-interaction-design-vision.md) · [2026-06-16 产品流程研究](2026-06-16-product-flow-study.md)
- 自我试点报告:[2026-06-18(早期 6 命令)](2026-06-18-pilot-report.md) · [2026-06-25(全命令面)](2026-06-25-pilot-report.md)

## discovery/ — 发现 / 策略(证据底座 + 决策归档)
- `README.md` — 问卷处理 SOP(差距分析→交叉引用→对抗复审→折 ROADMAP)
- `2026-06-22-vibetrace-pm-brief.md` — ICP / JTBD / 竞品坐标 / 北极星的证据底座(决策门 `vibetrace-pm` 的权威依据)
- `gap-analysis-问卷N.md` / `修正意见-问卷N.md` — 各份用户深访的差距分析与修正
- `2026-06-25~27-外部对标-第N轮.md` — 竞品/学术对标各轮(变现、幻觉检测、code-review 等)
- `护城河与北极星验证` / `接地命中率自证` / `接地召回自证` / `护城河盲测` — 可复跑的自证报告
- `2026-06-27-北极星-踩坑拦截-dogfood协议.md` + `interceptions.md` — 防事故里程碑的协议与拦截记录(现 0)
- `2026-06-29-战略评估汇总-会话档.md` — 一组产品/战略提议的 vibetrace-pm 裁决归档(桌面软件/飞书/变现/出网等)
- `2026-06-29-护城河对照卡-真实记录vs反推.md` — G2 素材:真实记录 vs 纯 diff 反推并排(给受访者测信任位移),复跑 `scripts/blind_test.py`
- `2026-06-29-G2验证问卷-信任位移+主力工具.md` — 可发的验证问卷:主力工具/会话可找回(破 N=1)+ 盲对照验「引真实记录 vs 反推」信任差值能否 ≥3 人复现(据问卷1/2/3 校准,含冷外联超短版 + 发放/记账/判据)
- `2026-06-29-G2发放SOP-一页.md` — G2 整条流程的一页发放 SOP(ASCII 流程图 + 每阶段要点 + 记账表头 + 判据)

## superpowers/
- `specs/` — 功能设计规格(brainstorm 产物) · `plans/` — 实施计划(写代码前的分步计划)

## images/
- 文档配图资源
