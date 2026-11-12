"""Defensive unified-diff parsing for decision review cards."""
import re

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_unified_diff_hunks(text):
    """Return post-image ranges plus the exact bounded hunk text."""
    hunks = []
    current_file = None
    current = None

    def finish():
        if current is not None:
            current["diff"] = "\n".join(current.pop("lines"))
            hunks.append(current)

    for line in (text or "").splitlines():
        if line.startswith("diff --git "):
            finish()
            current = None
            current_file = None
        elif line.startswith("+++ "):
            path = line[4:].strip()
            current_file = None if path == "/dev/null" else re.sub(r"^b/", "", path)
        elif line.startswith("@@") and current_file:
            finish()
            match = _HUNK.match(line)
            if not match:
                current = None
                continue
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) else 1
            current = (None if count <= 0 else {
                "file": current_file, "start": start, "end": start + count - 1,
                "lines": [line],
            })
        elif current is not None:
            current["lines"].append(line)
    finish()
    return hunks
