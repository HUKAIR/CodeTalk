"""self 自我周报:零 LLM 解析 usage.log,聚合近 N 天用量,自证『关掉 LLM 仍有价值』。

usage.log 每行一条 JSON(report.append_usage 写入),含 command + ts(+ 视命令的计数:
llm_calls / tokens_in / tokens_out / cache_hits / cache_hit_tokens ...)。
全程纯本地、确定性,不出网、不调模型;坏行容错跳过,绝不崩溃。
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger("vibetrace")


def parse_lines(lines):
    """逐行解析为 dict;非 JSON / 缺 command 或 ts 的坏行跳过(容错红线)。"""
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(rec, dict) or "command" not in rec or "ts" not in rec:
            continue
        out.append(rec)
    return out


def _parse_ts(rec):
    try:
        ts = datetime.fromisoformat(rec["ts"])
    except (ValueError, TypeError, KeyError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def within_days(records, days):
    """保留 ts 在近 days 天内的记录;ts 不可解析的丢弃。"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    kept = []
    for rec in records:
        ts = _parse_ts(rec)
        if ts and ts >= cutoff:
            kept.append(rec)
    return kept


def _num(rec, key):
    """容错取数:缺失/非数字按 0 计,不让坏数据污染聚合。"""
    val = rec.get(key)
    return val if isinstance(val, (int, float)) else 0


def aggregate(records):
    """聚合:命令次数、LLM 调用、缓存命中省额(token)、零-LLM 运行数。"""
    counts = {}
    llm_calls = tokens_in = tokens_out = cache_hit_tokens = zero_llm_runs = 0
    for rec in records:
        cmd = str(rec.get("command", "?"))
        counts[cmd] = counts.get(cmd, 0) + 1
        calls = _num(rec, "llm_calls")
        llm_calls += calls
        tokens_in += _num(rec, "tokens_in")
        tokens_out += _num(rec, "tokens_out")
        cache_hit_tokens += _num(rec, "cache_hit_tokens")
        if calls == 0:                      # 这次运行没动 LLM
            zero_llm_runs += 1
    return {
        "counts": counts,
        "total_runs": len(records),
        "llm_calls": llm_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_hit_tokens": cache_hit_tokens,
        "zero_llm_runs": zero_llm_runs,
    }


def render(agg, days, fill):
    """朴素自我周报(纯文本)。fill=(已开启胶囊数, 已回填数)→ 回填率。"""
    lines = [f"# vibetrace 自我周报(近 {days} 天)", ""]
    if agg["total_runs"] == 0:
        lines.append("暂无用量记录:这段时间还没跑过任何命令。")
        return "\n".join(lines)

    lines.append(f"总运行 {agg['total_runs']} 次,其中 "
                 f"{agg['zero_llm_runs']} 次零 LLM。")
    lines.append("")
    lines.append("## 命令次数")
    for cmd, n in sorted(agg["counts"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {cmd}:{n}")
    lines.append("")

    lines.append("## LLM 用量与省额")
    lines.append(f"- LLM 调用:{agg['llm_calls']} 次")
    lines.append(f"- token:输入 {agg['tokens_in']} / 输出 {agg['tokens_out']}")
    if agg["cache_hit_tokens"]:
        lines.append(f"- 缓存命中省下输入 token:{agg['cache_hit_tokens']}"
                     "(prompt caching / 叙事缓存)")
    lines.append("")

    opened, filled = fill
    rate = f"{filled}/{opened}" + (
        f"({filled * 100 // opened}%)" if opened else "")
    lines.append("## 预测回填率(北极星)")
    lines.append(f"- 到期胶囊回填:{rate}" if opened
                 else "- 到期胶囊回填:暂无已开启的胶囊")
    lines.append("")

    # 自证:关掉 LLM 仍有价值
    share = (agg["zero_llm_runs"] * 100 // agg["total_runs"]
             if agg["total_runs"] else 0)
    lines.append("## 关掉 LLM 仍有价值")
    lines.append(f"- {share}% 的运行完全不调用 LLM(brief/graph/blame/watch/"
                 "tunnel/console 等本地视图),纯本地也能用。")
    return "\n".join(lines)


def aggregate_fill(cache):
    """跨所有项目累加胶囊回填统计 → (已开启数, 已回填数),供 self 周报的北极星指标。"""
    opened = filled = 0
    for proj in cache.distinct_projects():
        o, f = cache.capsule_fill_stats(proj)
        opened += o
        filled += f
    return opened, filled


def build_self_report(log_path, days, fill):
    """读 usage.log → 解析 → 近 N 天 → 聚合 → 渲染。文件缺失/读失败时降级为空报告。"""
    path = Path(log_path)
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError) as exc:
        log.warning("usage.log 读取失败(%s),自我周报无数据可聚合", exc)
        text = ""
    records = within_days(parse_lines(text.splitlines()), days)
    return render(aggregate(records), days, fill)
