"""会话摘要(recap)解析核心:会话 jsonl → 逐轮结构 + 索引元信息。

每轮由一条真实用户消息(或 /命令调用)开启:你问 / 结论(最后一个 assistant
文本块的首个有效行,截到首个句号或 120 字符)/ 改动文件 / 工具计数 / 折叠全文 /
开轮时间戳。全程零 LLM、零网络、纯 stdlib;吃 ~/.claude/projects 的会话 jsonl,
容错解析(坏行计数跳过,绝不崩溃);isSidechain 侧链行不入主线摘要。
scan_meta 为索引页提供单遍流式的轻量元信息(63MB 级大会话也不整读入内存)。
隐私红线:所有入页文本先 redact_secrets(渲染层落盘前再兜底一遍)。
渲染(索引页 + 详情页)在 recap_render.py,本模块只管解析。
"""
import json
import re
from collections import Counter
from pathlib import Path

from .config import redact_secrets
from .sessions import (CLAUDE_PROJECTS, WRITE_TOOLS, _parse_ts, head_tail,
                       missing_dir_msg, project_slug)

ASK_CAP = 400          # 与 sessions.PROMPT_CAP 同级:入页提问首尾截断
CONCL_CAP = 120        # 结论行:首个句号(。/.)或 120 字符,取先到者
FULLTEXT_CAP = 20000   # 每轮折叠全文上限,超出截断并注明
PREVIEW_LEN = 50       # 索引页每条真实提问预览的截断长度
# 伪装成 user 的系统注入,含即中(对齐 Claude Code 实测记录形态)
SYSTEM_MARKERS = ("<system-reminder>", "<task-notification>",
                  "<local-command-stdout>", "<local-command-caveat>",
                  "[SYSTEM NOTIFICATION")
# 前缀即中:"<" 覆盖各类标签开头的注入(<command-name> 已在此前单独识别为命令轮)
SYSTEM_PREFIXES = ("<", "[Request interrupted", "Stop hook feedback:",
                   "Base directory for this skill:",
                   "The previous response failed")


def _user_text(msg):
    """user 消息文本:content 字符串/块列表两态;含 tool_result 的行属于当前轮 → None。"""
    c = msg.get("content")
    if isinstance(c, str):
        return c.strip() or None
    if isinstance(c, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
            return None
        text = "\n".join((b or {}).get("text") or "" for b in c
                         if isinstance(b, dict) and b.get("type") == "text").strip()
        return text or None
    return None


def _classify(obj, txt):
    """user 行分类 → 'real' | 'command' | 'skip'(系统伪装/元信息)。"""
    if obj.get("isMeta") or obj.get("isCompactSummary") or txt is None:
        return "skip"
    if "<command-name>" in txt:
        return "command"
    if any(m in txt for m in SYSTEM_MARKERS):
        return "skip"
    if txt.lstrip().startswith(SYSTEM_PREFIXES):
        return "skip"
    return "real"


def _command_ask(txt):
    name = re.search(r"<command-name>(.*?)</command-name>", txt, re.S)
    args = re.search(r"<command-args>(.*?)</command-args>", txt, re.S)
    return ((name.group(1).strip() if name else "?") + " "
            + (args.group(1).strip() if args else "")).strip()


def _first_valid_line(text):
    """首个有意义的行:跳过空行与纯 markdown 符号行,剥标题井号。"""
    for line in text.splitlines():
        s = line.strip()
        if not s or not re.search(r"[^\s#*\-=`~>|_:.]", s):
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
            if not s:
                continue
        return s
    return None


def _conclusion(text):
    """结论行:首个有效行,截到首个句号(。/.)或 120 字符,取先到者。"""
    line = _first_valid_line(text)
    if not line:
        return None
    m = re.search(r"[。.]", line)
    if m and m.end() <= CONCL_CAP:
        return line[:m.end()]
    return line if len(line) <= CONCL_CAP else line[:CONCL_CAP] + "…"


def parse_session(path):
    """单个会话 jsonl → {"session_id","turns",...}。容错:坏行计数,绝不 raise。"""
    s = {"session_id": path.stem, "turns": [], "start": None, "end": None,
         "parse_failures": 0, "tools_total": Counter()}
    cur = None
    last_ts = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                s["parse_failures"] += 1
                continue
            if not isinstance(obj, dict):
                s["parse_failures"] += 1
                continue
            if obj.get("isSidechain"):
                continue                      # 侧链(子 agent)行不入主线摘要
            ts = _parse_ts(obj.get("timestamp"))
            if ts:
                s["start"] = min(s["start"] or ts, ts)
                s["end"] = max(s["end"] or ts, ts)
                last_ts = ts
            rtype = obj.get("type")
            if rtype == "user":
                sid = obj.get("sessionId")
                if sid:
                    s["session_id"] = sid
                txt = _user_text(obj.get("message") or {})
                kind = _classify(obj, txt)
                if kind == "skip":
                    continue
                ask = _command_ask(txt) if kind == "command" else txt
                cur = {"kind": kind, "ts": ts or last_ts,   # 开轮时刻(缺则回落上一条已见)
                       "ask": redact_secrets(head_tail(ask, ASK_CAP)),
                       "texts": [], "tools": Counter(), "files": {}}
                s["turns"].append(cur)
            elif rtype == "assistant":
                if obj.get("isApiErrorMessage") or cur is None:
                    continue
                for b in (obj.get("message") or {}).get("content") or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text":     # thinking 块自然跳过
                        text = (b.get("text") or "").strip()
                        if text:
                            cur["texts"].append(text)
                    elif b.get("type") == "tool_use":
                        name = b.get("name") or "?"
                        cur["tools"][name] += 1
                        s["tools_total"][name] += 1
                        inp = b.get("input") or {}
                        target = inp.get("file_path") or inp.get("notebook_path")
                        if name in WRITE_TOOLS and isinstance(target, str) and target:
                            cur["files"][Path(target).name] = target
    for turn in s["turns"]:
        concl = _conclusion(turn["texts"][-1]) if turn["texts"] else None
        turn["concl"] = redact_secrets(concl) if concl else None
        full = "\n\n".join(turn["texts"])
        if len(full) > FULLTEXT_CAP:
            full = full[:FULLTEXT_CAP] + "\n\n…已截断,完整内容见原始会话记录"
        turn["full"] = redact_secrets(full)
        del turn["texts"]
    return s


def scan_meta(path):
    """索引页轻量元信息:单遍流式扫描,只留时段/轮数/前 2 条真实提问预览,不留全文。
    与 parse_session 同一套 _user_text/_classify 判定,保证索引轮数 == 详情页轮数。"""
    m = {"sid": path.stem, "start": None, "end": None, "turns": 0,
         "previews": [], "size": path.stat().st_size}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or obj.get("isSidechain"):
                continue
            ts = _parse_ts(obj.get("timestamp"))
            if ts:
                m["start"] = min(m["start"] or ts, ts)
                m["end"] = max(m["end"] or ts, ts)
            if obj.get("type") != "user":
                continue
            txt = _user_text(obj.get("message") or {})
            kind = _classify(obj, txt)
            if kind == "skip":
                continue
            m["turns"] += 1
            if kind == "real" and len(m["previews"]) < 2:
                one = txt.replace("\n", " ").strip()
                if len(one) > PREVIEW_LEN:
                    one = one[:PREVIEW_LEN] + "…"
                m["previews"].append(redact_secrets(one))
    return m


def _sessions_dir(project_path):
    return CLAUDE_PROJECTS / project_slug(project_path)


def _pick_session(project_path, session=None):
    """挑会话文件 → (path, error)。默认最近改动的主线转录;--session 按 ID 前缀匹配。
    子 agent 侧链转录在 <sessionId>/subagents/ 子目录,顶层 glob 天然排除。"""
    sessions_dir = _sessions_dir(project_path)
    if not sessions_dir.is_dir():
        return None, missing_dir_msg(sessions_dir)
    files = sorted(sessions_dir.glob("*.jsonl"))
    if session:
        files = [p for p in files if p.stem.startswith(session)]
        if not files:
            return None, f"没有匹配的会话:{session}"
    if not files:
        return None, "没有找到 Claude Code 会话记录"
    return max(files, key=lambda p: p.stat().st_mtime), None


def console_payload(project_path):
    """给 console 第 7 视图的有界载荷:最近会话逐轮 ask/结论/文件/工具,无全文。
    容错红线:任何失败(目录缺失/解析异常)都返回 None,绝不拖垮控制台装配。"""
    try:
        path, err = _pick_session(Path(project_path).resolve())
        if err:
            return None
        s = parse_session(path)
        if not s["turns"]:
            return None
        return {"session_id": s["session_id"],
                "turns": [{"kind": t["kind"], "ask": t["ask"], "concl": t["concl"],
                           "files": sorted(t["files"]),
                           "tools": [[n, c] for n, c in t["tools"].most_common()]}
                          for t in s["turns"]]}
    except Exception:                     # noqa: BLE001 — 旁路视图,降级不崩溃
        return None
