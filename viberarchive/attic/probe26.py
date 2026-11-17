"""Which sticker messages have no picture yet, and does the recovered .stickers folder have them? Read-only."""
import os, re, sqlite3, sys
from collections import Counter

db = sys.argv[1] if len(sys.argv) > 1 else r"archive\archive.db"
root = sys.argv[2] if len(sys.argv) > 2 else r"D:\ViberRecovery\files\files\.stickers"
arc = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
ids = Counter()
for (text,) in arc.execute("SELECT text FROM message WHERE kind = 'sticker'"):
    found = re.search(r"#(\d+)", text or "")
    if found:
        ids[int(found.group(1))] += 1
linked = {r[0] for r in arc.execute("SELECT message_id FROM message_media")} if arc.execute(
    "SELECT count(*) FROM sqlite_master WHERE name='message_media'").fetchone()[0] else set()
no_pic = [mid for (mid,) in arc.execute("SELECT id FROM message WHERE kind='sticker'") if mid not in linked]
print(f"sticker messages: {sum(ids.values())}  distinct sticker ids: {len(ids)}  without a picture yet: {len(no_pic)}")

files, exts, dirs = {}, Counter(), Counter()
for base, _, names in os.walk(root):
    for name in names:
        exts[os.path.splitext(name)[1].lower() or "(none)"] += 1
        dirs[os.path.relpath(base, root).split(os.sep)[0]] += 1
        stem = os.path.splitext(name)[0]
        digits = re.fullmatch(r"0*(\d+)(?:[_@.-].*)?", stem)
        if digits:
            files.setdefault(int(digits.group(1)), os.path.join(base, name))
print("files by extension:", dict(exts))
print("pack folders:", len(dirs), " biggest:", dirs.most_common(5))
have = [i for i in ids if i in files]
print(f"sticker ids found by number in file name: {len(have)} of {len(ids)} ({sum(ids[i] for i in have)} messages)")
pack = os.path.join(root, "154500")
print("sample of", pack)
for name in sorted(os.listdir(pack))[:25] if os.path.isdir(pack) else []:
    p = os.path.join(pack, name)
    print("  ", name, os.path.getsize(p) if os.path.isfile(p) else "<folder>")
print("most used ids with no file:", [i for i, _ in ids.most_common() if i not in files][:15])
