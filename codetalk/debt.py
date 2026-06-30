"""Understanding debt: per-module lapse between AI churn and your review.

Pure local arithmetic, zero LLM, no network — self-proves the cross-time
moat (a single model call can't reproduce accumulated review behaviour).

    debt(m) = churn(m) × decay(m) × (1 − understand(m))
      churn      Σ(decisions + 1) over commits touching m   # AI 替你做的决定越多,欠越多
      understand (reviewed commits + filled capsules) / (commits + capsules)
      decay      1 + days_since(last review, else last touch) / 30

SHA 统一短 7 位:隧道注入即短 sha,reviewed 表也存短 sha。
"""
from datetime import datetime, timezone

from .gitlog import collect_commit_files, tracked_files

DECAY_DAYS = 30


def _short(sha):
    return sha[:7]


def _to_date(iso):
    try:
        return datetime.fromisoformat(
            iso.replace("Z", "+00:00")).astimezone().date()
    except (ValueError, AttributeError, TypeError):
        return datetime.now(timezone.utc).astimezone().date()


def debt_board(project_path, cache, today, top=None):
    """每个文件的理解债,高→低。容错:无 commit/无叙事/无信号均不崩,返回 []。
    cache 键统一用 str(project_path)(绝对路径),与 commit_narratives 一致、同名项目不串。"""
    commits, err = collect_commit_files(project_path)  # 轻量:只取 sha/date/files
    if err or not commits:
        return []
    pkey = str(project_path)
    reviewed = cache.reviewed_shas(pkey)                # {short_sha: iso_ts}
    caps_by_sha = {}
    for cap in cache.all_capsules(pkey):
        caps_by_sha.setdefault(_short(cap["sha"]), []).append(cap)
    tracked = tracked_files(project_path)  # None=git 失败 → 容错降级:不过滤

    mods = {}  # file -> churn / 相关 commit / 最近改动 / 最近决定
    for commit in commits:
        sha = _short(commit["sha"])
        decisions = (cache.get_narrative(commit["sha"]) or {}).get("decisions") or []
        for f in commit["files"]:
            # 已删除/未跟踪文件不计入:无法回看、无债可还,否则会挤占 top 名额
            if tracked is not None and f not in tracked:
                continue
            m = mods.setdefault(f, {"churn": 0, "shas": set(), "last_touch": None,
                                    "last_decision": None, "dec_by_sha": {}})
            m["churn"] += len(decisions) + 1
            m["shas"].add(sha)
            if decisions:   # 下钻:记每个决策 commit 的 sha→{subject,decisions}(供未回看清单)
                m["dec_by_sha"][sha] = {"subject": commit.get("subject", ""),
                                        "decisions": decisions}
            if m["last_touch"] is None or commit["date"] > m["last_touch"]:
                m["last_touch"] = commit["date"]
                m["last_decision"] = decisions[0] if decisions else None

    rows = []
    for f, m in mods.items():
        shas = m["shas"]
        rel_caps = [c for s in shas for c in caps_by_sha.get(s, [])]
        reviewed_n = len(shas & set(reviewed))
        filled = sum(1 for c in rel_caps if c["outcome"])
        denom = len(shas) + len(rel_caps)
        understand = (reviewed_n + filled) / denom if denom else 0
        rev_dates = [_to_date(reviewed[s]) for s in shas if s in reviewed]
        ref = max(rev_dates) if rev_dates else m["last_touch"].astimezone().date()
        decay = 1 + max(0, (today - ref).days) / DECAY_DAYS
        rows.append({
            "file": f, "debt": round(m["churn"] * decay * (1 - understand), 1),
            "churn": m["churn"], "reviewed": reviewed_n, "commits": len(shas),
            "caps_filled": filled, "caps_total": len(rel_caps),
            "last_decision": m["last_decision"],
            # 下钻真实构成(零-LLM 重派生):未回看的决策 commit + 到期待填胶囊
            "unreviewed": [{"sha": s, "subject": v["subject"], "decisions": v["decisions"]}
                           for s, v in m["dec_by_sha"].items() if s not in reviewed],
            "pending_caps": [{"capsule_id": c["capsule_id"], "risk": c["risk"]}
                             for c in rel_caps if c.get("opened") and not c["outcome"]],
        })
    rows.sort(key=lambda r: r["debt"], reverse=True)
    return rows[:top] if top else rows
