"""Inline packaged UI assets before data substitution; exports remain standalone."""
import re
from pathlib import Path

_ROOT = Path(__file__).parent
_INCLUDE = re.compile(r"/\* include:([a-z0-9_-]+\.(?:css|js|html)) \*/")


def read_template(name):
    path = _ROOT / name
    page = path.read_text(encoding="utf-8")
    return _INCLUDE.sub(
        lambda match: (path.parent / match[1]).read_text(encoding="utf-8"), page)
