"""构建 codetalk.mcpb(MCP Bundle):zip(manifest.json + server/<纯 stdlib 源>)。

codetalk 零三方依赖(pyproject dependencies=[]),故无需打包解释器/编译依赖——
manifest 声明 `python3 -m codetalk mcp-serve`,靠用户已装的 python3 运行,PYTHONPATH
指向 bundle 内 server/。一次构建,Claude Code / Cursor / Codex 等所有 MCP 客户端一键装。
纯 stdlib(zipfile/json),自身也不引依赖。
"""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_SKIP_DIRS = {"__pycache__"}
_SKIP_SUFFIX = {".pyc", ".pyo"}


def build(out_path, root=ROOT):
    """打包成 .mcpb,返回产物 Path。校验 manifest 为合法 JSON(失败即抛,不静默)。"""
    root = Path(root)
    manifest = root / "manifest.json"
    json.loads(manifest.read_text(encoding="utf-8"))   # fail loud on bad manifest
    pkg = root / "codetalk"
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(manifest, "manifest.json")
        license_file = root / "LICENSE"
        if license_file.exists():
            z.write(license_file, "LICENSE")
        for p in sorted(pkg.rglob("*")):
            if not p.is_file() or p.suffix in _SKIP_SUFFIX:
                continue
            if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            z.write(p, str(Path("server") / p.relative_to(root)))  # server/codetalk/...
    return out_path


if __name__ == "__main__":
    out = build(ROOT / "codetalk.mcpb")
    print(f"built {out} ({out.stat().st_size} bytes)")
