"""Weekly postcard, Hong Kong neon edition (M1 experiment).

One self-contained HTML file: the week rendered as a neon signboard.
Design language: HK neon signs (M+ NEONSIGNS.HK), Beiwei-style vertical
signage, Wong Kar-wai red/green. Zero dependencies, zero LLM calls —
everything quoted comes verbatim from cached narratives (Dear Data
principle: one metric, your own words).
"""
import math
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from string import Template

from .cache import Cache
from .config import CACHE_DB_PATH, load_config
from .gitlog import collect_commits

# 周字:用 conventional-commit 前缀选一个总结本周的招牌大字(繁体应港味)
PREFIX_CHAR = [("feat", "建"), ("fix", "修"), ("docs", "記"),
               ("refactor", "拾"), ("chore", "理"), ("test", "驗")]
DEFAULT_CHAR = "碼"
WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"]


def _week_char(commits):
    counts = {}
    for commit in commits:
        for prefix, char in PREFIX_CHAR:
            if commit["subject"].startswith(prefix):
                counts[char] = counts.get(char, 0) + 1
                break
    return max(counts, key=counts.get) if counts else DEFAULT_CHAR


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


def _neon_spark(series):
    """Hand-drawn neon polyline: deterministic jitter, no straight lines."""
    peak = max((p["value"] for p in series), default=0) or 1
    points, dots, labels = [], [], []
    for i, p in enumerate(series):
        x = 40 + i * 70
        y = 150 - (p["value"] / peak) * 105
        jitter = 4 * math.sin(p["day"].toordinal() * 2.3 + i)
        y = round(y + jitter, 1)
        points.append(f"{x},{y}")
        dots.append(f'<circle cx="{x}" cy="{y}" r="4.5" fill="#2ee6c8"/>'
                    f'<text x="{x}" y="{y - 14}" class="num">{p["value"]}</text>')
        labels.append(f'<text x="{x}" y="180" class="day">{p["label"]}</text>')
    return (f'<polyline points="{" ".join(points)}" fill="none" '
            f'stroke="#ff2d78" stroke-width="3" stroke-linejoin="round" '
            f'filter="url(#glow)"/>' + "".join(dots) + "".join(labels))


def _pick_quote(commits, narratives):
    """Longest decision of the week — your own words, verbatim."""
    best = ""
    for commit in commits:
        for decision in (narratives.get(commit["sha"]) or {}).get("decisions") or []:
            if len(decision) > len(best):
                best = decision
    return best or "本週沒有留下決定的痕跡。"


def _open_lamps(commits, narratives, limit=3):
    lamps = []
    for commit in reversed(commits):  # newest first
        narrative = narratives.get(commit["sha"]) or {}
        for item in (narrative.get("risks") or []) + (narrative.get("open_loops") or []):
            if item not in lamps and "材料不足" not in item:
                lamps.append(item)
    return lamps[:limit]


TEMPLATE = Template("""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<title>$week_id · $project 霓虹週記</title>
<style>
  body { background: #0b0b10; margin: 0; display: flex; justify-content: center;
         align-items: center; min-height: 100vh;
         font-family: "Kaiti TC", "Kaiti SC", "STKaiti", serif; }
  .card { width: 920px; background:
            radial-gradient(ellipse at 75% 8%, #1d1626 0%, #0e0e14 55%, #08080c 100%);
          border: 1px solid #26222e; border-radius: 6px; display: flex;
          padding: 38px 40px; box-sizing: border-box; gap: 36px;
          box-shadow: 0 30px 80px #000; }
  .sign { writing-mode: vertical-rl; text-align: center; flex: 0 0 150px;
          border: 3px solid #ff2d78; border-radius: 10px; padding: 18px 10px;
          box-shadow: 0 0 18px #ff2d7866, inset 0 0 24px #ff2d7822; }
  .sign .big { font-family: "Songti TC", "Songti SC", serif; font-weight: 900;
          font-size: 120px; color: #ffd9e8; line-height: 1;
          text-shadow: 0 0 8px #ff2d78, 0 0 22px #ff2d78, 0 0 60px #ff2d78; }
  .sign .sub { font-size: 15px; color: #2ee6c8; letter-spacing: 8px;
          margin-right: 10px; text-shadow: 0 0 12px #2ee6c8aa; }
  main { flex: 1; color: #cfc8bd; }
  h1 { font-size: 21px; font-weight: normal; color: #2ee6c8; margin: 0 0 2px;
       letter-spacing: 5px; text-shadow: 0 0 14px #2ee6c877; }
  .meta { font-size: 12px; color: #6d6678; letter-spacing: 2px; }
  .metric-title { margin: 22px 0 0; font-size: 13px; color: #9b93a6; }
  svg { display: block; }
  .num { fill: #ffd9e8; font-size: 13px; text-anchor: middle;
         font-family: inherit; }
  .day { fill: #6d6678; font-size: 12px; text-anchor: middle;
         font-family: inherit; }
  .quote { border-left: 3px solid #1f6e54; background: #11161422;
           margin: 18px 0 0; padding: 10px 14px; font-size: 15px;
           line-height: 1.8; color: #b8d8c4; }
  .quote em { color: #5a8f6e; font-style: normal; font-size: 12px;
           display: block; margin-top: 4px; }
  .lamps { margin: 18px 0 0; padding: 0; list-style: none; font-size: 13.5px;
           line-height: 1.9; color: #c8a96a; }
  .lamps li::before { content: "•  "; color: #ff9d2d;
           text-shadow: 0 0 8px #ff9d2d; }
  .lamps-title, .footer { font-size: 12px; color: #6d6678; letter-spacing: 2px; }
  .lamps-title { margin-top: 20px; }
  .footer { margin-top: 24px; display: flex; justify-content: space-between;
            align-items: flex-end; }
  .stamp { width: 84px; height: 84px; border: 2px solid #8a4a52;
           border-radius: 50%; color: #b06a72; font-size: 11px; display: flex;
           flex-direction: column; justify-content: center; text-align: center;
           letter-spacing: 1px; transform: rotate(-12deg); opacity: .85; }
</style></head><body>
<div class="card">
  <div class="sign"><div class="big">$week_char</div>
    <div class="sub">本週招牌字</div></div>
  <main>
    <h1>霓虹週記 · $project</h1>
    <div class="meta">$date_range · 第 $week_no 週 · 此燈為你而亮</div>
    <p class="metric-title">本週唯一的度量:每日落下的決定</p>
    <svg width="520" height="190" viewBox="0 0 520 190">
      <defs><filter id="glow"><feGaussianBlur stdDeviation="3.2"
        result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/>
        </feMerge></filter></defs>
      $spark
    </svg>
    <div class="quote">「$quote」<em>—— 本週你親手寫下的一個決定</em></div>
    <p class="lamps-title">未熄的燈(待你回來驗證)</p>
    <ul class="lamps">$lamps</ul>
    <div class="footer">
      <span>$commits 個 commit · 霓虹易逝,記得回看</span>
      <div class="stamp"><span>VIBETRACE</span><span>$stamp_date</span>
        <span>HONG KONG NEON</span></div>
    </div>
  </main>
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
        return None, f"{since} 以來沒有 commit,招牌沒得亮。"
    cache = Cache(CACHE_DB_PATH)
    narratives = {c["sha"]: cache.get_narrative(c["sha"]) for c in commits}
    cache.close()

    today = datetime.now(timezone.utc).astimezone().date()
    series = _day_series(commits, narratives, today)
    lamps = _open_lamps(commits, narratives) or ["這週的燈都熄好了。"]
    week_no = today.isocalendar()[1]
    html_text = TEMPLATE.substitute(
        project=escape(project_path.name),
        week_id=f"{today.year}-W{week_no:02d}",
        week_char=_week_char(commits),
        week_no=week_no,
        date_range=f"{series[0]['day']:%m.%d} – {series[-1]['day']:%m.%d}",
        spark=_neon_spark(series),
        quote=escape(_pick_quote(commits, narratives)),
        lamps="".join(f"<li>{escape(l)}</li>" for l in lamps),
        commits=len(commits),
        stamp_date=f"{today:%Y.%m.%d}",
    )
    vault = Path(cfg["vault_path"]).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    out = vault / f"{today.year}-W{week_no:02d}-{project_path.name}-postcard.html"
    out.write_text(html_text, encoding="utf-8")
    return out, None
