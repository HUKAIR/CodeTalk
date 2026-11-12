# docs 截图目录

公开 README、静态产品体验和 `docs/mcp-install.md` 的图片放在这里。
**文件名如下**。界面截图建议宽度不超过 1600px、使用 PNG；可维护的流程图使用无脚本、无外部资源的 SVG。

公开图片只使用品牌图、技术示意图或合成数据演示，不使用真实工作区截图。
提交前清除 EXIF、文本、生成/签名溯源等附加元数据，并运行
`python -m unittest tests.test_release_privacy.PublicSourcePrivacyCase`。

| 文件名 | 内容 | 对应章节 |
|---|---|---|
| `codetalk-logo-banner.png` | CodeTalk 品牌横幅 | README / 静态产品体验 |
| `codetalk-pipeline.svg` | V3 配色的可维护流程图；本地证据与可选模型边界 | README 深层架构章节 |
| `codetalk-pipeline.png` | 旧版流程图，保留历史参考 | 不再用于当前 README |
| `codetalk-console-v3.png` | 历史 V3 控制台，合成时光轴展开态 | 保留参考 |
| `codetalk-reading-room.png` | B 决策书房，真实后端读取合成 Git 记录 | README / docs/demo.md |
| `codetalk-review-proof.png` | 历史合成产品体验截图 | 保留参考 |
| `codetalk-review-demo.png` | 真实 UI + 虚构 Git 历史，保存判断后截图 | README / docs/demo.md |
| `mcp-desktop-install.png` | Claude Desktop → Settings → Extensions 安装 `codetalk-0.4.0.mcpb`,填 project 路径,启用后 7 个工具出现 | 3·A |
| `mcp-claude-code.png` | Claude Code:`.mcp.json` 配置 + `claude mcp list` 显示 CodeTalk connected | 3·B |
| `mcp-cursor.png` | Cursor Settings → MCP:CodeTalk 已连接、显示工具数 | 3·C |
| `mcp-call-result.png` | agent 实际调用 `codetalk_blame` / `codetalk_ask` 的接地返回 | 4 |

## 截好图后提交

按 [开发与合并规范](../development.md) 检查隐私、元数据和实际文件清单后，
通过分支与 PR 提交。不要使用裸 `git push` 或将目录中的所有图片盲目暂存。

## 来源与授权核验（2026-11-06）

Owner 在本次审查中确认仓库代码、品牌横幅、pipeline 图及历史截图为其原创。
本记录是 owner 声明，不是独立权属鉴定；本次不改变现有许可。
`codetalk-review-demo.png` 来自项目真实 UI 的合成数据演示。

`codetalk-pipeline.png` 含第三方产品标识，包括 Git、Claude、Cursor、OpenAI、
VS Code 和 Obsidian。原创图稿声明不涵盖这些标识的商标权或第三方许可；
公开前需核对品牌使用条件，或改为纯文字产品名称。不得将这些标识一并宣称
为 CodeTalk 原创或 AGPL 授权。其他三张图片未发现此类外部产品标识。

## 当前候选替换（2026-11-08）

当前 `codetalk-pipeline.png` 已替换为本次使用内置 imagegen 生成的原创纯文字流程图，
内容为本地记录 → 本地检索 → 查看原文；目视检查未发现第三方产品标识，
并经仓库 PNG sanitizer 清除附加元数据。生成要求明确禁止第三方标识、
水印和仿品牌图形；没有提供真实项目或会话数据。
这解决当前文件的标识问题，不改写历史，也不声称历史版本的标识已经获得授权。
公开整个 Git 历史时，旧图仍须纳入 owner 的具体公开决定。


## 当前展示统一（2026-11-10）

双语 README 与 demo 文档展示当前 V3 控制台及真实审查界面。
`codetalk-console-v3.png` 来自 `scripts.demo_ui` 的 console-dark 合成页面：
切到时光轴，展开第一条记录，桌面 viewport 截图；经现有 PNG sanitizer 清理元数据。
已有 `codetalk-review-demo.png` 仍是 V3 真实服务保存后的截图，未用原型替代。

新的 `codetalk-pipeline.svg` 是手工编写的仓库内矢量流程图；配色取自
`codetalk/ui-design.css`，没有第三方标识、外部资源或脚本。SVG 可直接维护文字和连接，
避免截图与生成图中文字难以更新。旧 PNG 原样保留，不再作为当前 README 的流程图。

## 当前决策书房（2026-11-11）

README 与 demo 已改用 `scripts.demo_reading_room` 的真实本机服务截图。
`codetalk-reading-room.png` 展示原始记录和来源旁注；`codetalk-review-demo.png`
展示合成记录的历史理由、人工确认冲突及改变计划后保存的回执。
全部 Git、会话和判断数据均为合成，PNG 经现有 sanitizer 去除附加元数据。
历史 V3 图保留，不再代表当前阅读布局。

当前书房图已更新为原始 B 结构的真实后端版本：顶部阅读模式、文件夹、纸页、来源印章、旁注和底部操作条。数据仍来自隔离合成 Git 演示；不使用原型写死的数据。
