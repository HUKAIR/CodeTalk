"""Build a UI gallery from synthetic data without reading project/user records."""
import argparse
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template

from codetalk.filetree import build_tree
from codetalk.ui_template import read_template
from codetalk.recap_render import _build_detail, _build_index
from codetalk.review_web import render_review_html
from codetalk.webserve import inline_json

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "cache-lab · 合成演示"


def review_card():
    return {
        "id": "synthetic-review", "kind": "potential_conflict",
        "change": {"file": "cache.py", "start": 1, "end": 2,
                   "diff": "@@ -1,2 +1,2 @@\n def invalidate(cache, key):\n"
                           "-    cache.pop(key, None)\n+    cache.clear()"},
        "association": {"reason": "当前改动关联到此文件的历史；语义是否适用需要人工判断。",
                        "semantic_match": "not_evaluated"},
        "provenance": {"precision": "line", "label": "行级溯源 · 人工决策记录"},
        "evidence": {"primary": {
            "sha": "1" * 40, "date": "2026-11-01", "subject": "保留按 key 失效",
            "decision_notes": {"chosen": ["只失效变更 key。"],
                               "rejected": ["清空整个缓存会丢弃无关条目。"]},
            "sessions": [], "tests": [], "pull_requests": []}, "supporting": []},
        "interpretation": None, "judgment": {"status": "unresolved"},
    }


def build_pages(output):
    output = Path(output)
    pages = output / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    entries = []

    def template(name, **values):
        values.setdefault("project_key", "synthetic-gallery")
        return Template(read_template(name)).substitute(**values)

    def save(key, title, body, family, theme=None):
        # The fixed theme belongs only to the gallery, never the user's preference.
        if theme:
            body = body.replace('</body>', '<script>document.documentElement.'
                                'setAttribute("data-theme",' + json.dumps(theme)
                                + ');</script></body>')
        (pages / (key + ".html")).write_text(body, encoding="utf-8")
        entries.append({"id": key, "title": title, "family": family})

    subjects = ["按 key 缓存检索结果", "把证据与生成解释分开", "增加缓存失效回归测试",
                "为审查卡添加原始来源", "记录人工判断结果", "核对全量缓存清空"]
    reasons = ["避免无关条目被清空，让重复查询复用已验证结果。",
               "生成解释不能代替原始记录，必须能够回读来源。",
               "将曾被否决的方案变成可检验约束。",
               "先看发生了什么，再看当时为什么。",
               "确认冲突与改变行动分别记录。", "本次改动触及旧决定，由维护者核对。"]
    timeline = [dict(sha=f"{i+1:07x}", date=f"2026-11-{i//2+1:02d} 10:30",
                     day=f"2026-11-{i//2+1:02d}", days_ago=3-i//2,
                     subject=title, what=title, why=reasons[i], decisions=[reasons[i]],
                     risks=["空缓存场景仍需验证"] if i % 2 == 0 else [], capsules=[])
                for i, title in enumerate(subjects)][::-1]
    graph = {"nodes": [dict(id=f"{i+1:07x}", date=f"2026-11-{i//2+1:02d}",
                            subject=title, text=reasons[i] if i % 2 == 0 else "",
                            kind="breadcrumb" if i % 2 == 0 else "change", badge="", ts=i)
                       for i, title in enumerate(subjects)],
             "edges": [{"from": f"{a:07x}", "to": f"{b:07x}"}
                       for a, b in [(1, 2), (1, 3), (1, 6), (3, 4), (3, 5)]]}
    debt = [dict(file=f, debt=n, churn=n//2, reviewed=1, commits=5, caps_total=1,
                 caps_filled=0, last_decision="保留按 key 失效", unreviewed=[], pending_caps=[])
            for f, n in [("cache.py", 8), ("review.py", 5), ("tests/test_cache.py", 3)]]
    tree = build_tree(["cache.py", "review.py", "README.md", "tests/test_cache.py"],
                      {"cache.py": {"code": " M", "label": "已修改"}})
    turns = [dict(ask=q, concl=a, kind="question", files=["cache.py"],
                  tools=[["read_file", 2]]) for q, a in [
        ("为什么不能直接清空整个缓存？", "记录明确否决了全量清空：会丢弃无关条目。"),
        ("这次修改会重走旧路吗？", "当前 diff 使用 cache.clear()，需要核对此前拒绝理由。"),
        ("先把这个选择留下来。", "保留按 key 失效，并增加回归测试。")]]
    data = {"overview": {"last": {"overview": "缓存失效的边界已经明确，接下来核对审查流程。",
                                  "decision": "只失效变更 key，保留无关结果。"},
                         "debt_top": debt, "pending": [{"sha": "0000005",
                             "capsule_id": "synthetic-watch", "risk": "空缓存时能否解释缺少证据？"}],
                         "coverage": [4, 6], "last_digest": "2026-11-04", "today": "2026-11-04"},
            "timeline": timeline, "graph": graph, "debt": debt,
            "tree": {"nodes": tree, "grounding": []},
            "prompts_md": "# 本次工作的约束\n\n- 保留证据与解释的区别。\n- 缓存按 key 失效。",
            "recap": {"session_id": "synthetic-session", "turns": turns}}
    common = {"project": PROJECT, "generated": "2026.11.04"}
    console = template("console.html", **common, data=inline_json(data), serve="false", chat="false")
    for theme, label in [("dark", "深色"), ("light", "浅色")]:
        save("console-" + theme, "控制台 · " + label, console, "工作台", theme)
    empty = dict(data, overview={"last": None, "pending": [], "debt_top": []},
                 timeline=[], graph={"nodes": [], "edges": []}, debt=[], recap={})
    save("console-empty", "控制台 · 无记录", template("console.html", **common,
         data=inline_json(empty), serve="false", chat="false"), "状态", "dark")
    save("review", "决策审查", render_review_html(PROJECT, [review_card()], {}), "审查")
    save("review-empty", "审查 · 无证据", render_review_html(PROJECT, [], {}), "状态")
    long_card = review_card()
    long_card["change"]["file"] = "很长的路径/" * 20 + "cache.py"
    long_card["interpretation"] = {"summary": reasons[0] * 80}
    save("review-long", "审查 · 长内容", render_review_html(PROJECT, [long_card], {}), "状态")
    for state, label, key in [("pending", "保存中", "saving"),
                              ("success", "保存成功", "saved"),
                              ("error", "保存失败", "failed")]:
        body = render_review_html(PROJECT, [review_card()], {})
        script = ('document.querySelector(\'input[value="unrelated"]\').checked=true;'
                  'var previewStatus=document.querySelector(".saved");'
                  f'previewStatus.dataset.state="{state}";previewStatus.textContent=t("{key}");')
        if state == "pending":
            script += ('document.querySelectorAll("form input,form button").forEach('
                       'function(el){el.disabled=true});')
        body = body.replace('</body>', '<script>' + script + '</script></body>')
        save("review-" + state, "审查 · " + label + "（合成状态）", body, "状态")
    chat = template("web_chat.html", tree_data=inline_json({"nodes": tree, "status": []}))
    save("chat-empty", "对话 · 尚未提问", chat, "状态")
    for state, label, text in [("pending", "检索中", "合成状态：正在检索来源…"),
                               ("error", "请求失败", "合成状态：请求失败，请检查本机服务后重试。"),
                               ("long", "长回答", reasons[0] * 100)]:
        code = 'add("CodeTalk","bot").textContent=' + inline_json(text) + ';'
        save("chat-" + state, "对话 · " + label,
             chat.replace('</body>', '<script>' + code + '</script></body>'), "状态")
    chat = chat.replace('</body>', '<script>add("你","user").textContent="为什么只按 key 失效？";'
                        'var answer=add("CodeTalk","bot");answer.textContent="合成示例：原始记录否决了清空无关条目。";'
                        'renderDone(answer,{degraded:true,citations:[{id:0,sha:"111111111111",kind:"commit",'
                        'evidence:"Vibe-Rejected: 清空整个缓存会丢弃无关条目。",sources:[]}]},answer.textContent);'
                        '</script></body>')
    save("chat", "接地对话", chat, "工作台")
    save("timeline", "时光轴", template("tunnel.html", **common,
                                        data=inline_json(timeline), serve="false"), "历史")
    save("graph", "决策图", template("graph.html", **common, data=inline_json(graph)), "历史")
    chapters = [{"title": "从缓存边界开始", "intro": reasons[0],
                 "plain": "像只换一本书的标签，无需清空整个书架。",
                 "blocks": [{"type": "feat", "sha": "0000001", "subject": subjects[0],
                             "diff": "- cache.clear()\n+ cache.pop(key, None)", "what": reasons[0]}],
                 "risks": ["失效 key 缺失时应安全返回"], "open_loops": [],
                 "quiz": [{"q": "哪个行为会重引入曾被否决的选择？",
                           "options": ["按 key 失效", "清空整个缓存", "记录测试结果"],
                           "answer": 1, "hint": "全量清空会影响不相关条目。"}]}]
    save("course", "演进课程", template("course.html", **common,
                                        data=inline_json({"chapters": chapters, "degraded": False})), "历史")
    start = datetime(2026, 11, 4, 10, tzinfo=timezone(timedelta(hours=8)))
    session = {"turns": [dict(t, ts=start + timedelta(minutes=i*8), files={"cache.py": "cache.py"},
                              tools=Counter({"read_file": 2}), full=t["concl"])
                          for i, t in enumerate(turns)], "tools_total": Counter({"read_file": 6}),
               "start": start, "end": start + timedelta(minutes=24)}
    for theme, label in [("dark", "深色"), ("light", "浅色")]:
        save("recap-" + theme, "会话摘要 · " + label,
             _build_detail(Path("synthetic-session.jsonl"), session, PROJECT, index_href="sessions.html"), "会话", theme)
    meta = [dict(sid=f"synthetic-{i}", start=start - timedelta(days=i), end=start,
                 turns=3, size=24000, previews=[turns[0]["ask"]]) for i in range(15)]
    save("sessions", "会话索引", _build_index(PROJECT, meta, lambda m: "recap-dark.html"), "会话", "dark")
    ab = {"items": [dict(sha="0000001", date="2026-11-01", subject=subjects[0],
                         a="可能是出于性能优化。", b="示例记录：只失效变更 key，避免清空无关条目。", real="b")]}
    save("trust", "A/B 辨别 · 合成示例", template("trust_ab.html", project=PROJECT,
                                                data=inline_json(ab)), "演示")
    save("landing", "README 体验页", (ROOT / "index.html").read_text(), "演示")
    image_dir = pages / "docs" / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "docs/images/codetalk-logo-banner.png", image_dir / "codetalk-logo-banner.png")
    gallery = (ROOT / "scripts/demo_ui.html").read_text().replace("/* ITEMS */[]", inline_json(entries))
    (output / "index.html").write_text(gallery, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-serve", action="store_true")
    args = parser.parse_args()
    output = args.output or Path(tempfile.mkdtemp(prefix="codetalk-ui-demo-"))
    entries = build_pages(output)
    print(f"{len(entries)} synthetic previews retained at {output}", flush=True)
    if args.no_serve:
        return
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(output)))
    print(f"UI gallery: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
