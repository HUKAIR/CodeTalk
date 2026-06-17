# 单代码 AI 提问(`ask`)+ 决策面包屑 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 vibetrace 加 `vibetrace ask <文件>[:起-止] "问题"`——接项目记忆(已缓存叙事 + commit 决策面包屑)对一段代码作接地回答,区别于"对 logfile 做一次 LLM 调用"。

**Architecture:** write-time 捕获(commit message 里的 `Vibe-Decision:`/`Vibe-Watch:` trailer,由协作 agent 自动留)+ read-time 廉价检索(`git log -L` 命中 commit → 取已缓存叙事 + 收割面包屑 → 一次轻 LLM 综合)。贵活只在 commit 那次按 SHA 算一遍永久缓存;`ask` 只取现成的。`Vibe-Watch` 收割进 `risks`,复用现有 risks→`seal_capsule` 预测-验证环。

**Tech Stack:** Python 3.11+,仅标准库 + anthropic SDK(M0 红线);测试用 stdlib `unittest`(零新依赖);git 子进程;SQLite 缓存。源于已批准 spec `docs/superpowers/specs/2026-06-17-single-code-ai-question-design.md`。

**执行约定:**
- 测试:仓库根目录跑 `python3 -m unittest discover -s tests -v`;单模块 `python3 -m unittest tests.test_xxx -v`。
- 每次 `git commit` 末尾附 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
- 在本计划自身的实质性 commit 上**吃自己的狗粮**:带 `Vibe-Decision:` trailer 记录关键取舍。
- M0:每模块改后 `wc -l` 必须 <300(Task 11 统一校验)。

---

## 文件结构

| 文件 | 职责 | 改动 |
|---|---|---|
| `vibetrace/gitlog.py` | git 取数 | 新增 `parse_breadcrumbs`、`line_log`、`file_log`、`commit_body` |
| `vibetrace/enrich.py` | commit 富集 | 收割面包屑并入 narrative(decision→decisions,watch→**risks**),合并在现有脱敏之前 |
| `vibetrace/llm.py` | LLM 封装 | `narrate` 加可选 `system`;新增 `ASK_SCHEMA`、`ASK_SYSTEM_PROMPT` |
| `vibetrace/cache.py` | SQLite 缓存 | `recent_open_loops` 的 WHERE 排除 `ask:%`/`course:%` |
| `vibetrace/ask.py` | **新建**:检索 + 综合 | `_parse_target`/`_retrieve`/`answer_question`/`ask` |
| `vibetrace/cli.py` | CLI | 新增 `ask` 子命令 |
| `CLAUDE.md` / `AGENTS.md` | 约定 | 面包屑书写约定 |
| `tests/` | **新建**:unittest | 每个 bug-prone 单元一份测试 |

---

## Task 1: gitlog.parse_breadcrumbs(纯函数,面包屑解析)

**Files:**
- Create: `tests/__init__.py`(空文件)
- Create: `tests/test_breadcrumbs.py`
- Modify: `vibetrace/gitlog.py`

- [ ] **Step 1: 建 tests 包占位**

```bash
mkdir -p tests && : > tests/__init__.py
```

- [ ] **Step 2: 写失败测试**

`tests/test_breadcrumbs.py`:
```python
import unittest

from vibetrace.gitlog import parse_breadcrumbs


class TestParseBreadcrumbs(unittest.TestCase):
    def test_extracts_decision_and_watch(self):
        body = ("修复缓存键\n\n"
                "Vibe-Decision: 用 urllib 不引第三方\n"
                "Vibe-Watch: 先这么扛,并发安全待验证\n"
                "Co-Authored-By: x")
        decisions, watches = parse_breadcrumbs(body)
        self.assertEqual(decisions, ["用 urllib 不引第三方"])
        self.assertEqual(watches, ["先这么扛,并发安全待验证"])

    def test_empty_and_none_safe(self):
        self.assertEqual(parse_breadcrumbs(""), ([], []))
        self.assertEqual(parse_breadcrumbs(None), ([], []))

    def test_ignores_lowercase_midline_and_blank_value(self):
        body = ("vibe-decision: 小写不算\n"
                "随便 Vibe-Decision: 行中不算\n"
                "Vibe-Decision:   ")
        self.assertEqual(parse_breadcrumbs(body), ([], []))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 跑测试确认失败**

Run: `python3 -m unittest tests.test_breadcrumbs -v`
Expected: FAIL / ERROR — `ImportError: cannot import name 'parse_breadcrumbs'`

- [ ] **Step 4: 实现 parse_breadcrumbs**

在 `vibetrace/gitlog.py` 末尾追加:
```python
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
```

- [ ] **Step 5: 跑测试确认通过**

Run: `python3 -m unittest tests.test_breadcrumbs -v`
Expected: PASS(3 tests OK)

- [ ] **Step 6: 提交**

```bash
git add tests/__init__.py tests/test_breadcrumbs.py vibetrace/gitlog.py
git commit -m "feat(gitlog): parse_breadcrumbs 解析 Vibe-Decision/Vibe-Watch trailer"
```

---

## Task 2: gitlog.line_log / file_log / commit_body(git 行历史)

**Files:**
- Create: `tests/test_gitlog_history.py`
- Modify: `vibetrace/gitlog.py`(顶部 `import re`;新增三个函数)

- [ ] **Step 1: 写失败测试(自建临时 git 仓库,无网络)**

`tests/test_gitlog_history.py`:
```python
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from vibetrace.gitlog import line_log, file_log, commit_body


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


class TestGitlogHistory(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        _git(["init", "-q"], self.dir)
        _git(["config", "user.email", "t@t"], self.dir)
        _git(["config", "user.name", "t"], self.dir)
        f = Path(self.dir) / "f.py"
        f.write_text("a\nb\nc\n")
        _git(["add", "f.py"], self.dir)
        _git(["commit", "-q", "-m", "c1 初版\n\nVibe-Decision: 初版决定"], self.dir)
        f.write_text("a\nB2\nc\n")  # 改第 2 行
        _git(["add", "f.py"], self.dir)
        _git(["commit", "-q", "-m", "c2 改第二行"], self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_line_log_returns_only_shas_oldest_first(self):
        shas, err = line_log(self.dir, "f.py", 2, 2)
        self.assertIsNone(err)
        self.assertEqual(len(shas), 2)            # 两次 commit 都动过第 2 行
        for s in shas:
            self.assertRegex(s, r"^[0-9a-f]{40}$")  # 确保没混入 diff 文本行
        self.assertIn("初版决定", commit_body(self.dir, shas[0]))  # 旧→新

    def test_file_log_fallback(self):
        shas, err = file_log(self.dir, "f.py")
        self.assertIsNone(err)
        self.assertEqual(len(shas), 2)

    def test_bad_path_degrades_with_error_not_crash(self):
        shas, err = line_log(self.dir, "nope.py", 1, 1)
        self.assertTrue(err)
        self.assertEqual(shas, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_gitlog_history -v`
Expected: FAIL — `ImportError: cannot import name 'line_log'`

- [ ] **Step 3: 实现三个函数**

`vibetrace/gitlog.py` 顶部已 `import subprocess`;在 import 区补 `import re`。文件末尾追加:
```python
LINE_LOG_LIMIT = 12
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def line_log(project_path, file, start, end):
    """命中 file 第 start..end 行演化的 commit SHA(旧→新,最多 LINE_LOG_LIMIT 条)。
    git log -L<a>,<b>:<file> -s --format=%H;只保留 40 位 hex 行,稳健剔除可能漏出的
    diff 文本(不依赖各 git 版本对 -s + -L 的具体行为)。失败→由调用方降级到文件级。"""
    try:
        raw = _git(["log", "-s", "--format=%H",
                    f"-L{start},{end}:{file}"], project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log -L 失败:{exc}"
    shas = [s.strip() for s in raw.splitlines() if _SHA_RE.match(s.strip())]
    shas.reverse()  # git log 新→旧,翻成旧→新
    return shas[-LINE_LOG_LIMIT:], None


def file_log(project_path, file):
    """文件级降级:命中该文件的 commit SHA(旧→新,最多 LINE_LOG_LIMIT 条)。"""
    try:
        raw = _git(["log", "--format=%H", "--", file], project_path)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        return [], f"git log 失败:{exc}"
    shas = [s.strip() for s in raw.splitlines() if _SHA_RE.match(s.strip())]
    shas.reverse()
    return shas[-LINE_LOG_LIMIT:], None


def commit_body(project_path, sha):
    """单 commit 的 message body(供面包屑收割)。失败返回 ''。"""
    try:
        return _git(["show", "-s", "--format=%b", sha], project_path).strip()
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        return ""
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_gitlog_history -v`
Expected: PASS(3 tests OK)。

> 注:本任务以真实临时仓库验证了 spec『风险与开放问题』里 `git log -L` + `-s` 的行为——hex 行过滤使结果不依赖该行为,该开放问题就此关闭。

- [ ] **Step 5: 提交**

```bash
git add tests/test_gitlog_history.py vibetrace/gitlog.py
git commit -m "feat(gitlog): line_log/file_log/commit_body 取行历史与 body"
```

---

## Task 3: enrich 收割面包屑(decision→decisions,watch→risks,脱敏前合并)

**Files:**
- Create: `tests/test_enrich_breadcrumbs.py`
- Modify: `vibetrace/enrich.py`(顶部加 import;改 `enrich_commits` 成功分支 73-78 行附近)

- [ ] **Step 1: 写失败测试(FakeLLM,无网络;真内存 Cache)**

`tests/test_enrich_breadcrumbs.py`:
```python
import unittest
from datetime import datetime, timezone

from vibetrace import enrich
from vibetrace.cache import Cache


class _FakeLLM:
    model = "fake"

    def narrate(self, prompt, *args, **kwargs):
        return {"what": "w", "why": "y", "decisions": ["LLM 决定"],
                "risks": ["LLM 风险"], "open_loops": ["LLM 未闭环"]}


def _commit(body):
    return {"sha": "abc123", "author": "x", "subject": "s", "body": body,
            "date": datetime(2026, 6, 17, tzinfo=timezone.utc),
            "stat": "", "diff_excerpt": "", "files": [], "matches": []}


class TestEnrichBreadcrumbs(unittest.TestCase):
    def test_watch_into_risks_decision_into_decisions_and_redacted(self):
        cache = Cache(":memory:")
        body = ("Vibe-Decision: 用 urllib\n"
                "Vibe-Watch: 临时 token=sk-abcdefghijklmnop1234 待移除")
        enrich.enrich_commits([_commit(body)], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertIn("用 urllib", narr["decisions"])      # 收割决策
        self.assertIn("LLM 决定", narr["decisions"])        # 原 LLM 决策保留
        watch_risks = [r for r in narr["risks"] if "临时" in r]
        self.assertTrue(watch_risks)                        # cons-1: watch 进 risks
        self.assertNotIn("sk-abcdefghijklmnop1234", watch_risks[0])  # priv-1
        self.assertIn("[REDACTED]", watch_risks[0])
        self.assertEqual(narr["open_loops"], ["LLM 未闭环"])  # watch 不进 open_loops

    def test_no_breadcrumb_keeps_llm_narrative(self):
        cache = Cache(":memory:")
        enrich.enrich_commits([_commit("普通 message")], _FakeLLM(), cache, "P")
        narr = cache.get_narrative("abc123")
        self.assertEqual(narr["decisions"], ["LLM 决定"])
        self.assertEqual(narr["risks"], ["LLM 风险"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_enrich_breadcrumbs -v`
Expected: FAIL — watch 未进 risks(`watch_risks` 为空)/ secret 未脱敏。

- [ ] **Step 3: 实现合并**

`vibetrace/enrich.py` 顶部 import 区加:
```python
from .gitlog import parse_breadcrumbs
```

把 `enrich_commits` 成功分支(当前 73-74 行)的:
```python
            raw = llm.narrate(redact_secrets(_commit_prompt(commit)))
            narrative = json.loads(redact_secrets(
                json.dumps(_normalize(raw), ensure_ascii=False)))
```
改为(合并放在那次 `redact_secrets` **之前**,单次脱敏覆盖面包屑文本):
```python
            raw = llm.narrate(redact_secrets(_commit_prompt(commit)))
            normalized = _normalize(raw)
            decisions, watches = parse_breadcrumbs(commit.get("body", ""))
            if decisions:  # 人原话并入决策,去重,保留 LLM 既有决策
                normalized["decisions"] = list(dict.fromkeys(
                    normalized["decisions"] + decisions))
            if watches:    # Vibe-Watch 进 risks → 复用现有 risks→seal_capsule 环
                normalized["risks"] = normalized["risks"] + watches
            narrative = json.loads(redact_secrets(
                json.dumps(normalized, ensure_ascii=False)))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_enrich_breadcrumbs -v`
Expected: PASS(2 tests OK)。

- [ ] **Step 5: 提交(吃狗粮:带 Vibe-Watch trailer 验收环路)**

```bash
git add tests/test_enrich_breadcrumbs.py vibetrace/enrich.py
git commit -m "feat(enrich): 收割面包屑 decision→decisions / watch→risks(脱敏前合并)

Vibe-Decision: watch 进 risks 而非 open_loops——全仓唯一封胶囊入口只遍历 risks
Vibe-Watch: 合并放在 redact_secrets 之前靠单次脱敏覆盖,待真实含 key 的 commit 验证"
```

---

## Task 4: cache.recent_open_loops 排除 ask:/course: 行(防污染简报)

**Files:**
- Create: `tests/test_cache_filter.py`
- Modify: `vibetrace/cache.py:169-172`(`recent_open_loops` 的 SQL)

- [ ] **Step 1: 写失败测试**

`tests/test_cache_filter.py`:
```python
import unittest

from vibetrace.cache import Cache


class TestRecentOpenLoopsFilter(unittest.TestCase):
    def test_excludes_ask_course_digest_rows(self):
        c = Cache(":memory:")
        c.put_narrative("realsha", "P", "m", {"open_loops": ["真未闭环"]})
        c.put_narrative("digest:x", "P", "m", {"open_loops": ["不该出现-digest"]})
        c.put_narrative("course:v2:y", "P", "m", {"open_loops": ["不该出现-course"]})
        c.put_narrative("ask:z", "P", "m",
                        {"answer": "a", "open_loops": ["不该出现-ask"]})
        self.assertEqual(c.recent_open_loops("P"), ["真未闭环"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_cache_filter -v`
Expected: FAIL — 结果含 "不该出现-course"/"不该出现-ask"(当前只排除 `digest:%`)。

- [ ] **Step 3: 改 SQL**

`vibetrace/cache.py` 把 `recent_open_loops` 里(169-172 行)的查询:
```python
        rows = self.conn.execute(
            "SELECT narrative_json FROM commit_narratives WHERE project=? "
            "AND sha NOT LIKE 'digest:%' "
            "ORDER BY created_at DESC LIMIT ?", (project, limit)).fetchall()
```
改为:
```python
        rows = self.conn.execute(
            "SELECT narrative_json FROM commit_narratives WHERE project=? "
            "AND sha NOT LIKE 'digest:%' AND sha NOT LIKE 'ask:%' "
            "AND sha NOT LIKE 'course:%' "
            "ORDER BY created_at DESC LIMIT ?", (project, limit)).fetchall()
```
并把该方法 docstring 末句的"排除 digest: 概览行"改为"排除 digest:/ask:/course: 派生行"。

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_cache_filter -v`
Expected: PASS(1 test OK)。

- [ ] **Step 5: 提交**

```bash
git add tests/test_cache_filter.py vibetrace/cache.py
git commit -m "fix(cache): recent_open_loops 排除 ask:/course: 派生行防污染简报『悬而未决』"
```

---

## Task 5: llm 加可选 system + ASK_SCHEMA / ASK_SYSTEM_PROMPT

**Files:**
- Create: `tests/test_llm_ask.py`
- Modify: `vibetrace/llm.py`(新增常量;`narrate`/`_openai_compat`/`_anthropic` 加 `system` 参)

- [ ] **Step 1: 写失败测试(mock urlopen,无网络)**

`tests/test_llm_ask.py`:
```python
import json
import unittest
from unittest import mock

from vibetrace.llm import LLMClient, ASK_SCHEMA, ASK_SYSTEM_PROMPT


def _cfg():
    return {"provider": "deepseek", "model": "m",
            "providers": {"deepseek": {"base_url": "http://x/v1",
                                       "api_key": "k"}}}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


class TestAskSystem(unittest.TestCase):
    def test_ask_schema_required_fields(self):
        self.assertEqual(ASK_SCHEMA["required"], ["answer", "cited_shas"])

    def test_system_param_threaded_into_request(self):
        captured = {}
        payload = {"choices": [{"message": {"content":
                   json.dumps({"answer": "a", "cited_shas": []})}}],
                   "usage": {}}

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _FakeResp(payload)

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = LLMClient(_cfg()).narrate("Q", schema=ASK_SCHEMA,
                                            system=ASK_SYSTEM_PROMPT)
        self.assertEqual(out["answer"], "a")
        sys_msg = captured["body"]["messages"][0]["content"]
        self.assertIn("单代码问答引擎", sys_msg)  # 用了 ASK 而非默认 SYSTEM_PROMPT


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_llm_ask -v`
Expected: FAIL — `ImportError: cannot import name 'ASK_SCHEMA'`

- [ ] **Step 3: 实现**

`vibetrace/llm.py` 在 `NARRATIVE_SCHEMA` 定义之后新增:
```python
ASK_SYSTEM_PROMPT = (
    "你是 vibetrace 的单代码问答引擎。基于给定材料(这段代码相关 commit 的叙事 + 决策"
    "面包屑,旧→新),用中文回答开发者关于这段代码的问题。\n"
    "事实纪律(最高优先级):\n"
    "- 只用给定材料作答;材料不足以回答就直说『材料不足』,不补全、不编造\n"
    "- 禁止编造材料中不存在的文件名/SHA/数字/专有名词\n"
    "- 在 cited_shas 里列出你实际据以回答的 commit 短 SHA\n"
    "- 没把握的部分写进 unsure,不要混进 answer 充数\n"
    "输出必须是符合给定 JSON Schema 的单个 JSON 对象,不要输出任何其他文字。"
)

ASK_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "对问题的回答,只据材料"},
        "cited_shas": {"type": "array", "items": {"type": "string"},
                       "description": "实际据以回答的 commit 短 SHA"},
        "unsure": {"type": "string", "description": "没把握/材料不足之处,可空"},
    },
    "required": ["answer", "cited_shas"],
    "additionalProperties": False,
}
```

把 `narrate` 签名与转发改为带 `system`:
```python
    def narrate(self, user_prompt, schema=NARRATIVE_SCHEMA,
                max_tokens=MAX_OUTPUT_TOKENS, system=None):
        """One structured-JSON completion. Raises LLMError on final failure.
        system=None 时用默认 SYSTEM_PROMPT(叙事纪律);ask 传 ASK_SYSTEM_PROMPT。
        max_tokens 须覆盖『推理 + 输出』,推理模型按需调大。"""
        if self.provider == "anthropic":
            return self._anthropic(user_prompt, schema, max_tokens, system)
        return self._openai_compat(user_prompt, schema, max_tokens, system)
```

`_openai_compat` 签名与首行:
```python
    def _openai_compat(self, user_prompt, schema, max_tokens, system=None):
        system = ((system or SYSTEM_PROMPT) + "\n\nJSON Schema:\n"
                  + json.dumps(schema, ensure_ascii=False))
```

`_anthropic` 签名与 system 块:
```python
    def _anthropic(self, user_prompt, schema, max_tokens, system=None):
```
并把其 `client.messages.create(...)` 里的 system 文本由 `SYSTEM_PROMPT` 改为 `system or SYSTEM_PROMPT`:
```python
                system=[{"type": "text", "text": system or SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_llm_ask -v`
Expected: PASS(2 tests OK)。

- [ ] **Step 5: 全量回归(确认默认 narrate 行为未变)**

Run: `python3 -m unittest discover -s tests -v`
Expected: 所有已写测试 PASS(默认 `system=None` 路径与旧行为一致)。

- [ ] **Step 6: 提交**

```bash
git add tests/test_llm_ask.py vibetrace/llm.py
git commit -m "feat(llm): narrate 加可选 system + ASK_SCHEMA/ASK_SYSTEM_PROMPT(接地问答)"
```

---

## Task 6: ask._parse_target(纯函数,解析提问对象)

**Files:**
- Create: `vibetrace/ask.py`(本任务先放最小骨架 + `_parse_target`)
- Create: `tests/test_ask_parse.py`

- [ ] **Step 1: 写失败测试**

`tests/test_ask_parse.py`:
```python
import unittest

from vibetrace.ask import _parse_target


class TestParseTarget(unittest.TestCase):
    def test_plain_file(self):
        self.assertEqual(_parse_target("a/b.py"), ("a/b.py", None, None))

    def test_range(self):
        self.assertEqual(_parse_target("a/b.py:42-60"), ("a/b.py", 42, 60))

    def test_single_line(self):
        self.assertEqual(_parse_target("b.py:7"), ("b.py", 7, 7))

    def test_colon_but_not_range_is_file(self):
        self.assertEqual(_parse_target("weird:name"), ("weird:name", None, None))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_ask_parse -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'vibetrace.ask'`

- [ ] **Step 3: 建 ask.py 骨架 + _parse_target**

`vibetrace/ask.py`:
```python
"""单代码 AI 提问:接项目记忆对一段代码作接地回答。

write-time 捕获(commit trailer 面包屑)+ read-time 廉价检索(git log -L → 已缓存
叙事 + 面包屑 → 一次轻 LLM)。无 key/失败时降级为打印该代码的原始决策史,绝不崩。
"""
import hashlib
import re
import sys
from pathlib import Path

from .cache import Cache
from .config import CACHE_DB_PATH, load_config, redact_secrets
from .gitlog import line_log, file_log, commit_body, parse_breadcrumbs
from .llm import ASK_SCHEMA, ASK_SYSTEM_PROMPT, LLMClient, LLMError

EXCERPT = 200
CONTEXT_BUDGET = 6000
_RANGE_RE = re.compile(r"^(\d+)(?:-(\d+))?$")


def _parse_target(target):
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_ask_parse -v`
Expected: PASS(4 tests OK)。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/ask.py tests/test_ask_parse.py
git commit -m "feat(ask): 新建 ask.py 骨架 + _parse_target 解析文件/行范围"
```

---

## Task 7: ask._retrieve(检索器:命中 commit → 叙事 + 面包屑 → 上下文)

**Files:**
- Modify: `vibetrace/ask.py`(追加 `_retrieve`)
- Create: `tests/test_ask_retrieve.py`

- [ ] **Step 1: 写失败测试(monkeypatch git 调用,真内存 Cache)**

`tests/test_ask_retrieve.py`:
```python
import unittest
from unittest import mock

from vibetrace import ask
from vibetrace.cache import Cache


class TestRetrieve(unittest.TestCase):
    def test_assembles_cached_narrative_and_breadcrumbs(self):
        cache = Cache(":memory:")
        cache.put_narrative("sha1aaaabbbb", "P", "m",
                            {"why": "因为要省依赖", "decisions": ["LLM决定"],
                             "risks": [], "open_loops": []})
        with mock.patch.object(ask, "line_log",
                               lambda *a: (["sha1aaaabbbb"], None)), \
             mock.patch.object(ask, "commit_body",
                               lambda p, s: "Vibe-Watch: 并发待验证"):
            ctx, shas, state = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertIn("sha1aaa", ctx)        # 短 sha
        self.assertIn("因为要省依赖", ctx)     # 缓存叙事 why
        self.assertIn("LLM决定", ctx)         # 缓存决策
        self.assertIn("并发待验证", ctx)       # 面包屑 watch
        self.assertEqual(state, "sha1aaaabbbb")

    def test_line_log_failure_falls_back_to_file_log(self):
        cache = Cache(":memory:")
        called = {}

        def fake_file_log(*a):
            called["hit"] = True
            return ([], None)

        with mock.patch.object(ask, "line_log", lambda *a: ([], "boom")), \
             mock.patch.object(ask, "file_log", fake_file_log), \
             mock.patch.object(ask, "commit_body", lambda p, s: ""):
            ctx, shas, state = ask._retrieve(".", "f.py", 1, 5, cache)
        self.assertTrue(called.get("hit"))
        self.assertEqual(ctx, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_ask_retrieve -v`
Expected: FAIL — `AttributeError: module 'vibetrace.ask' has no attribute '_retrieve'`

- [ ] **Step 3: 实现 _retrieve**

`vibetrace/ask.py` 追加:
```python
def _retrieve(project_path, file, start, end, cache):
    """→ (context_str, shas oldest-first, code_state)。无历史时 context_str 为 ''。
    code_state = 命中行最新 commit SHA,进缓存键 → 代码一变旧答案自然失效。"""
    if start is not None:
        shas, err = line_log(project_path, file, start, end)
        if err:                       # 行级失败 → 文件级降级
            shas, _ = file_log(project_path, file)
    else:
        shas, _ = file_log(project_path, file)
    blocks = []
    for sha in shas:
        narrative = cache.get_narrative(sha) or {}
        decisions, watches = parse_breadcrumbs(commit_body(project_path, sha))
        decs = (narrative.get("decisions") or []) + decisions
        risks = (narrative.get("risks") or []) + watches
        parts = [f"[{sha[:7]}]"]
        if narrative.get("why"):
            parts.append("意图:" + narrative["why"][:EXCERPT])
        if decs:
            parts.append("决策:" + ";".join(decs)[:EXCERPT])
        if risks:
            parts.append("风险/待验证:" + ";".join(risks)[:EXCERPT])
        blocks.append(" / ".join(parts))
    context = "\n".join(blocks)[:CONTEXT_BUDGET]
    code_state = shas[-1] if shas else ""
    return context, shas, code_state
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_ask_retrieve -v`
Expected: PASS(2 tests OK)。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/ask.py tests/test_ask_retrieve.py
git commit -m "feat(ask): _retrieve 拼 commit 叙事+面包屑成有界上下文(行级失败降级文件级)"
```

---

## Task 8: ask.answer_question + ask(综合、缓存、降级、写笔记)

**Files:**
- Modify: `vibetrace/ask.py`(追加 `_ask_prompt`/`_format`/`_write_note`/`answer_question`/`ask`)
- Create: `tests/test_ask_answer.py`

- [ ] **Step 1: 写失败测试(monkeypatch _retrieve + FakeLLM,真内存 Cache)**

`tests/test_ask_answer.py`:
```python
import unittest
from unittest import mock

from vibetrace import ask
from vibetrace.cache import Cache


class _FakeLLM:
    model = "fake"

    def __init__(self):
        self.calls = 0

    def narrate(self, prompt, *a, **k):
        self.calls += 1
        return {"answer": "因为是推理模型,3000 不够",
                "cited_shas": ["sha1aaa"], "unsure": ""}


def _patch_retrieve(ctx="[sha1aaa] 决策:用 urllib", state="sha1aaaabbbb"):
    return mock.patch.object(ask, "_retrieve",
                             lambda *a: (ctx, ["sha1aaaabbbb"], state))


class TestAnswerQuestion(unittest.TestCase):
    def test_answers_caches_and_second_call_hits_cache(self):
        cache, llm = Cache(":memory:"), _FakeLLM()
        with _patch_retrieve():
            t1, e1 = ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "为什么")
            t2, e2 = ask.answer_question(cache, llm, ".", "P", "f.py:1-2", "为什么")
        self.assertIsNone(e1)
        self.assertIsNone(e2)
        self.assertIn("推理模型", t1)
        self.assertIn("sha1aaa", t1)        # cited_shas 露出
        self.assertEqual(llm.calls, 1)      # 第二次命中缓存,不再调 LLM

    def test_no_llm_degrades_to_raw_history(self):
        cache = Cache(":memory:")
        with _patch_retrieve():
            text, err = ask.answer_question(cache, None, ".", "P", "f.py:1-2", "Q")
        self.assertIsNone(err)
        self.assertIn("用 urllib", text)     # 原始决策史
        self.assertIn("原始决策史", text)

    def test_no_history_returns_error(self):
        cache = Cache(":memory:")
        with mock.patch.object(ask, "_retrieve", lambda *a: ("", [], "")):
            text, err = ask.answer_question(cache, _FakeLLM(), ".", "P", "x.py", "Q")
        self.assertIsNone(text)
        self.assertTrue(err)

    def test_answer_redacted_before_cache(self):
        cache = Cache(":memory:")

        class _LeakLLM:
            model = "m"

            def narrate(self, *a, **k):
                return {"answer": "key 是 sk-abcdefghijklmnop1234",
                        "cited_shas": []}

        with _patch_retrieve():
            text, err = ask.answer_question(cache, _LeakLLM(), ".", "P",
                                            "f.py:1-2", "Q")
        self.assertNotIn("sk-abcdefghijklmnop1234", text)
        self.assertIn("[REDACTED]", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_ask_answer -v`
Expected: FAIL — `AttributeError: ... has no attribute 'answer_question'`

- [ ] **Step 3: 实现**

`vibetrace/ask.py` 追加:
```python
def _ask_prompt(context, question):
    return ("材料(这段代码相关 commit 的叙事与决策面包屑,旧→新):\n"
            f"{context}\n\n问题:{question}\n"
            "只据材料回答;材料不足就说『材料不足』。")


def _format(payload):
    cited = "、".join(payload.get("cited_shas") or []) or "(无)"
    out = payload.get("answer", "")
    if payload.get("unsure"):
        out += f"\n\n[不确定] {payload['unsure']}"
    return f"{out}\n\n据此回答的 commit:{cited}"


def _write_note(vault_path, project, target, question, payload):
    vault = Path(vault_path).expanduser()
    vault.mkdir(parents=True, exist_ok=True)
    slug = hashlib.sha256(f"{target}|{question}".encode()).hexdigest()[:8]
    note = f"# 提问:{target}\n\n> {question}\n\n{_format(payload)}\n"
    (vault / f"{project}-ask-{slug}.md").write_text(
        redact_secrets(note), encoding="utf-8")


def answer_question(cache, llm, project_path, project, target, question,
                    vault_path=None):
    """核心:解析→检索→(命中缓存/无 key 降级/调 LLM)→脱敏缓存→(可选)写笔记。
    返回 (text, error_or_None)。llm=None 表示无 key,降级打印原始决策史。"""
    file, start, end = _parse_target(target)
    context, shas, code_state = _retrieve(project_path, file, start, end, cache)
    if not context:
        return None, f"{file} 没有可用的提交历史,无从回答。"
    key = "ask:" + hashlib.sha256(
        f"{file}|{start}-{end}|{question}|{code_state}".encode()
    ).hexdigest()[:40]
    cached = cache.get_narrative(key)
    if cached:
        return _format(cached), None
    if llm is None:                       # 无 API key:降级到原始决策史
        return "(未配置 LLM,以下为这段代码的原始决策史)\n" + context, None
    try:
        raw = llm.narrate(_ask_prompt(context, question),
                          schema=ASK_SCHEMA, system=ASK_SYSTEM_PROMPT)
    except LLMError:
        return "(LLM 调用失败,以下为原始决策史)\n" + context, None
    payload = {
        "answer": redact_secrets(str(raw.get("answer", ""))),
        "cited_shas": [str(s) for s in (raw.get("cited_shas") or [])],
        "unsure": redact_secrets(str(raw.get("unsure", ""))),
    }
    cache.put_narrative(key, project, llm.model, payload)
    if vault_path:
        _write_note(vault_path, project, target, question, payload)
    return _format(payload), None


def ask(project_path, target, question, vault=None):
    """CLI 入口:装配 cache/llm,转 answer_question,打印,返回退出码。"""
    cfg = load_config()
    if vault:
        cfg["vault_path"] = vault
    pp = Path(project_path).resolve()
    cache = Cache(CACHE_DB_PATH)
    try:
        llm = LLMClient(cfg)
    except LLMError:
        llm = None                        # 无 key → 降级,不报错退出
    text, err = answer_question(cache, llm, pp, pp.name, target, question,
                                cfg["vault_path"] if vault else None)
    cache.close()
    if err:
        print(f"错误:{err}", file=sys.stderr)
        return 2
    print(text)
    return 0
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_ask_answer -v`
Expected: PASS(4 tests OK)。

- [ ] **Step 5: 提交**

```bash
git add vibetrace/ask.py tests/test_ask_answer.py
git commit -m "feat(ask): answer_question+ask 综合/缓存/无key降级/脱敏写笔记"
```

---

## Task 9: cli ask 子命令

**Files:**
- Modify: `vibetrace/cli.py`(`main` 加 subparser + 分派分支)
- Create: `tests/test_cli_ask.py`

- [ ] **Step 1: 写失败测试(monkeypatch ask.ask)**

`tests/test_cli_ask.py`:
```python
import unittest
from unittest import mock

from vibetrace import ask, cli


class TestCliAsk(unittest.TestCase):
    def test_ask_subcommand_dispatches_args(self):
        got = {}

        def fake_ask(project_path, target, question, vault=None):
            got.update(p=project_path, t=target, q=question, v=vault)
            return 0

        with mock.patch.object(ask, "ask", fake_ask):
            rc = cli.main(["ask", "f.py:1-2", "为什么", "--project", ".",
                           "--vault", "/tmp/v"])
        self.assertEqual(rc, 0)
        self.assertEqual(got, {"p": ".", "t": "f.py:1-2", "q": "为什么",
                               "v": "/tmp/v"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python3 -m unittest tests.test_cli_ask -v`
Expected: FAIL — argparse 报错 "invalid choice: 'ask'"(SystemExit)。

- [ ] **Step 3: 加 subparser + 分派**

`vibetrace/cli.py` 的 `main` 里,在 `crs = sub.add_parser("course", ...)` 那段之后、`args = parser.parse_args(argv)` 之前加:
```python
    asq = sub.add_parser("ask", help="就某段代码提问(接项目记忆,接地回答)")
    asq.add_argument("--project", default=".", help="项目路径(默认当前目录)")
    asq.add_argument("target", help='文件或 文件:起-止,如 vibetrace/llm.py:72-78')
    asq.add_argument("question", help="你的问题")
    asq.add_argument("--vault", help="同时写一份脱敏 Q&A 笔记到该目录")
```
并在 `if args.command == "brief": return brief_cmd(args)` 之后、`return digest(args)` 之前加:
```python
    if args.command == "ask":
        from .ask import ask
        return ask(args.project, args.target, args.question, vault=args.vault)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python3 -m unittest tests.test_cli_ask -v`
Expected: PASS(1 test OK)。

- [ ] **Step 5: 确认 help 可用**

Run: `python3 -m vibetrace ask --help`
Expected: 打印 ask 子命令用法,含 `target`、`question`、`--project`、`--vault`。

- [ ] **Step 6: 提交**

```bash
git add vibetrace/cli.py tests/test_cli_ask.py
git commit -m "feat(cli): 新增 ask 子命令分派到 ask.ask"
```

---

## Task 10: 面包屑约定写进 CLAUDE.md / AGENTS.md

**Files:**
- Modify: `CLAUDE.md`(Project-Specific Guidelines 末尾)
- Modify: `AGENTS.md`(对应位置,保持镜像)

- [ ] **Step 1: 在 CLAUDE.md 的 `## Project-Specific Guidelines` 列表末尾追加一条**

```markdown
- 决策面包屑:做关键技术取舍时,在 commit message 正文留 `Vibe-Decision: <一句话决策,
  可含被否决备选>`;没把握、需日后验证的留 `Vibe-Watch: <一句话>`。vibetrace digest 会把
  Decision 并进该 commit 决策、Watch 并进 risks(到期封成可验证胶囊),`vibetrace ask` 据此
  接地回答"这段代码当初为什么这么写"。行首精确匹配、区分大小写。
```

- [ ] **Step 2: 在 AGENTS.md 同步同一条**(AGENTS.md 是 CLAUDE.md 的跨工具镜像,保持一致)

- [ ] **Step 3: 提交(吃狗粮)**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: 约定 Vibe-Decision/Vibe-Watch 决策面包屑(供 ask 与胶囊)

Vibe-Decision: 面包屑走 commit trailer 而非内联注释——git 原生、不污染代码、agent 易自动留"
```

---

## Task 11: 验收(spec 6 条 + 全量回归 + 行数校验)

**Files:** 无代码改动;运行验证并记录结果。

- [ ] **Step 1: 全量单测回归**

Run: `python3 -m unittest discover -s tests -v`
Expected: 全部 PASS(test_breadcrumbs / gitlog_history / enrich_breadcrumbs / cache_filter / llm_ask / ask_parse / ask_retrieve / ask_answer / cli_ask)。

- [ ] **Step 2: 行数校验(M0 <300)**

Run: `wc -l vibetrace/*.py`
Expected: 每个文件 < 300(尤其 ask.py / gitlog.py / enrich.py / llm.py / cli.py / cache.py)。

- [ ] **Step 3: 验收 #1 — 接地回答 + 引用真实 SHA**(需 ~/.vibetrace/config.json 里 deepseek key)

先确保本仓历史已被 digest 过(叙事入缓存),否则只靠面包屑/subject:
Run: `python3 -m vibetrace digest --since "60 days ago" --project .`(已跑过可跳过)
Run: `python3 -m vibetrace ask "vibetrace/llm.py:72-78" "为什么 narrate 要带 max_tokens" --project .`
Expected: 回答命中"推理模型(deepseek-v4-pro)先花 reasoning token、默认 3000 不够"这条理由;末尾"据此回答的 commit"列出确实改过这几行的短 SHA。

- [ ] **Step 4: 验收 #2 — 反幻觉**

Run: `python3 -m vibetrace ask "README.md:99999" "这行为什么这么写" --project .`
Expected: 回答"材料不足"或返回"没有可用的提交历史"错误;**不编造** commit/文件名。

- [ ] **Step 5: 验收 #3 — 无 key 降级**(已由 `tests.test_ask_answer.test_no_llm_degrades_to_raw_history` 覆盖)

确认该单测通过即可;无需真的清空 key。

- [ ] **Step 6: 验收 #4 — Vibe-Watch 封胶囊**

造一个带 watch 的真实 commit(本分支,吃狗粮),再 digest,查 capsules:
```bash
F=vibetrace/__init__.py
printf '\n# touch for capsule acceptance\n' >> "$F"
git add "$F"
git commit -m "test: 验收 Vibe-Watch 封胶囊

Vibe-Watch: 这是验收用的待验证点,应在 digest 后封成胶囊"
python3 -m vibetrace digest --since "1 day ago" --project .
SHA=$(git rev-parse HEAD)
sqlite3 ~/.vibetrace/cache.db "SELECT capsule_id, risk FROM capsules WHERE sha='$SHA';"
```
Expected: 查到一行胶囊,`risk` 文本即"这是验收用的待验证点…"。
随后回滚这次验收 commit 与文件改动,保持分支干净:
```bash
git reset --hard HEAD~1
```
（若无 `sqlite3` CLI,改用:`python3 -c "import sqlite3,os;c=sqlite3.connect(os.path.expanduser('~/.vibetrace/cache.db'));print(c.execute(\"SELECT capsule_id,risk FROM capsules WHERE sha=?\",('$SHA',)).fetchall())"`)

- [ ] **Step 7: 验收 #5 — ask 不污染简报**(已由 `tests.test_cache_filter` 覆盖)

可补一次真实观察:`python3 -m vibetrace ask "vibetrace/cli.py:1-5" "这文件干嘛的" --project .` 后
Run: `python3 -m vibetrace brief --project .`
Expected: 『悬而未决』段仍是真 open_loops,无 ask 答案串入。

- [ ] **Step 8: 记录验收结果并提交**(若 Step 6 已 reset,本步仅在有遗留改动时需要)

把 #1/#2 的实际输出摘要追加到本计划文件末尾"验收记录"小节,然后:
```bash
git add docs/superpowers/plans/2026-06-17-single-code-ai-question.md
git commit -m "docs: 记录单代码提问功能验收结果"
```

---

## 验收记录
（执行 Task 11 时填:#1 引用的 SHA 与命中理由、#2 的拒答文本、#4 的胶囊 id。)
