"""report 命令:从当前仓状态确定性生成一份「汇报」HTML(零 LLM、纯本地只读)。

像 console/tunnel 那样可 --serve 本地起服务 + 自动开浏览器。三块内容:
① 变更日志(最近 commit:短 SHA + 日期 + subject)
② 决策面包屑覆盖(N/M 带 Vibe-Decision/Watch)
③ Discovery 发现(已处理问卷清单 + ROADMAP「发现驱动的方向修正」段要点)

容错铁律:无 git / 无 ROADMAP / 无 docs/discovery / 非 git 仓 → 友好降级,绝不抛。
出口脱敏:返回前整页 redact_secrets(commit subject 可能含 secret)。
"""
import html as _html
import re
from datetime import datetime
from pathlib import Path

from .config import load_config, redact_secrets
from .gitlog import collect_commit_files, parse_breadcrumbs

CHANGELOG_LIMIT = 20
DISCOVERY_HEADING = "发现驱动的方向修正"


def _esc(text):
    return _html.escape(str(text or ""))


def _bold(text):
    """轻量把 **...** 转成 <strong>...</strong>(先转义,后注入安全标签)。
    脱敏须在"去 ** 标记的连续文本"上做:secret 若被 ** 劈断会逃过最终整页脱敏,
    故去标记后命中 secret 则放弃该行加粗、回退脱敏纯文本(安全 > 装饰)。"""
    raw = str(text or "")
    demarked = re.sub(r"\*\*(.+?)\*\*", r"\1", raw)
    if redact_secrets(demarked) != demarked:        # secret(可能被 ** 劈断)→ 安全回退
        return _esc(redact_secrets(demarked))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", _esc(raw))


def _changelog_section(commits):
    """① 变更日志:最近 CHANGELOG_LIMIT 条 commit(新→旧)。"""
    recent = list(reversed(commits))[:CHANGELOG_LIMIT]  # collect 返回旧→新
    if not recent:
        return ['<section><h2>变更日志</h2>'
                '<p class="empty">没有可读的 git 历史。</p></section>']
    rows = ['<section><h2>变更日志</h2>',
            f'<p class="sub">最近 {len(recent)} 条提交</p>', '<ul class="log">']
    for c in recent:
        rows.append(
            f'<li><code>{_esc(c["sha"][:8])}</code>'
            f'<span class="date">{c["date"]:%Y-%m-%d}</span>'
            f'<span class="subj">{_esc(c["subject"])}</span></li>')
    rows.append('</ul></section>')
    return rows


def _coverage_section(commits):
    """② 决策面包屑覆盖:最近 CHANGELOG_LIMIT 条里几条带 Vibe-Decision/Watch。"""
    recent = list(reversed(commits))[:CHANGELOG_LIMIT]
    if not recent:
        return ['<section><h2>决策面包屑覆盖</h2>'
                '<p class="empty">暂无提交可统计。</p></section>']
    got = sum(1 for c in recent if any(parse_breadcrumbs(c.get("body", ""))))
    m = len(recent)
    pct = round(got / m * 100) if m else 0
    return ['<section><h2>决策面包屑覆盖</h2>',
            f'<p class="big">{got}/{m}</p>',
            f'<p class="sub">最近 {m} 条提交中有 <strong>{got}</strong> 条'
            f'带 Vibe-Decision / Vibe-Watch 面包屑({pct}%)。</p></section>']


def _questionnaire_list(project):
    """已处理问卷:glob docs/discovery/gap-analysis-问卷*.md(失败返回 [])。"""
    try:
        return sorted(p.name for p in
                      (project / "docs" / "discovery").glob(
                          "gap-analysis-问卷*.md"))
    except OSError:
        return []


def _parse_discovery_sections(text):
    """解析 ROADMAP 中所有 `^## 发现驱动的方向修正...` 段(到下一个 `^## `)。
    返回 [(标题, [要点 - ...]), ...];任何异常都吞掉返回 []。"""
    sections = []
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## ") and DISCOVERY_HEADING in line:
            title = line[3:].strip()
            points = []
            i += 1
            while i < len(lines) and not lines[i].startswith("## "):
                stripped = lines[i].strip()
                if stripped.startswith("- "):
                    points.append(stripped[2:].strip())
                i += 1
            sections.append((title, points))
        else:
            i += 1
    return sections


def _discovery_section(project):
    """③ Discovery 发现:问卷清单 + ROADMAP「发现驱动」段要点。读失败→降级空块。"""
    parts = ['<section><h2>Discovery 发现</h2>']

    quests = _questionnaire_list(project)
    if quests:
        parts.append('<h3>已处理问卷</h3><ul class="quest">')
        parts += [f'<li><code>{_esc(q)}</code></li>' for q in quests]
        parts.append('</ul>')

    sections = []
    roadmap = project / "ROADMAP.md"
    try:
        sections = _parse_discovery_sections(
            roadmap.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        sections = []

    for title, points in sections:
        parts.append(f'<h3>{_bold(title)}</h3>')
        if points:
            parts.append('<ul class="points">')
            parts += [f'<li>{_bold(p)}</li>' for p in points]
            parts.append('</ul>')

    if not quests and not sections:
        parts.append('<p class="empty">未发现问卷或 ROADMAP 发现段。</p>')
    parts.append('</section>')
    return parts


_CSS = """
:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;
--bd:#30363d;--ac:#58a6ff;--code:#1f2430}
*{box-sizing:border-box}
body{margin:0;font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",
"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg)}
.wrap{max-width:880px;margin:0 auto;padding:32px 20px 80px}
h1{font-size:26px;margin:0 0 4px}
.meta{color:var(--mut);margin:0 0 28px}
section{background:var(--card);border:1px solid var(--bd);border-radius:12px;
padding:20px 22px;margin-bottom:20px}
h2{font-size:18px;margin:0 0 12px;border-bottom:1px solid var(--bd);
padding-bottom:8px}
h3{font-size:15px;margin:18px 0 8px;color:var(--ac)}
.sub{color:var(--mut);margin:0 0 12px;font-size:13px}
.empty{color:var(--mut);font-style:italic}
.big{font-size:40px;font-weight:700;margin:0;color:var(--ac)}
code{background:var(--code);padding:1px 6px;border-radius:5px;font-size:12.5px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
ul{margin:0;padding-left:0;list-style:none}
ul.points,ul.quest{padding-left:18px;list-style:disc}
ul.points li,ul.quest li{margin:5px 0}
ul.log li{display:flex;gap:10px;align-items:baseline;padding:5px 0;
border-bottom:1px solid var(--bd);flex-wrap:wrap}
ul.log li:last-child{border-bottom:none}
.date{color:var(--mut);font-size:12.5px;white-space:nowrap}
.subj{flex:1}
.themebtn{position:fixed;top:16px;right:16px;background:var(--card);
color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:6px 12px;
cursor:pointer;font-size:13px}
[data-theme=light]{--bg:#f6f8fa;--fg:#1f2328;--mut:#656d76;--card:#fff;
--bd:#d0d7de;--ac:#0969da;--code:#eff1f3}
@media(prefers-color-scheme:light){:root:not([data-theme=dark]){
--bg:#f6f8fa;--fg:#1f2328;--mut:#656d76;--card:#fff;--bd:#d0d7de;
--ac:#0969da;--code:#eff1f3}}
"""

_THEME_JS = """
var b=document.getElementById('themebtn');
b.onclick=function(){var r=document.documentElement;
var cur=r.getAttribute('data-theme');
var nxt=cur==='light'?'dark':(cur==='dark'?'light':
(matchMedia('(prefers-color-scheme: light)').matches?'dark':'light'));
r.setAttribute('data-theme',nxt);};
"""


def _build_briefing(project_path):
    """从当前仓状态确定性生成自包含汇报 HTML。→ (html_text, err)。
    任何读取失败 → 返回(降级 HTML, None),绝不抛。出口前整页脱敏。"""
    project = Path(project_path).resolve()
    body = []
    try:
        commits, err = collect_commit_files(project)
        if err:
            commits = []          # 非 git / 空仓 / git 失败 → 降级空历史,不报错
    except Exception:             # noqa: BLE001 — 容错铁律:解析外部数据绝不崩
        commits = []

    body += _changelog_section(commits)
    body += _coverage_section(commits)
    body += _discovery_section(project)

    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    doc = (
        '<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(project.name)} 汇报</title>'
        f'<style>{_CSS}</style></head><body>'
        '<button id="themebtn">明/暗</button>'
        '<div class="wrap">'
        f'<h1>{_esc(project.name)} · 汇报</h1>'
        f'<p class="meta">本地生成 · {_esc(generated)} · 零 LLM 确定性快照</p>'
        + "".join(body) +
        f'</div><script>{_THEME_JS}</script></body></html>'
    )
    return redact_secrets(doc), None


def render_report(project_path):
    """写静态汇报 HTML 到 vault(file://,只读)。→ (path|None, err)。"""
    html_text, err = _build_briefing(project_path)
    if err:
        return None, err
    vault = Path(load_config()["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / (Path(project_path).resolve().name + "-report.html")
    out.write_text(html_text, encoding="utf-8")
    return out, None


def serve_report(project_path, open_browser=True):
    """起本地服务托管汇报 HTML(127.0.0.1)。→ err_or_None(阻塞到 Ctrl+C)。
    实时性:每次启动从当前仓状态重建(快照,与 console 一致)。"""
    html_text, err = _build_briefing(project_path)
    if err:
        return err
    from .webserve import serve_html
    return serve_html(html_text, project_path, open_browser)
