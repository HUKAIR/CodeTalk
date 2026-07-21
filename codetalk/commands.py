"""codetalk 核心子命令——digest/brief/watch/self/enrich/init。
视图/输出类命令在 commands_view.py;drift/adr 各自独立模块。"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import brief, report
from .cache import Cache
from .config import USAGE_LOG_PATH, load_config
from .digest import digest  # noqa: F401 — cli._DISPATCH 经 commands.digest 分发

log = logging.getLogger("codetalk")


def _cache_db_path():
    from . import cli
    return cli.CACHE_DB_PATH


def _fail(msg):
    print(f"错误:{msg}", file=sys.stderr)
    return 2


def _scan_sessions(cfg, args, pp, cache):
    """按 config.sources/--source 扫 claude/cursor/codex 会话(增量缓存)→ session 列表;降级不崩。"""
    from . import codex_sessions, cursor_sessions, sessions
    from .digest import _since_to_dt, _sources
    since_dt = _since_to_dt(args.since)
    srcs = _sources(cfg, args)
    sess = []
    for name, mod in (("claude", sessions), ("cursor", cursor_sessions),
                      ("codex", codex_sessions)):
        if name not in srcs:
            continue
        if name != "claude":
            mod.maybe_notice()
        lst, err = mod.scan_sessions(pp, since_dt, cache)
        if err:
            log.warning("%s 会话层降级:%s", name, err)
        sess += lst
    return sess


def brief_cmd(args):
    cfg = load_config()
    if args.vault:
        cfg["vault_path"] = args.vault
    cache = Cache(_cache_db_path())
    if args.all:
        today = datetime.now(timezone.utc).astimezone().date()
        projects = cache.distinct_projects()
        content = brief.build_overview(cache, projects, today)
        cache.close()
        report.append_usage({"command": "brief", "mode": "all",
                             "projects": len(projects)})
        print(content)
        if args.vault:
            path = report.write_report(cfg["vault_path"], "overview",
                                       "brief", content)
            print(f"总览已写入:{path}")
        return 0
    project_path = Path(args.project).resolve()
    project = project_path.name
    pkey = str(project_path)
    cache.rekey_project(project, pkey)
    report.read_capsule_answers(cfg["vault_path"], pkey, cache)
    content = brief.build_brief(cache, project, pkey)
    cache.close()
    report.append_usage({"command": "brief", "mode": "single", "project": pkey})
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], project, "brief", content)
        print(f"简报已写入:{path}")
    return 0


def watch_cmd(args):
    """跨项目 watch 收件箱:列出所有项目里已到期未回填的胶囊(零 LLM,不出网)。"""
    cfg = load_config()
    if args.vault:                       # 与 brief_cmd 一致:--vault 重定向写入目标
        cfg["vault_path"] = args.vault
    cache = Cache(_cache_db_path())
    today = datetime.now(timezone.utc).astimezone().date()
    content = brief.build_watch(cache, cache.distinct_projects(), today)
    cache.close()
    print(content)
    if args.vault:
        path = report.write_report(cfg["vault_path"], "watch", "watch", content)
        print(f"收件箱已写入:{path}")
    return 0


def self_cmd(args):
    """自我周报(零 LLM):解析 usage.log 聚合近 N 天用量,回填率取自全项目胶囊统计。"""
    from . import self_report
    cache = Cache(_cache_db_path())
    fill = self_report.aggregate_fill(cache)
    cache.close()
    print(self_report.build_self_report(USAGE_LOG_PATH, args.days, fill))
    return 0


def init_cmd(args):
    """写配置模板到 ~/.codetalk/config.json(chmod 600),引导填 key。"""
    from .config import CONFIG_PATH, DEFAULTS
    if CONFIG_PATH.exists() and not args.force:
        print(f"配置已存在:{CONFIG_PATH}(加 --force 覆盖)")
        return 0
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(DEFAULTS, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)
    except OSError:
        pass
    print(f"已写入配置模板:{CONFIG_PATH}")
    print(f"请填 providers.{DEFAULTS['provider']}.api_key,"
          f"或设环境变量 {DEFAULTS['provider'].upper()}_API_KEY")
    return 0


def enrich_cmd(args):
    """富集补全(coverage):扫会话对齐 → 零-LLM 给已叙事补 evidence 原话锚点 → LLM 补未叙事。"""
    from . import align, enrich, enrich_plan, gitlog
    from .digest import _sources
    from .llm import LLMClient, LLMError
    cfg = load_config()
    if getattr(args, "no_llm", False):
        cfg["no_llm"] = True
    pp = Path(args.project).resolve()
    commits, err = gitlog.collect_commits(pp, args.since, cfg["diff_token_budget"])
    if err:
        return _fail(err)
    cache = Cache(_cache_db_path())
    cache.rekey_project(pp.name, str(pp))
    sources = sorted(_sources(cfg, args))
    align.align(commits, _scan_sessions(cfg, args, pp, cache), pp)
    ev = enrich.backfill_evidence(commits, cache, str(pp))
    reenrich = getattr(args, "reenrich", False)
    if reenrich:
        log.warning("--reenrich: 重 enrich 全部 %d 个 commit,违反 SHA 缓存 immutability "
                    "(opt-in,用于 prompt 规则升级)", len(commits))
        missing = commits
    else:
        missing = [c for c in commits if not cache.get_narrative(c["sha"])]
    plan = enrich_plan.build_plan(
        cfg, commits, missing, str(pp), sources, ev, reenrich=reenrich,
        allow_remote=getattr(args, "allow_remote", False),
        payload_preview=getattr(args, "payload_preview", False))
    preview = None
    if getattr(args, "payload_preview", False) and missing:
        preview = enrich_plan.outbound_request_preview(
            cfg, missing[0], cache, str(pp))
    print(enrich_plan.render_plan(plan, preview))
    if not plan["model_request"]:
        cache.close()
        print(f"补 evidence {ev} 条;模型请求未发送;待叙事 {len(missing)} 个 commit。")
        return 0
    if plan.get("endpoint_error"):
        cache.close()
        return _fail("模型端点配置无效:" + plan["endpoint_error"])
    try:
        llm = LLMClient(cfg)
    except LLMError as exc:
        cache.close()
        if ev:
            print(f"补 evidence {ev} 条;未叙事 {len(missing)} 个需 LLM(已关/无 key)跳过。")
            return 0
        return _fail(exc)
    stats = enrich.enrich_commits(missing, llm, cache, str(pp), force=reenrich)
    cache.close()
    print(f"补 evidence {ev} 条;补全 {len(missing)}/{len(commits)} 无叙事 commit:"
          f"LLM {stats['llm_calls']} · 机械 {stats['trivial']} · 失败 {stats['failures']}。")
    return 0
