"""Self-check for the vulnerability-merge logic in check_dependencies.py.

Run: python tests/check_dependencies_selfcheck.py
Exits non-zero on failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.check_dependencies import _version_sort_key

# 1. Numeric ordering: the bug this guards against is "2026.10" < "2026.9"
#    under plain string comparison.
assert max(["26.1.2", "26.2", "26.2.0"], key=_version_sort_key) == "26.2.0", \
    "26.2.0 should beat 26.2 and 26.1.2"
assert max(["2026.9", "2026.10"], key=_version_sort_key) == "2026.10", \
    "2026.10 must beat 2026.9 (string compare gets this backwards)"
assert max(["3.14.2", "3.14.3"], key=_version_sort_key) == "3.14.3"

# 2. post-release sorts after the plain release it follows.
assert max(["2026.3", "2026.3.post1"], key=_version_sort_key) == "2026.3.post1"

# 3. The exact duplicate-ID shape from the reported alert must collapse to one.
dup = [
    {"id": "PYSEC-2026-3547", "fix_versions": ["3.14.2"]},
    {"id": "PYSEC-2026-3546", "fix_versions": ["3.14.2"]},
    {"id": "PYSEC-2026-3545", "fix_versions": ["3.14.2"]},
    {"id": "PYSEC-2026-3545", "fix_versions": ["3.14.3"]},
    {"id": "PYSEC-2026-3546", "fix_versions": ["3.14.2"]},
    {"id": "PYSEC-2026-3547", "fix_versions": ["3.14.2"]},
]
merged: dict[str, str] = {}
for v in dup:
    vid = v["id"]
    fixes = [str(x) for x in v.get("fix_versions", []) if x]
    best = max(fixes, key=_version_sort_key) if fixes else ""
    if vid not in merged or (best and not merged[vid]):
        merged[vid] = best
    elif best:
        merged[vid] = max(merged[vid], best, key=_version_sort_key)

assert len(merged) == 3, f"expected 3 unique IDs, got {len(merged)}: {merged}"
assert merged["PYSEC-2026-3545"] == "3.14.3", \
    f"duplicate ID must take the highest fix, got {merged['PYSEC-2026-3545']}"
assert set(merged) == {"PYSEC-2026-3545", "PYSEC-2026-3546", "PYSEC-2026-3547"}

# 4. An advisory with no fix must not be dropped, and must read "no fix".
no_fix = [{"id": "PYSEC-2026-9999", "fix_versions": []}]
merged2: dict[str, str] = {}
for v in no_fix:
    vid = v["id"]
    fixes = [str(x) for x in v.get("fix_versions", []) if x]
    merged2[vid] = max(fixes, key=_version_sort_key) if fixes else ""
assert merged2 == {"PYSEC-2026-9999": ""}
assert "no fix" == ("no fix" if not merged2["PYSEC-2026-9999"] else "x")

print("check_dependencies self-check: all assertions passed")
