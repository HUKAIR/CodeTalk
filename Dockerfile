# vibetrace web 单镜像(自托管接地对话)。纯 Python + vanilla-JS,无 node 构建链。
# 隐私红线:数据不出本机 —— 服务绑 127.0.0.1,镜像零遥测、绝不 phone home(除 LLM 调用)。
#
# 用法(数据留在客户自己机器):
#   docker build -t vibetrace .
#   docker run --rm -p 127.0.0.1:8000:8000 \
#     -v "$PWD:/repo:ro" \                                    # 你的 git 仓(只读)
#     -v "$HOME/.vibetrace:/root/.vibetrace" \                # cache.db / config(读写)
#     -v "$HOME/.claude/projects:/root/.claude/projects:ro" \ # 可选:会话原话接地源
#     vibetrace
#   打开 http://127.0.0.1:8000/   (零出网/无 key:加 -e VIBETRACE_NO_LLM=1)
#
# 注:沙箱无 docker,本文件未构建验证;落地需真机 `docker build` smoke test。
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e ".[web]"
EXPOSE 8000
ENTRYPOINT ["python", "-m", "vibetrace", "web", "--no-open", "--port", "8000", "--project", "/repo"]
