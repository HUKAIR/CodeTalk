"""recap 渲染层:会话索引页 + 会话详情页 双静态 HTML(零 LLM、零网络、纯 stdlib)。

索引页(<项目>-recap.html):全部会话按日期分组、新在前;每会话一张横条卡
(短 id / 起始时刻 / 时长 / 轮数 / 前 2 条真实提问预览 / 大小);已生成详情页的
卡可点击跳转,未生成的显示 `codetalk recap --session <id8>` 命令提示。
详情页(<项目>-recap-<sid8>.html):日期分组 sticky 目录 + 结论先行卡片
(时刻 + 类型徽章)+ 顶栏筛选 chips(全部/提问/命令/有改动)+ 迷你日程图
(按天分段、段宽∝轮数、段内刻度按当日 0-24h 定位、点击跳该日首轮)。
--serve(serve_recap):同两页每次 GET 现算,索引卡片链接改指 /s/<sid8> 路由,
纯读零 vault 写入;链接模式差异通过 _build_index 的 link_of 回调注入,渲染不分叉。
隐私红线:解析层字段级 redact_secrets 之外,两页落盘/出服务前整页再兜底脱敏一遍。
页面壳/样式在 recap.html / recap_index.html,本模块只装配数据。
"""
import html
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from urllib.parse import quote

from .ui_template import read_template
from . import recap
from .config import load_config, redact_secrets

TOC_CAP = 40           # 目录行提问截断


def _esc(text):
    return html.escape(text or "", quote=True)


def _tpl(name):
    return Template(read_template(name))


def _now_stamp():
    return f"{datetime.now(timezone.utc).astimezone():%Y.%m.%d}"


def _day_key(ts):
    return f"{ts.astimezone():%Y-%m-%d}" if ts else "unknown"


def _day_label(ts):
    return f"{ts.astimezone():%Y-%m-%d}" if ts else "(无时间)"


def _hm(ts):
    return f"{ts.astimezone():%H:%M}" if ts else "--:--"


def _human_size(n):
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    return f"{n / (1 << 10):.0f} KB"


def _human_dur(a, b):
    if not a or not b:
        return "—"
    m = int((b - a).total_seconds() // 60)
    return f"{m // 60}时{m % 60:02d}分" if m >= 60 else f"{m}分"


# ---------- 详情页(A 卡片流 + B 迷你日程图) ----------

def _minimap(turns):
    """按天分段:段宽∝轮数,段内刻度=该轮在当日 0-24h 的位置,点击跳该日首轮。"""
    order, days = [], {}
    for t in turns:
        k = _day_key(t["ts"])
        if k not in days:
            days[k] = []
            order.append(k)
        days[k].append(t["ts"])
    segs = []
    for k in order:
        tss = days[k]
        label = k[5:] if k != "unknown" else "无时间"
        ticks = []
        for ts in tss:
            if ts:
                lt = ts.astimezone()
                pct = (lt.hour * 3600 + lt.minute * 60 + lt.second) / 864
                ticks.append(f'<i style="left:{pct:.2f}%"></i>')
        segs.append(
            f'<a class="seg" style="flex-grow:{len(tss)}" href="#d-{k}" '
            f'title="{label} · {len(tss)} 轮">'
            f'<span class="ticks">{"".join(ticks)}</span>'
            f'<span class="seglbl">{label}<b>{len(tss)}</b></span></a>')
    return "".join(segs)


def _card(i, t, hm, edit):
    badge = ('<span class="tbadge cmd">⌘ 命令</span>' if t["kind"] == "command"
             else '<span class="tbadge ask">💬 提问</span>')
    rows = [f'<div class="row"><span class="lbl">你问</span>'
            f'<span class="ask">{_esc(t["ask"])}</span></div>',
            f'<div class="row"><span class="lbl">结论</span>'
            f'<span class="concl">{_esc(t["concl"] or "(无文本输出)")}</span></div>']
    if t["files"]:
        chips = " ".join(f'<span class="chip" title="{_esc(full)}">{_esc(base)}</span>'
                         for base, full in sorted(t["files"].items()))
        rows.append(f'<div class="row"><span class="lbl">改了</span>'
                    f'<span class="chips">{chips}</span></div>')
    if t["tools"]:
        parts = " ".join(f"{_esc(n)}×{c}" for n, c in t["tools"].most_common())
        rows.append(f'<details><summary>工具记录</summary>'
                    f'<div class="tools">{parts}</div></details>')
    if t["full"]:
        rows.append(f'<details><summary>全文</summary>'
                    f'<pre class="raw">{_esc(t["full"])}</pre></details>')
    return (f'<section class="card" id="turn-{i}" data-kind="{t["kind"]}" '
            f'data-edit="{edit}"><div class="head"><span class="hm">{hm}</span>'
            f'{badge}<span class="num">#{i}</span></div>' + "".join(rows)
            + "</section>")


def _toc_cards(turns):
    """左目录(日期分组)+ 卡片流(跨日插分割条,分割条即日程图跳转锚点)。"""
    toc, cards, cur = [], [], None
    for i, t in enumerate(turns, 1):
        key = _day_key(t["ts"])
        hm = _hm(t["ts"])
        edit = "1" if t["files"] else "0"
        if key != cur:
            if cur is not None:
                toc.append("</div>")
            toc.append(f'<div class="tgroup"><div class="tday">'
                       f'{_day_label(t["ts"])}</div>')
            cards.append(f'<div class="daybar" id="d-{key}">'
                         f'<span>{_day_label(t["ts"])}</span></div>')
            cur = key
        icon = "⌘" if t["kind"] == "command" else "💬"
        snip = t["ask"].replace("\n", " ")[:TOC_CAP]
        toc.append(f'<a href="#turn-{i}" data-kind="{t["kind"]}" data-edit="{edit}">'
                   f'<span class="thm">{hm}</span><span class="tic">{icon}</span>'
                   f'<span class="ttx">{_esc(snip)}</span></a>')
        cards.append(_card(i, t, hm, edit))
    toc.append("</div>")
    return "".join(toc), "".join(cards)


def _build_detail(path, s, project, index_href=None):
    turns = s["turns"]
    files = {b for t in turns for b in t["files"]}
    n_cmd = sum(1 for t in turns if t["kind"] == "command")
    stats = (f'共 <b>{len(turns)}</b> 轮(命令 {n_cmd})· 改动文件 '
             f'<b>{len(files)}</b> · 工具调用 <b>{sum(s["tools_total"].values())}</b>')
    span = " – ".join(f"{t.astimezone():%Y-%m-%d %H:%M}"
                      for t in (s["start"], s["end"]) if t)
    toc, cards = _toc_cards(turns)
    return _tpl("recap.html").substitute(
        project=_esc(project),            # 目录名可含元字符 → 转义防注入
        session=_esc(path.stem[:8]),
        index_href=_esc(index_href if index_href is not None else quote(f"{project}-recap.html")),
        generated=_now_stamp(),
        span=_esc(span),
        stats=stats,
        minimap=_minimap(turns),
        toc=toc,
        cards=cards)


# ---------- 索引页(C 形态:日期分组横条卡) ----------

def _sess_card(m, href):
    """一张会话横条卡。href 由调用方按链接模式注入(静态=文件名/None,serve=路由);
    无 href → 不可点,显示生成命令提示。"""
    sid8 = m["sid"][:8]
    meta = (f'<div class="meta"><span class="sid">{_esc(sid8)}</span>'
            f'<span>{_hm(m["start"])} 起</span>'
            f'<span>{_human_dur(m["start"], m["end"])}</span>'
            f'<span>{m["turns"]} 轮</span>'
            f'<span class="sz">{_human_size(m["size"])}</span></div>')
    pvs = "".join(f'<div class="pv">{_esc(p)}</div>' for p in m["previews"]) \
        or '<div class="pv none">(全命令轮,无自由提问)</div>'
    if href:
        return f'<a class="sess" href="{_esc(href)}">{meta}{pvs}</a>'
    return (f'<div class="sess">{meta}{pvs}'
            f'<div class="gen">codetalk recap --session {_esc(sid8)}</div></div>')


def _build_index(project, metas, link_of):
    groups = {}
    for m in metas:
        groups.setdefault(_day_key(m["start"]), []).append(m)
    day_order = sorted((k for k in groups if k != "unknown"), reverse=True)
    if "unknown" in groups:
        day_order.append("unknown")
    parts = []
    for day in day_order:
        rows = sorted(groups[day],
                      key=lambda m: m["start"].timestamp() if m["start"] else 0,
                      reverse=True)
        label = day if day != "unknown" else "(无时间戳)"
        parts.append(f'<div class="day"><b>{label}</b> · {len(rows)} 场</div>')
        parts += [_sess_card(m, link_of(m)) for m in rows]
    stats = f'{len(metas)} 场会话 · 共 {sum(m["turns"] for m in metas)} 轮'
    return _tpl("recap_index.html").substitute(
        project=_esc(project), generated=_now_stamp(),
        stats=stats, groups="".join(parts))


def render_recap(project_path, session=None):
    """写索引页 + 详情页到 vault → ([index_path, detail_path], error)。
    默认渲染最近会话的详情页;--session 按前缀只更新该会话详情页;
    两种走法都重扫全部会话元信息(scan_meta 单遍流式)刷新索引页链接状态。"""
    cfg = load_config()
    pp = Path(project_path).resolve()
    path, err = recap._pick_session(pp, session)
    if err:
        return None, err
    s = recap.parse_session(path)
    if not s["turns"]:
        return None, f"会话 {path.stem} 里没有可摘要的轮次"
    from . import report  # 零 LLM 命令:记一行用量,写失败不影响主流程
    report.append_usage({"command": "recap", "project": str(pp),
                         "turns": len(s["turns"])})
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    detail = vault / f"{pp.name}-recap-{path.stem[:8]}.html"
    detail.write_text(redact_secrets(_build_detail(path, s, pp.name)),
                      encoding="utf-8")
    metas = [recap.scan_meta(p)
             for p in sorted(recap._sessions_dir(pp).glob("*.jsonl"))]
    have = {p.name for p in vault.glob(f"{pp.name}-recap-*.html")}

    def _file_link(m):                        # 静态模式:已生成的详情页才可点
        name = f"{pp.name}-recap-{m['sid'][:8]}.html"
        return name if name in have else None

    index = vault / f"{pp.name}-recap.html"
    index.write_text(redact_secrets(_build_index(pp.name, metas, _file_link)),
                     encoding="utf-8")
    return [index, detail], None


def serve_recap(project_path, open_browser=True):
    """--serve:起 127.0.0.1 服务,/ 索引与 /s/<sid8> 详情每次 GET 都从会话 jsonl
    现算(F5 即最新);纯读零 vault 写入。新会话落盘后刷新索引即现、点击即算,
    无需重启(路由按当前目录 glob 动态发现)。→ err_or_None(阻塞到 Ctrl+C)。"""
    pp = Path(project_path).resolve()
    _, err = recap._pick_session(pp)          # 起服前确认有会话可看,复用既有报错
    if err:
        return err
    from . import report  # 零 LLM 命令:同 console serve,起点记一行用量(GET 不落盘)
    report.append_usage({"command": "recap", "project": str(pp), "serve": True})
    sess_dir = recap._sessions_dir(pp)

    def index():
        metas = [recap.scan_meta(p) for p in sorted(sess_dir.glob("*.jsonl"))]
        return redact_secrets(
            _build_index(pp.name, metas, lambda m: f"/s/{m['sid'][:8]}"))

    def route(path):                          # /s/<sid8> → 该会话详情的现算回调
        sid = path[3:] if path.startswith("/s/") else ""
        hits = [p for p in sess_dir.glob("*.jsonl")
                if p.stem.startswith(sid)] if sid else []
        if not hits:
            return None
        p = max(hits, key=lambda q: q.stat().st_mtime)
        return lambda: redact_secrets(_build_detail(p, recap.parse_session(p),
                                                    pp.name, index_href="/"))

    from .webserve import serve_html
    return serve_html(index(), pp, open_browser=open_browser,
                      builder=index, routes=route)
