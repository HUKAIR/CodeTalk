# codetalk web 单镜像(自托管接地对话)。纯 Python + vanilla-JS,无 node 构建链。
# 隐私红线:数据不出本机 —— 容器内监听地址经 CODETALK_WEB_HOST=0.0.0.0 放开,但请务必
# 用 `-p 127.0.0.1:8000:8000` 只映射到宿主 loopback;应用仍靠 Host 头校验拒绝非 loopback
# 访问,零遥测、绝不 phone home(除 LLM 调用)。
#
# 用法(数据留在运行机器);各行末反斜杠续行,勿把中文说明连行内一起粘:
#   docker build -t codetalk .
#   docker run --rm -p 127.0.0.1:8000:8000 \
#     -v "$PWD:/repo:ro" \
#     -v "$HOME/.codetalk:/root/.codetalk" \
#     -v "$HOME/.claude/projects:/root/.claude/projects:ro" \
#     codetalk
#   # 挂载:$PWD=你的 git 仓(只读);~/.codetalk=cache.db/config(读写);
#   #       ~/.claude/projects=可选会话原话接地源(只读)
#   打开 http://127.0.0.1:8000/   (零出网/无 key:加 -e CODETALK_NO_LLM=1)
FROM python:3.11-slim
WORKDIR /app
# Privacy boundary: copy only runtime inputs. Git-ignored local files such as
# .mcp.json, .codetalk/, or private planning notes must never enter the image.
COPY pyproject.toml README.md LICENSE /app/
COPY codetalk /app/codetalk
RUN pip install --no-cache-dir -e ".[web]"
ENV CODETALK_WEB_HOST=0.0.0.0
EXPOSE 8000
ENTRYPOINT ["python", "-m", "codetalk", "web", "--no-open", "--port", "8000", "--project", "/repo"]
