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
