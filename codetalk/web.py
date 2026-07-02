"""codetalk web —— 自托管接地对话 web app 后端(FastAPI)。需 pip install -e ".[web]"。

隐私红线(继承):默认仅绑 127.0.0.1(不暴露 --host);每请求新 Cache 连接;
出口 redact_secrets 兜底;LLM 出网受 no_llm 硬开关(--no-llm / config / env)。
Phase 2 v1:非流式 /api/chat + 只读端点;SSE 流式、SPA 静态托管见后续 Phase。
本模块仅在 `codetalk web` 时按需 import;CLI/MCP 不依赖它,核心仍纯 stdlib。

注:web 路由有 TestClient 覆盖;发布前仍建议真机 `pip install -e ".[web]"`
后 smoke test(`codetalk web` → curl /api/chat 验证接地对话链路)。接地/脱敏/降级
核心逻辑在 chat.py/retrieval.py(已 TDD),本文件只是其 HTTP 外壳。
"""
import datetime
import json
import os
import re
import webbrowser
from pathlib import Path
from string import Template
from typing import Optional
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from .webserve import inline_json
from . import chat, console, course, filetree, gitlog, tunnel
from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_data, redact_secrets
from .graph import build_graph_json, render_graph_html
from .llm import LLMClient, LLMError
from .report import _OUTCOMES
from .search import topic_search

app = FastAPI(title="CodeTalk web")
_DEFAULT_PROJECT = "."
_CHAT_HTML = Template((Path(__file__).parent / "web_chat.html").read_text(encoding="utf-8"))
# 前端零外联红线:connect-src 'self' 让页面只能 fetch 同源 /api(LLM egress 仅后端发);
# inline 脚本/样式沿用既有单文件 HTML 范式,故 script/style 放 'unsafe-inline'。
_CSP = ("default-src 'self'; connect-src 'self'; img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@app.middleware("http")
async def _local_request_guard(request: Request, call_next):
    """Local web app guard: CSP protects our page, but not cross-site POSTs to
    127.0.0.1. Reject DNS-rebind Host headers and browser requests whose Origin
    is not the same loopback origin. CLI/curl with no Origin remains allowed."""
    host = request.url.hostname
    if host not in _LOOPBACK_HOSTS:
        return JSONResponse({"error": "bad host"}, status_code=403)
    origin = request.headers.get("origin")
    if origin:
        try:
            op = urlsplit(origin)
        except ValueError:
            return JSONResponse({"error": "bad origin"}, status_code=403)
        if op.hostname not in _LOOPBACK_HOSTS or op.netloc != request.url.netloc:
            return JSONResponse({"error": "bad origin"}, status_code=403)
    resp = await call_next(request)
    resp.headers["Content-Security-Policy"] = _CSP
    return resp


@app.get("/")
def index(project: Optional[str] = None):
    pp = _project(project)
    html = _CHAT_HTML.substitute(tree_data=inline_json(redact_data(filetree.tree_payload(pp))))
    return HTMLResponse(redact_secrets(html))


@app.get("/console")
def console_view(project: Optional[str] = None):
    """接已设计好的「统一控制台」(四视图单页)。serve=True → 页面可答胶囊/标回看,
    经 /capsule、/reviewed 写回 cache.db。复用 console._build_html。"""
    html, _name, err = console._build_html(_project(project), serve=True, chat=True)
    if err:
        return HTMLResponse(
            "<body style='background:#0d0d0f;color:#e8e8ea;font-family:sans-serif;"
            f"padding:24px'>控制台暂不可用:{redact_secrets(str(err))}</body>",
            status_code=400)
    return HTMLResponse(redact_secrets(html))


@app.get("/tunnel")
def tunnel_view(project: Optional[str] = None):
    """接已设计好的「时光轴」(线性时间线 + 气球 hover)。serve=True → 胶囊可回写。"""
    html, _name, err = tunnel._build_html(_project(project), serve=True)
    if err:
        return HTMLResponse(
            "<body style='background:#0d0d0f;color:#e8e8ea;font-family:sans-serif;"
            f"padding:24px'>时光轴暂不可用:{redact_secrets(str(err))}</body>",
            status_code=400)
    return HTMLResponse(redact_secrets(html))


def _err_page(kind, err):
    return HTMLResponse(
        "<body style='background:#0d0d0f;color:#e8e8ea;font-family:sans-serif;"
        f"padding:24px'>{kind}暂不可用:{redact_secrets(str(err))}</body>",
        status_code=400)


@app.get("/graph")
def graph_view(project: Optional[str] = None):
    """富交互决策影响图 DAG(零 LLM);与 CLI `codetalk graph` 同一渲染,浏览器内可达。"""
    html, err = render_graph_html(_project(project))
    if err:
        return _err_page("决策图", err)
    return HTMLResponse(redact_secrets(html))


@app.get("/course")
def course_view(project: Optional[str] = None):
    """演进课程(项目怎么长成的);无 key 时自动降级为零-LLM 朴素章节,不崩。"""
    html, err = course.render_course_html(_project(project))
    if err:
        return _err_page("演进课程", err)
    return HTMLResponse(redact_secrets(html))


def _llm():
    """构造 LLMClient;no_llm/无 key → LLMError → None(chat.answer 据此降级零-LLM)。"""
    try:
        return LLMClient(load_config())
    except LLMError:
        return None


def _project(p):
    return Path(p or _DEFAULT_PROJECT).resolve()


class ChatReq(BaseModel):
    question: str
    project: Optional[str] = None
    conv_id: str = "c1"
    target: Optional[str] = None
    turn_seq: int = 0


class CapsuleReq(BaseModel):
    capsule_id: str
    outcome: str


class ReviewedReq(BaseModel):
    sha: str


@app.post("/api/chat")
def api_chat(req: ChatReq):
    cache = Cache(CACHE_DB_PATH)
    try:
        out = chat.answer(cache, _llm(), _project(req.project), req.question,
                          target=req.target, conv_id=req.conv_id,
                          turn_seq=req.turn_seq,
                          now=datetime.datetime.now().astimezone().isoformat())
    finally:
        cache.close()
    # 整体脱敏响应(递归所有字符串叶子):一次覆盖 answer + citations(evidence/sources/
    # verbatim)+ highlights。取代逐字段脱敏——后者易漏:新增字段静默绕过(verbatim/
    # highlights 曾因此把原始面包屑 secret 泄露到浏览器)。verbatim 源自 merge_breadcrumbs
    # 并入未脱敏的 raw git 面包屑,必须在出口收口。
    return JSONResponse(redact_data(out))


@app.post("/api/chat/stream")
def api_chat_stream(req: ChatReq):
    """SSE 流式接地对话。逐块 token 出口再脱敏(输入已在 chat 内 C-1 整体收口,
    跨块 secret 极不可能——LLM 只读到已脱敏材料;落库由 save_turn 再脱)。"""
    cache = Cache(CACHE_DB_PATH)

    def gen():
        try:
            for ev in chat.answer_stream(
                    cache, _llm(), _project(req.project), req.question,
                    target=req.target, conv_id=req.conv_id, turn_seq=req.turn_seq,
                    now=datetime.datetime.now().astimezone().isoformat()):
                if ev.get("type") == "token":
                    ev["text"] = redact_secrets(ev["text"])
                elif ev.get("type") == "done":
                    ev = redact_data(ev)   # 整体脱敏 done 事件:覆盖 citations(含 verbatim)+
                                           # highlights,防字段枚举遗漏(曾泄露到浏览器)
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
        finally:
            cache.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/search")
def api_search(q: str, project: Optional[str] = None):
    cache = Cache(CACHE_DB_PATH)
    try:
        return redact_data({"text": topic_search(cache, _project(project), q)})
    finally:
        cache.close()


@app.get("/api/graph")
def api_graph(project: Optional[str] = None):
    cache = Cache(CACHE_DB_PATH)
    try:
        js, err = build_graph_json(_project(project), cache)
    finally:
        cache.close()
    if err:
        return JSONResponse(redact_data({"error": err}), status_code=400)
    try:
        return JSONResponse(redact_data(json.loads(js)))
    except (ValueError, TypeError):
        return JSONResponse({"error": "graph unavailable"}, status_code=500)


_SHA_PARAM = re.compile(r"[0-9a-fA-F]{7,40}")


@app.get("/api/commit/{sha}")
def api_commit(sha: str, project: Optional[str] = None):
    """点引用 SHA → 看真实 commit(message + 面包屑 + diff),把「可核验」落到浏览器里。
    零 LLM、纯本地 git show;SHA 严格 hex 校验防 git 参数注入(leading-dash 当 flag)。"""
    if not _SHA_PARAM.fullmatch(sha):
        return JSONResponse({"error": "bad sha"}, status_code=400)
    pp = _project(project)
    date_iso, subject = gitlog.commit_meta(pp, sha)
    body = gitlog.commit_body(pp, sha)
    diff = gitlog.commit_diff(pp, sha, char_budget=8000)
    if not subject and not diff:
        return JSONResponse({"error": "commit not found"}, status_code=404)
    return JSONResponse(redact_data({          # 出口整体脱敏:message/面包屑/diff 均可能含 secret
        "sha": sha, "date": date_iso, "subject": subject,
        "body": body, "diff": diff}))


@app.get("/api/projects")
def api_projects():
    cache = Cache(CACHE_DB_PATH)
    try:
        return redact_data({"projects": cache.distinct_projects()})
    finally:
        cache.close()


@app.post("/capsule")
def api_capsule(req: CapsuleReq):
    """console/tunnel 答待验证胶囊 → 写回 cache。outcome 白名单防任意串(同 webserve)。"""
    if req.outcome not in _OUTCOMES:
        return JSONResponse({"error": "bad outcome"}, status_code=400)
    cache = Cache(CACHE_DB_PATH)
    try:
        cache.set_capsule_outcome(req.capsule_id, req.outcome, str(_project(None)))
    finally:
        cache.close()
    return {"ok": True}


@app.post("/reviewed")
def api_reviewed(req: ReviewedReq):
    """console/tunnel 展开一条 → 标记回看(还理解债信号)写回 cache。"""
    if not req.sha:
        return JSONResponse({"error": "bad sha"}, status_code=400)
    cache = Cache(CACHE_DB_PATH)
    try:
        cache.mark_reviewed(str(_project(None)), req.sha)
    finally:
        cache.close()
    return {"ok": True}


def serve(project=".", port=8000, no_open=False, no_llm=False):
    """绑 127.0.0.1 起服务(不暴露 --host,守隐私红线);no_llm → 全局关 LLM。"""
    global _DEFAULT_PROJECT
    _DEFAULT_PROJECT = project
    if no_llm:
        os.environ["CODETALK_NO_LLM"] = "1"
    url = f"http://127.0.0.1:{port}/"
    print(f"codetalk web:{url}(接地对话 POST /api/chat;数据不出本机,Ctrl+C 停)")
    if not no_open:
        try:
            webbrowser.open(url)
        except Exception:                          # noqa: BLE001 开浏览器失败不影响服务
            pass
    # 默认绑 127.0.0.1(守隐私红线)。仅容器内经 CODETALK_WEB_HOST=0.0.0.0 放开监听地址,
    # 此时仍靠 _local_request_guard 拒绝非 loopback Host,配合 `-p 127.0.0.1:8000:8000`
    # 端口映射,数据不出宿主机。非容器场景保持 127.0.0.1,行为不变。
    host = os.environ.get("CODETALK_WEB_HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
