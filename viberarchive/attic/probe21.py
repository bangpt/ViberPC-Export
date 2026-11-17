"""Which photo/video files do you have, and how are they named? Read-only; prints counts and name SHAPES only.
    python probe21.py --archive archive\\archive.db --pc-folder ..\\ViberPCExport --phone-mirror <phone media folder>
                      [--phone-db D:\\ViberRecovery\\DatabaseCopy\\viber_messages]
A name shape replaces letters with a, digits with N and long runs with a short mark, so no real name is shown."""
import argparse
import csv
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def shape(name):
    name = re.sub(r"[0-9a-fA-F]{16,}", "<HEX>", name)
    name = re.sub(r"\d+", "N", name)
    return re.sub(r"[A-Za-z]+", "a", name)[:60]


ap = argparse.ArgumentParser()
ap.add_argument("--archive", required=True)
ap.add_argument("--pc-folder")
ap.add_argument("--phone-mirror")
ap.add_argument("--phone-db")
a = ap.parse_args()

print("== A. PC export folder")
if a.pc_folder:
    root = Path(a.pc_folder)
    for item in sorted(root.iterdir())[:25]:
        if item.is_dir():
            n = sum(len(f) for _, _, f in os.walk(item))
            print(f"  dir  {item.name}: {n:,} files")
        else:
            print(f"  file {item.name}: {item.stat().st_size:,} bytes")
    index = next(root.rglob("media_index.csv"), None)
    print("media_index.csv:", index if index else "not found")
    if index:
        with open(index, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh))
        print("  columns:", list(rows[0]) if rows else [], " rows:", len(rows))
        print("  file name shapes:", Counter(shape(os.path.basename(r.get("file") or r.get("path") or "")) for r in rows).most_common(5))

print("\n== B. Media in the archive")
arc = sqlite3.connect(f"file:{a.archive}?mode=ro", uri=True)
print("messages by kind (media kinds only):",
      arc.execute("SELECT kind, source, count(*), sum(media_path IS NOT NULL AND media_path != '') FROM message "
                  "WHERE kind IN ('image','video','file','voice','sticker') GROUP BY kind, source").fetchall())
paths = [r[0] for r in arc.execute("SELECT media_path FROM message WHERE source LIKE 'pc-%' AND media_path LIKE '_:%' LIMIT 3000")]
print("PC media paths sampled:", len(paths), " that exist on THIS computer:", sum(os.path.exists(p) for p in paths))
print("PC path shapes:", Counter(shape(os.path.dirname(p)) for p in paths).most_common(4))

print("\n== C. Phone media mirror")
if a.phone_mirror:
    manifest = Path(a.phone_mirror) / "manifest.csv"
    if manifest.exists():
        with open(manifest, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        print("manifest rows:", len(rows), " by label:", Counter(r["label"] for r in rows).most_common())
        print("extensions:", Counter(os.path.splitext(r["remote_path"])[1].lower() for r in rows).most_common(8))
        print("name shapes:", Counter(shape(os.path.basename(r["remote_path"])) for r in rows).most_common(8))
        print("folder shapes:", Counter(shape(os.path.dirname(r["remote_path"]).split("files/")[-1]) for r in rows).most_common(6))
        years = Counter(datetime.fromtimestamp(int(r["mtime"]), timezone.utc).strftime("%Y") for r in rows)
        print("files by modified year:", sorted(years.items()))
    else:
        print("no manifest.csv in", a.phone_mirror)

print("\n== D. Phone database media addresses")
if a.phone_db:
    ph = sqlite3.connect(f"file:{a.phone_db}?mode=ro", uri=True)
    rows = ph.execute("SELECT extra_mime, extra_uri, msg_date FROM messages WHERE extra_uri IS NOT NULL AND extra_uri != ''").fetchall()
    print("rows with an address:", len(rows), " by mime:", Counter(r[0] for r in rows).most_common())
    print("address shapes:", Counter(shape(re.split(r"[?]", r[1])[0]) for r in rows).most_common(6))
    years = Counter(datetime.fromtimestamp(r[2] / 1000, timezone.utc).strftime("%Y") for r in rows if r[2] and r[2] > 0)
    print("by year:", sorted(years.items()))
