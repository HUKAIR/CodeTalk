"""digest 子命令 — git+会话 → 按日变更叙事日报。

从 commands.py 拆出:digest 体量最大(占该模块过半),独立成模块以守住
单模块 <300 行红线;commands.py 仅保留各命令的轻量分发。
"""
import calendar
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import align, codex_sessions, cursor_sessions, enrich, gitlog, report, sessions
from .cache import Cache
from .config import CODETALK_DIR, load_config, redact_secrets
from .gitlog import parse_breadcrumbs
from .llm import LLMClient, LLMError

log = logging.getLogger("codetalk")

_PR_NOTICE_SENTINEL = CODETALK_DIR / ".pr_notice_shown"


def _maybe_pr_notice():
    """首次启用 PR 源时一次性告知(数据出本机、可关),之后静默。写不了 sentinel 也不崩。"""
    try:
        if _PR_NOTICE_SENTINEL.exists():
            return
        log.warning("已启用 PR 讨论源:将向 GitHub 查询本仓 PR 讨论,数据出本机;"
                    "可在 ~/.codetalk/config.json 的 sources 移除 \"pr\" 关闭。")
        _PR_NOTICE_SENTINEL.parent.mkdir(parents=True, exist_ok=True)
        _PR_NOTICE_SENTINEL.write_text("", encoding="utf-8")
    except OSError:
        pass


def _since_to_dt(since):
    """Loose mirror of common 'git --since' phrases, for session file filtering."""
    parts = since.split()
    units = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30,
             "months": 30, "hour": 1 / 24, "hours": 1 / 24}
    try:
        if len(parts) >= 2 and parts[-1] == "ago" and parts[1] in units:
            return datetime.now(timezone.utc) - timedelta(
                days=float(parts[0]) * units[parts[1]])
        return datetime.fromisoformat(since).astimezone(timezone.utc)
    except ValueError:
        return None  # git understands it; we just skip mtime pre-filtering


def _shift(d, *, years=0, months=0):
    """同一日历日往前推 N 月/年;溢出日(如 3/31→2/28)夹紧到月末。"""
    m = d.month - 1 - months
    y = d.year - years + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _sources(cfg, args):
    """会话源:默认 config.sources;--source 覆盖(both=claude+cursor;all=三源全开)。"""
    srcs = list(cfg.get("sources") or ["claude"])
    sel = getattr(args, "source", None)
    if sel == "both":
        return ["claude", "cursor"]
    if sel == "all":
        return ["claude", "cursor", "codex"]
    if sel:
        return [sel]
    return srcs


def coverage_nudge(total, narrated):
    """digest 收尾的零-LLM 叙事覆盖提示:有未叙事 commit 时返回一行提示,否则 None。
    digest 只富集 --since 窗口,窗口外新 commit 会悄悄拉低叙事覆盖——收尾如实点出缺口、
    引导 `codetalk enrich` 补全,不自动调 LLM(不偷花 token)。注:这是「有无叙事」的口径,
    比 grounding_hitrate.py 的「叙事 OR 面包屑」接地覆盖上限更严,故名『叙事覆盖』不混用。"""
    missing = total - narrated
    if total <= 0 or missing <= 0:
        return None
    pct = 100 * narrated / total
    return (f"叙事覆盖 {narrated}/{total} = {pct:.1f}%;{missing} 个 commit 仍无叙事"
            f" —— 跑 `codetalk enrich` 看计划,确认后加 `--allow-remote` 补全"
            "(digest 只富集 --since 窗口)。")


def _capsule_days():
    """胶囊到期窗口天数 + 是否 dogfood。env CODETALK_CAPSULE_DAYS 显式设值=dogfood 短窗:
    绕过 seal-guard,当天即可密封并开胶囊,取首个真实回面数据点(对位北极星验证)。
    坏值/未设 → (21, False) 正常窗口。注:seal_capsule 是 INSERT OR IGNORE,已封胶囊
    (如本仓 7-01 到期的 dogfood 数据)不会被短窗重定日期,只对新 risk 生效;短窗宜配
    窄 --since 用,避免历史回放 risk 即时密封成洪流。"""
    raw = os.environ.get("CODETALK_CAPSULE_DAYS")
    if raw is None:
        return 21, False
    try:
        return max(0, int(raw)), True
    except ValueError:
        return 21, False


def _seal_commit_capsules(cache, pkey, commit, sealed, opens):
    """只 seal 与 commit body 里 `Vibe-Watch:` 面包屑逐字一致的 risks。
    LLM 推断的 risks 不进胶囊——对账价值低,塞进会污染北极星处理率分母(回面收件箱噪声)。
    用户手写的 Vibe-Watch 才是真在意的预测,值得 21 天后回面验证。"""
    _decs, watches = parse_breadcrumbs(commit.get("body") or "")
    if not watches:
        return
    # narrative.risks 经 enrich 的 redact_secrets 往返(put_narrative 落库再脱敏),含 secret
    # 形 Watch 会读成 [REDACTED];watches 来自原始 body(未脱敏)。两侧同口径脱敏后再比,
    # 否则含密钥的手写 Watch exact-match 漏命中、永不封存。
    watches_norm = {redact_secrets(w) for w in watches}
    for idx, risk in enumerate(commit["narrative"].get("risks") or []):
        if redact_secrets(risk) in watches_norm:
            cache.seal_capsule(pkey, commit["sha"], idx, risk, sealed, opens)


def digest(args):
    from .commands import _cache_db_path, _fail  # 复用 commands 的轻量分发辅助
    started = time.time()
    cfg = load_config()
    if args.provider:
        cfg["provider"] = args.provider
    if args.model:
        cfg["model"] = args.model
    if args.vault:
        cfg["vault_path"] = args.vault
    if getattr(args, "no_llm", False):
        cfg["no_llm"] = True
    project_path = Path(args.project).resolve()
    project = project_path.name        # 显示标题 / 输出文件名
    pkey = str(project_path)            # cache 键:绝对路径,同名项目不串

    commits, git_err = gitlog.collect_commits(
        project_path, args.since, cfg["diff_token_budget"])
    if git_err:
        return _fail(git_err)
    if not commits:
        print(f"{args.since} 以来没有 commit,无日报可写。")
        return 0

    cache = Cache(_cache_db_path())
    cache.rekey_project(project, pkey)   # 迁移旧 basename 键数据(一次性,幂等)
    session_list, session_err = ([], None)
    srcs = _sources(cfg, args)
    if "claude" in srcs:
        session_list, session_err = sessions.scan_sessions(
            project_path, _since_to_dt(args.since), cache)
        if session_err:
            log.warning("会话层降级:%s", session_err)
    if "cursor" in srcs:
        cursor_sessions.maybe_notice()
        cur_list, cur_err = cursor_sessions.scan_sessions(
            project_path, _since_to_dt(args.since), cache)
        if cur_err:
            log.warning("Cursor 会话层降级:%s", cur_err)
        session_list = session_list + cur_list
    if "codex" in srcs:
        codex_sessions.maybe_notice()
        cx_list, cx_err = codex_sessions.scan_sessions(
            project_path, _since_to_dt(args.since), cache)
        if cx_err:
            log.warning("Codex 会话层降级:%s", cx_err)
        session_list = session_list + cx_list
    align.align(commits, session_list, project_path)

    try:
        llm = LLMClient(cfg)
    except LLMError as exc:
        return _fail(exc)
    # 回读上次运行后用户在 Obsidian 里勾选的胶囊答案,闭合预测-验证环
    report.read_capsule_answers(cfg["vault_path"], pkey, cache)
    # 运行前已缓存的 SHA:用于区分每天的缓存命中 vs 新算(按日页脚统计)
    pre_cached = {c["sha"] for c in commits if cache.get_narrative(c["sha"])}
    with_pr = bool(getattr(args, "with_pr", False)) or (
        "pr" in (cfg.get("sources") or []))
    if with_pr:
        _maybe_pr_notice()
    enrich.enrich_commits(commits, llm, cache, str(project_path), with_pr=with_pr)
    if cfg.get("backlinks"):                 # opt-in:产出 Obsidian 决策反链笔记(默认关)
        from . import obsidian
        n = obsidian.emit_decision_notes(commits, project, cfg["vault_path"], pkey)
        if n:
            log.info("Obsidian 反链:写出 %d 张决策笔记", n)

    # 按 commit 日期分桶,一天一份日报:bound 住报告长度与概览输入,
    # 并让历史各天都进 daily_digests 缓存(修复回补时 On This Day 查不到)。
    by_day = {}
    for commit in commits:
        by_day.setdefault(commit["date"].date(), []).append(commit)

    days = []  # 先按日生成概览/胶囊,等 LLM 统计齐了再统一渲染
    tok_in0, tok_out0 = 0, 0  # 按日 token 差分基线(运行前 enrich 增量并入首日)
    for day in sorted(by_day):
        day_commits = by_day[day]
        date_str = day.isoformat()
        overview, decision, calls = enrich.make_overview(
            day_commits, llm, cache, str(project_path), date_str)
        day_tok_in = llm.stats["input_tokens"] - tok_in0     # 本日 token=累计差分,非整轮和
        day_tok_out = llm.stats["output_tokens"] - tok_out0
        tok_in0, tok_out0 = llm.stats["input_tokens"], llm.stats["output_tokens"]
        cache.put_daily(pkey, date_str, overview, decision)
        cap_days, dogfood = _capsule_days()
        for commit in day_commits:  # 以该天为「今日」封存,忠实重放胶囊时间线
            sealed = commit["date"].date().isoformat()
            opens = (commit["date"].date() + timedelta(days=cap_days)).isoformat()
            if opens <= date_str and not dogfood:
                continue  # 该天视角下已到期的不补密封,不复活成洪流(dogfood 短窗显式放行)
            _seal_commit_capsules(cache, pkey, commit, sealed, opens)
        # 仅对真正的「今日」削峰(留次日);历史回放当天全开,天数不失真
        cap_limit = 3 if day == date.today() else None
        capsules = cache.open_due_capsules(pkey, date_str, cap_limit)
        on_this_day = {}
        for label, shifted in (("上月今日", _shift(day, months=1)),
                               ("去年今日", _shift(day, years=1))):
            past = cache.get_daily(pkey, shifted.isoformat())
            if past:
                on_this_day[label] = (shifted.isoformat(), past["overview"])
        hits = sum(1 for c in day_commits if c["sha"] in pre_cached)
        days.append({
            "date_str": date_str, "commits": day_commits, "overview": overview,
            "decision": decision, "capsules": capsules, "today": day,
            "on_this_day": on_this_day, "llm_calls": len(day_commits) - hits + calls,
            "cache_hits": hits, "tokens_in": day_tok_in, "tokens_out": day_tok_out,
        })

    opened, filled = cache.capsule_fill_stats(pkey)
    paths = []
    for d in days:
        run_stats = {
            "commits": len(d["commits"]), "sessions": len(session_list),
            "cache_hits": d["cache_hits"], "llm_calls": d["llm_calls"],
            "tokens_in": d["tokens_in"],
            "tokens_out": d["tokens_out"],
            "model": f"{cfg['provider']}/{cfg['model']}",
            "elapsed_s": round(time.time() - started, 1),
            "capsule_opened": opened, "capsule_filled": filled,
        }
        content = report.render(project, d["date_str"], d["overview"],
                                d["commits"], session_list, session_err,
                                run_stats, decision=d["decision"],
                                on_this_day=d["on_this_day"],
                                capsules=d["capsules"], today=d["today"],
                                project_path=project_path)
        path = report.write_report(cfg["vault_path"], project, d["date_str"],
                                   content)
        paths.append(path)
        report.append_usage({"command": "digest", "project": str(project_path),
                             "since": args.since, "report": str(path),
                             **run_stats})
    # 接地覆盖自检(零 LLM):digest 只富集 --since 窗口,收尾点出全史未叙事缺口
    all_commits, cov_err = gitlog.collect_commit_files(project_path)
    nudge = None
    if not cov_err and all_commits:
        narrated = sum(1 for c in all_commits if cache.get_narrative(c["sha"]))
        nudge = coverage_nudge(len(all_commits), narrated)
    cache.close()
    print(f"生成 {len(paths)} 份日报:")
    for p in paths:
        print(f"  {p}")
    if nudge:
        print(nudge)
    return 0
