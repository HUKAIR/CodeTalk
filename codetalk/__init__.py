"""codetalk — local-first code decision provenance (zero-LLM grounding)."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("codetalk")
except PackageNotFoundError:        # 源码树未安装时回退,不崩
    __version__ = "0.3.0"
