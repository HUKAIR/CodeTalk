# docs 截图目录

公开 README、静态产品体验和 `docs/mcp-install.md` 的图片放在这里。
**文件名固定如下**，建议宽度不超过 1600px、使用 PNG。

| 文件名 | 内容 | 对应章节 |
|---|---|---|
| `codetalk-logo-banner.png` | CodeTalk 品牌横幅 | README / 静态产品体验 |
| `codetalk-pipeline.png` | 本地证据管道与隐私边界 | README 深层架构章节 |
| `codetalk-review-proof.png` | 已确认冲突并改变行动的成功决策审查 | README 第一屏 |
| `mcp-desktop-install.png` | Claude Desktop → Settings → Extensions 安装 `codetalk.mcpb`,填 project 路径,启用后 7 个工具出现 | 3·A |
| `mcp-claude-code.png` | Claude Code:`.mcp.json` 配置 + `claude mcp list` 显示 CodeTalk connected | 3·B |
| `mcp-cursor.png` | Cursor Settings → MCP:CodeTalk 已连接、显示工具数 | 3·C |
| `mcp-call-result.png` | agent 实际调用 `codetalk_blame` / `codetalk_ask` 的接地返回 | 4 |

## 截好图后提交

```bash
git add docs/images/*.png
git commit -m "docs(mcp): 补 MCP 安装/验证截图"
git push
```

保存截图后,把对应图片引用插进 `docs/mcp-install.md` 的章节下方。
