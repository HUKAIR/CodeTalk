"""Weekly postcard, monochrome editorial edition (M1 experiment, v2).

Design language after enxiliuart.com and datacurve.ai: near-black canvas,
grotesque display type with tight tracking, small mono labels, hairline
dividers, dot-matrix data, a single pure-red accent. No glow, no ornament.

One self-contained HTML file. Zero dependencies, zero LLM calls —
everything quoted comes verbatim from cached narratives (Dear Data
principle: one metric, your own words).
"""
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .gitlog import collect_commits

WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def _day_series(commits, narratives, today):
    """Per-day decision counts for the last 7 days (commit count fallback)."""
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    series = []
    for day in days:
        decisions = commits_n = 0
        for commit in commits:
            if commit["date"].astimezone().date() != day:
                continue
            commits_n += 1
            narrative = narratives.get(commit["sha"]) or {}
            decisions += len(narrative.get("decisions") or [])
        series.append({"day": day, "label": WEEKDAYS[day.weekday()],
                       "value": decisions or commits_n})
    return series


def _dot_matrix(series):
    """Seven columns of stacked dots; the peak day's top dot is pure red."""
    peak = max((p["value"] for p in series), default=0)
    columns = []
    for p in series:
        dots = "".join(
            '<i{}></i>'.format(' class="r"' if (p["value"] == peak and peak
                               and i == p["value"] - 1) else "")
            for i in range(p["value"]))
        columns.append(
            f'<div class="col"><span class="n">{p["value"] or "·"}</span>'
            f'<div class="dots">{dots}</div>'
            f'<span class="d">{p["label"]}</span></div>')
    return "".join(columns)


def _pick_quote(commits, narratives):
    """Longest decision of the week — your own words, verbatim."""
    best = ""
    for commit in commits:
        for decision in (narratives.get(commit["sha"]) or {}).get("decisions") or []:
            if len(decision) > len(best):
                best = decision
    return best or "本周没有留下决定的痕迹。"


def _commit_index(commits):
    rows = []
    for commit in commits:
        when = commit["date"].astimezone().strftime("%m.%d")
        rows.append(f'<li><span class="t">{when}</span>'
                    f'<span class="s">{escape(commit["subject"])}</span>'
                    f'<span class="h">{commit["sha"][:7]}</span></li>')
    return "".join(rows)


def _open_questions(commits, narratives, limit=3):
    items = []
    for commit in reversed(commits):  # newest first
        narrative = narratives.get(commit["sha"]) or {}
        for item in (narrative.get("risks") or []) + (narrative.get("open_loops") or []):
            if item not in items and "材料不足" not in item:
                items.append(item)
    return items[:limit]


TEMPLATE = Template("""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$week_id — $project</title>
<style>
  :root { --fg: #ededed; --mid: #a0a0a0; --dim: #6b6b6b;
          --line: #232323; --red: #ff0000; }
  * { box-sizing: border-box; }
  body { background: #0a0a0a; color: var(--fg); margin: 0;
         font-family: "Helvetica Neue", "Neue Haas Grotesk", -apple-system,
           "PingFang SC", "Noto Sans CJK SC", sans-serif;
         -webkit-font-smoothing: antialiased; }
  .page { max-width: 880px; margin: 0 auto; padding: 56px 40px 72px; }
  .mono { font-family: "SF Mono", ui-monospace, "JetBrains Mono", Menlo,
          monospace; font-size: 11px; letter-spacing: .08em;
          text-transform: uppercase; color: var(--dim); }
  header { display: flex; justify-content: space-between;
           padding-bottom: 14px; border-bottom: 1px solid var(--line); }
  .quote { font-size: 38px; line-height: 1.18; letter-spacing: -.015em;
           font-weight: 500; margin: 72px 0 0; max-width: 22em; }
  .quote-src { margin: 22px 0 0; }
  .quote-src .red { color: var(--red); }
  section { margin-top: 88px; }
  .label { padding-bottom: 12px; border-bottom: 1px solid var(--line);
           display: flex; justify-content: space-between; }
  .matrix { display: flex; gap: 44px; align-items: flex-end;
            padding: 36px 2px 0; }
  .col { display: flex; flex-direction: column; align-items: center;
         gap: 10px; }
  .dots { display: flex; flex-direction: column-reverse; gap: 7px;
          min-height: 120px; justify-content: flex-start; }
  .dots i { width: 7px; height: 7px; border-radius: 50%;
            background: var(--mid); }
  .dots i.r { background: var(--red); }
  .col .n { font-family: "SF Mono", ui-monospace, monospace; font-size: 12px;
            color: var(--fg); }
  .col .d { font-family: "SF Mono", ui-monospace, monospace; font-size: 10px;
            letter-spacing: .12em; color: var(--dim); }
  ol.index { list-style: none; margin: 0; padding: 0; }
  ol.index li { display: flex; gap: 28px; align-items: baseline;
            padding: 14px 2px; border-bottom: 1px solid var(--line);
            font-size: 14.5px; }
  ol.index .t, ol.index .h { font-family: "SF Mono", ui-monospace, monospace;
            font-size: 11.5px; color: var(--dim); flex: 0 0 auto; }
  ol.index .s { flex: 1; color: var(--mid); }
  ol.questions { list-style: none; margin: 0; padding: 0;
            counter-reset: q; }
  ol.questions li { counter-increment: q; display: flex; gap: 28px;
            padding: 20px 2px; border-bottom: 1px solid var(--line);
            font-size: 15.5px; line-height: 1.65; color: var(--mid); }
  ol.questions li::before { content: counter(q, decimal-leading-zero);
            font-family: "SF Mono", ui-monospace, monospace; font-size: 11.5px;
            color: var(--red); padding-top: 4px; }
  footer { margin-top: 96px; padding-top: 14px;
           border-top: 1px solid var(--line); display: flex;
           justify-content: space-between; }
</style></head><body>
<div class="page">
  <header>
    <span class="mono">Vibetrace — 週記</span>
    <span class="mono">$week_id · $project</span>
  </header>

  <p class="quote">「$quote」</p>
  <p class="quote-src mono"><span class="red">●</span>&nbsp; 本周你写下的一个决定
     — a decision you made, verbatim</p>

  <section>
    <div class="label"><span class="mono">每日决定 — Decisions / Day</span>
      <span class="mono">$date_range</span></div>
    <div class="matrix">$matrix</div>
  </section>

  <section>
    <div class="label"><span class="mono">本周目录 — Index</span>
      <span class="mono">$commits commits</span></div>
    <ol class="index">$index</ol>
  </section>

  <section>
    <div class="label"><span class="mono">未验证 — Open Questions</span>
      <span class="mono">awaiting your return</span></div>
    <ol class="questions">$questions</ol>
  </section>

  <footer>
    <span class="mono">Local-first · 数据未离开这台机器</span>
    <span class="mono">$stamp_date</span>
  </footer>
</div></body></html>
""")


def render_postcard(project_path, since="7 days ago"):
    """Build the weekly postcard; returns (output_path, error_or_None)."""
    cfg = load_config()
    project_path = Path(project_path).resolve()
    commits, err = collect_commits(project_path, since, 200)
    if err:
        return None, err
    if not commits:
        return None, f"{since} 以来没有 commit,本周无可记。"
    cache = Cache(CACHE_DB_PATH)
    narratives = {c["sha"]: cache.get_narrative(c["sha"]) for c in commits}
    cache.close()

    today = datetime.now(timezone.utc).astimezone().date()
    series = _day_series(commits, narratives, today)
    questions = _open_questions(commits, narratives) or ["本周没有悬而未决的事。"]
    week_no = today.isocalendar()[1]
    html_text = TEMPLATE.substitute(
        project=escape(project_path.name),
        week_id=f"{today.year}-W{week_no:02d}",
        quote=escape(_pick_quote(commits, narratives)),
        date_range=f"{series[0]['day']:%m.%d}–{series[-1]['day']:%m.%d}",
        matrix=_dot_matrix(series),
        index=_commit_index(commits),
        commits=len(commits),
        questions="".join(f"<li>{escape(q)}</li>" for q in questions),
        stamp_date=f"{today:%Y.%m.%d}",
    )
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / f"{today.year}-W{week_no:02d}-{project_path.name}-postcard.html"
    out.write_text(html_text, encoding="utf-8")
    return out, None
