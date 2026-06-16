"""开工简报(Boot Brief):开工前把『你上次停在哪』端到面前。
纯本地缓存读,不调 LLM、不出网——补『日常化』最大短板。"""


def build_brief(cache, project, project_full):
    """组装开工简报 markdown。project=项目名(daily/capsules 键),
    project_full=项目绝对路径(commit_narratives 键)。"""
    lines = [f"# {project} 开工简报", ""]

    last = cache.latest_daily(project)
    lines += ["## 你上次停在哪", ""]
    if last:
        lines.append(f"_{last['date']}_:{last['overview']}")
        if last["decision"]:
            lines += ["", f"> 上次的决定 — {last['decision']}"]
    else:
        lines.append("(还没有任何日报——先跑一次 `vibetrace digest`。)")
    lines.append("")

    pending = cache.pending_capsules(project)
    if pending:
        lines += ["## 待验证的预测", ""]
        for cap in pending:
            lines.append(f"- (`{cap['sha'][:7]}`)你曾担心:「{cap['risk']}」"
                         "——现在验证了吗?")
        lines.append("")

    loops = cache.recent_open_loops(project_full)
    if loops:
        lines += ["## 悬而未决", ""]
        lines += ["- " + l for l in loops]
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
