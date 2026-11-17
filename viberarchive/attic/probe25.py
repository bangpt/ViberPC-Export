"""List what is inside the Viber .emoticons folder (read-only)."""
import os, sys
from collections import Counter

root = sys.argv[1] if len(sys.argv) > 1 else r"D:\ViberRecovery\files\files\.emoticons"
exts, rows = Counter(), []
for base, dirs, names in os.walk(root):
    for name in names:
        path = os.path.join(base, name)
        exts[os.path.splitext(name)[1].lower() or "(none)"] += 1
        rows.append((os.path.relpath(path, root), os.path.getsize(path)))
print("files:", len(rows), " by extension:", dict(exts))
print("sub-folders:", sorted({os.path.dirname(r[0]) for r in rows})[:30])
for rel, size in sorted(rows)[:70]:
    print(f"  {size:>8}  {rel}")
print("names containing smiley/teeth/yummi/sad:")
for rel, size in rows:
    if any(k in rel.lower() for k in ("smiley", "teeth", "yummi", "sad", "wink")):
        print(f"  {size:>8}  {rel}")
