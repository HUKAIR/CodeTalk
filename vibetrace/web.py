"""vibetrace web —— 自托管接地对话 web app 后端(FastAPI)。需 pip install -e ".[web]"。

隐私红线(继承):默认仅绑 127.0.0.1(不暴露 --host);每请求新 Cache 连接;
出口 redact_secrets 兜底;LLM 出网受 no_llm 硬开关(--no-llm / config / env)。
Phase 2 v1:非流式 /api/chat + 只读端点;SSE 流式、SPA 静态托管见后续 Phase。
本模块仅在 `vibetrace web` 时按需 import;CLI/MCP 不依赖它,核心仍纯 stdlib。

注:沙箱无 fastapi/uvicorn,本文件未在 CI 跑通;落地需真机 `pip install -e ".[web]"`
后 smoke test(`vibetrace web` → curl /api/chat 验证接地对话链路)。接地/脱敏/降级
核心逻辑在 chat.py/retrieval.py(已 TDD),本文件只是其 HTTP 外壳。
"""
import datetime
import json
import os
import webbrowser
from pathlib import Path
from string import Template
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import (HTMLResponse, JSONResponse, Response,
                               StreamingResponse)
from pydantic import BaseModel

from .webserve import inline_json
from . import chat, console, filetree, tunnel
from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_data, redact_secrets
from .graph import build_graph_json
from .llm import LLMClient, LLMError
from .report import _OUTCOMES
from .search import topic_search

app = FastAPI(title="vibetrace web")
_DEFAULT_PROJECT = "."
_CHAT_HTML = Template((Path(__file__).parent / "web_chat.html").read_text(encoding="utf-8"))
# 前端零外联红线:connect-src 'self' 让页面只能 fetch 同源 /api(LLM egress 仅后端发);
# inline 脚本/样式沿用既有单文件 HTML 范式,故 script/style 放 'unsafe-inline'。
_CSP = ("default-src 'self'; connect-src 'self'; img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'")


@app.middleware("http")
async def _csp_header(request, call_next):
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
            f"padding:24px'>控制台暂不可用:{err}</body>", status_code=400)
    return HTMLResponse(html)


@app.get("/tunnel")
def tunnel_view(project: Optional[str] = None):
    """接已设计好的「时光轴」(线性时间线 + 气球 hover)。serve=True → 胶囊可回写。"""
    html, _name, err = tunnel._build_html(_project(project), serve=True)
    if err:
        return HTMLResponse(
            "<body style='background:#0d0d0f;color:#e8e8ea;font-family:sans-serif;"
            f"padding:24px'>时光轴暂不可用:{err}</body>", status_code=400)
    return HTMLResponse(html)


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
    out["answer"] = redact_secrets(out["answer"])   # 出口兜底脱敏
    for cit in out.get("citations", []):            # 引用证据 + 结构化来源出口同样脱敏
        cit["evidence"] = redact_secrets(cit.get("evidence", ""))
        cit["sources"] = redact_data(cit.get("sources") or [])
    return JSONResponse(out)


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
                    for cit in ev.get("citations", []):
                        cit["evidence"] = redact_secrets(cit.get("evidence", ""))
                        cit["sources"] = redact_data(cit.get("sources") or [])
                yield "data: " + json.dumps(ev, ensure_ascii=False) + "\n\n"
        finally:
            cache.close()

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/search")
def api_search(q: str, project: Optional[str] = None):
    cache = Cache(CACHE_DB_PATH)
    try:
        return {"text": topic_search(cache, _project(project), q)}
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
        return JSONResponse({"error": err}, status_code=400)
    return Response(content=js, media_type="application/json")


@app.get("/api/projects")
def api_projects():
    cache = Cache(CACHE_DB_PATH)
    try:
        return {"projects": cache.distinct_projects()}
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
        os.environ["VIBETRACE_NO_LLM"] = "1"
    url = f"http://127.0.0.1:{port}/"
    print(f"vibetrace web:{url}(接地对话 POST /api/chat;数据不出本机,Ctrl+C 停)")
    if not no_open:
        try:
            webbrowser.open(url)
        except Exception:                          # noqa: BLE001 开浏览器失败不影响服务
            pass
    uvicorn.run(app, host="127.0.0.1", port=port)
