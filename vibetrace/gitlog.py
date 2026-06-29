"""Collect commits (message + stat + truncated diff) via git subprocess."""
import json
import logging
import re
import subprocess
from datetime import datetime

log = logging.getLogger("vibetrace")

FIELD_SEP = "\x1f"
RECORD_SEP = "\x1e"
CHARS_PER_TOKEN = 4  # rough budget heuristic; exact counting needs no extra dep


def _git(args, cwd):
    # core.quotepath=false:让 git 对中文/重音文件名输出原始 UTF-8 而非 C 转义
    # ("\303\274ber.py"),恢复文件级交集;对已用 -z 的调用无副作用。
    out = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=cwd,
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip()[:200])
    return out.stdout


def collect_commits(project_path, since, diff_token_budget):
    """Return (commits oldest-first, error_message_or_None)."""
    fmt = FIELD_SEP.join(["%H", "%aI", "%an", "%s", "%b"]) + RECORD_SEP
    try:
        raw = _git(["log", "--no-merges", f"--since={since}",
                    f"--pretty=format:{fmt}"], project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log 失败:{exc}"

    commits = []
    for rec in raw.split(RECORD_SEP):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(FIELD_SEP)
        if len(parts) < 4:
            log.warning("跳过无法解析的 git log 记录")
            continue
        sha, date_iso, author, subject = parts[0], parts[1], parts[2], parts[3]
        body = parts[4].strip() if len(parts) > 4 else ""
        try:
            date = datetime.fromisoformat(date_iso)
        except ValueError:
            log.warning("commit %s 日期无法解析,已跳过", sha[:8])
            continue
        commits.append({
            "sha": sha, "author": author, "subject": subject, "body": body,
            "date": date, "stat": "", "diff_excerpt": "", "files": [],
        })

    char_budget = diff_token_budget * CHARS_PER_TOKEN
    for commit in commits:
        sha = commit["sha"]
        try:
            commit["files"] = [f for f in _git(
                ["show", "--name-only", "--pretty=format:", sha],
                project_path).splitlines() if f]
            commit["stat"] = _git(
                ["show", "--stat", "--pretty=format:", sha],
                project_path).strip()
            diff = _git(["show", "--patch", "--no-color", "-U10",
                         "--pretty=format:", sha], project_path)  # 加厚上下文,让叙事看懂改动所在函数
            if len(diff) > char_budget:
                diff = diff[:char_budget] + "\n... [diff 已截断]"
            commit["diff_excerpt"] = diff.strip()
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            log.warning("commit %s 详情获取失败:%s", sha[:8], exc)

    commits.reverse()  # git log is newest-first; report reads oldest-first
    return commits, None


def collect_commit_files(project_path, since="30 years ago"):
    """轻量:一次 git log --name-only 取 (sha, date, subject, body, files),不碰 diff/stat。
    供理解债量化、课程与面包屑收割——一次批量拿到主题、正文(面包屑源)、文件清单,
    替代调用方逐 commit 跑 git show(commit_body)。
    返回 (commits oldest-first, error_or_None);文件以 \\x00 分隔避免空格路径问题。
    %b 含换行,故按 \\x00 切出文件 token,首 token 用 rpartition 剥出第一个文件名。"""
    fmt = RECORD_SEP + FIELD_SEP.join(["%H", "%aI", "%s", "%b"])
    try:
        raw = _git(["log", "--no-merges", f"--since={since}", "--name-only",
                    "-z", f"--pretty=format:{fmt}"], project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log 失败:{exc}"
    commits = []
    for rec in raw.split(RECORD_SEP):
        if not rec.strip("\x00\n"):
            continue
        # rec = "H\x1fdate\x1fsubject\x1fbody\n\nfile1\x00file2\x00...";body 可含 \n,
        # 不含 \x00。按 \x00 切:首段含元数据+第一个文件名,余段是其余文件名。
        tokens = rec.split("\x00")
        meta_and_first = tokens[0]
        rest_files = [f for f in tokens[1:] if f.strip()]
        meta, _, first_file = meta_and_first.rpartition("\n")
        if not meta:                       # 无文件的 commit:整段都是元数据
            meta, first_file = meta_and_first, ""
        parts = meta.split(FIELD_SEP)
        if len(parts) < 3:
            continue
        if not _SHA_RE.match(parts[0]):    # 分隔符异变时静默错切的防御:首段须是 40 hex SHA
            log.warning("跳过疑似错切的 git log 记录(首段非 SHA)")
            continue
        try:
            date = datetime.fromisoformat(parts[1])
        except ValueError:
            continue
        body = parts[3].strip() if len(parts) > 3 else ""
        files = ([first_file] if first_file.strip() else []) + rest_files
        commits.append({"sha": parts[0], "date": date, "subject": parts[2],
                        "body": body, "files": files})
    commits.reverse()
    return commits, None


def commit_diff(project_path, sha, char_budget=2000):
    """单 commit 的截断 diff 片段(供课程『代码↔讲解』)。失败返回 ''。"""
    try:
        diff = _git(["show", "--patch", "--no-color", "--pretty=format:", sha],
                    project_path).strip()
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return ""
    return diff[:char_budget] + ("\n... [diff 已截断]" if len(diff) > char_budget else "")


def tracked_files(project_path):
    """当前工作树仍跟踪的文件集(git ls-files)。失败返回 None(调用方据此降级不过滤)。"""
    try:
        return {f for f in _git(["ls-files"], project_path).splitlines() if f}
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return None


def parse_breadcrumbs(body):
    """从 commit body 提取决策面包屑。区分大小写,行首匹配 Vibe-Decision:/Vibe-Watch:。
    返回 (decisions, watches);body 为空/None 安全返回 ([], [])。"""
    decisions, watches = [], []
    for line in (body or "").splitlines():
        line = line.strip()
        if line.startswith("Vibe-Decision:"):
            text = line[len("Vibe-Decision:"):].strip()
            if text:
                decisions.append(text)
        elif line.startswith("Vibe-Watch:"):
            text = line[len("Vibe-Watch:"):].strip()
            if text:
                watches.append(text)
    return decisions, watches


def parse_rejected(body):
    """从 commit body 提取 Vibe-Rejected 面包屑(被否决的备选)。区分大小写,行首匹配。
    被否决方案是 diff 结构性取不到的 why-NOT(README 护城河),提成一等公民供 blame 独立标注。
    body 为空/None 安全返回 []。"""
    rejected = []
    for line in (body or "").splitlines():
        line = line.strip()
        if line.startswith("Vibe-Rejected:"):
            text = line[len("Vibe-Rejected:"):].strip()
            if text:
                rejected.append(text)
    return rejected


def merge_breadcrumbs(narrative, project_path, sha):
    """命中 SHA 的缓存叙事 ∪ commit body 面包屑(去重,叙事在前、面包屑在后)。
    返回 (decisions, risks, rejected);供 ask/blame/search 共用,缓存已折入的面包屑不重复。"""
    body = commit_body(project_path, sha)
    decisions, watches = parse_breadcrumbs(body)
    decs = list(dict.fromkeys((narrative.get("decisions") or []) + decisions))
    risks = list(dict.fromkeys((narrative.get("risks") or []) + watches))
    rejected = list(dict.fromkeys((narrative.get("rejected") or []) + parse_rejected(body)))
    return decs, risks, rejected


_RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_target(target):
    """'foo.py' → ('foo.py', None, None);'foo.py:42-60' → ('foo.py', 42, 60);
    'foo.py:42' → ('foo.py', 42, 42)。冒号右侧不是行号则整串当文件(路径含冒号罕见)。"""
    if ":" in target:
        file, _, tail = target.rpartition(":")
        match = _RANGE_RE.match(tail)
        if file and match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else start
            return file, start, end
    return target, None, None


LINE_LOG_LIMIT = 50
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def line_log(project_path, file, start, end, extra=None):
    """命中 file 第 start..end 行演化的 commit SHA(旧→新,最多 LINE_LOG_LIMIT 条)。
    git log -L<a>,<b>:<file> -s --format=%H;只保留 40 位 hex 行,稳健剔除可能漏出的
    diff 文本(不依赖各 git 版本对 -s + -L 的具体行为)。失败→由调用方降级到文件级。
    extra:时间范围 token(--since=... 或 rev range),须排在 -L 之前(git -L 对顺序敏感)。"""
    try:
        raw = _git(["log", "-s", "--format=%H", *(extra or []),
                    f"-L{start},{end}:{file}"], project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log -L 失败:{exc}"
    shas = [s.strip() for s in raw.splitlines() if _SHA_RE.match(s.strip())]
    shas.reverse()  # git log 新→旧,翻成旧→新
    return shas[-LINE_LOG_LIMIT:], None


def file_log(project_path, file, extra=None):
    """文件级降级:命中该文件的 commit SHA(旧→新,最多 LINE_LOG_LIMIT 条)。
    extra:时间范围 token(--since=... 或 rev range),须排在 -- pathspec 之前。"""
    try:
        raw = _git(["log", "--format=%H", *(extra or []), "--", file],
                   project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log 失败:{exc}"
    shas = [s.strip() for s in raw.splitlines() if _SHA_RE.match(s.strip())]
    shas.reverse()
    return shas[-LINE_LOG_LIMIT:], None


def prior_commit(project_path, sha, files):
    """最近一个在 sha 之前、改过 files 里任一文件的 commit(40 hex);无/失败返回 ''。
    供叙事跨时间接地:让 LLM 知道这些文件上次改动做了什么。"""
    if not files:
        return ""
    try:
        raw = _git(["log", f"{sha}~1", "-1", "--format=%H", "--", *files],
                   project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return ""
    out = raw.strip().splitlines()
    return out[0] if out and _SHA_RE.match(out[0]) else ""


def commit_body(project_path, sha):
    """单 commit 的 message body(供面包屑收割)。失败返回 ''。"""
    try:
        return _git(["show", "-s", "--format=%b", sha], project_path).strip()
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return ""


def pr_discussion(project_path, sha):
    """该 commit 关联的第一个 PR(标题+描述,作 why 接地源;opt-in,数据出本机)。
    gh api repos/{owner}/{repo}/commits/<sha>/pulls(gh 自动解析当前仓 owner/repo)。
    容错铁律:gh 不存在/非零退出/超时/空列表/JSON 解析失败 → 一律返回 None,绝不抛。
    返回 {number, url(取 html_url), title, body}。"""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/commits/{sha}/pulls"],
            cwd=project_path, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    try:
        prs = json.loads(out.stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(prs, list) or not prs:
        return None
    pr = prs[0]
    if not isinstance(pr, dict):
        return None
    return {"number": pr.get("number"), "url": pr.get("html_url", ""),
            "title": pr.get("title", ""), "body": pr.get("body") or ""}


def commit_meta(project_path, sha):
    """单 commit 的 (作者日期 ISO, subject)(供 blame 确定性罗列)。失败返回 ('', '')。"""
    try:
        raw = _git(["show", "-s", f"--format=%aI{FIELD_SEP}%s", sha],
                   project_path).strip()
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return "", ""
    date_iso, _, subject = raw.partition(FIELD_SEP)
    return date_iso, subject
