# docs 截图目录

`docs/mcp-install.md` 的可选截图素材放这里。**文件名固定如下**——如果要发布图文版,
按名保存到本目录后,在对应章节插入引用即可。建议宽度 ≤ 1600px、PNG。

| 文件名 | 内容 | 对应章节 |
|---|---|---|
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
