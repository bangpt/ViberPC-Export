"""Do the phone database, the phone media copy and the PC media share file ids? Read-only; prints counts only.
    python probe22.py --archive archive.db --phone-db viber_messages --phone-mirror <phone media folder> --pc-folder <PC export folder>
A file id here is any run of 32 or more hex characters inside an address or file name."""
import argparse
import csv
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

HEX = re.compile(r"[0-9a-fA-F]{32,}")


def ids_of(text):
    return {m.lower() for m in HEX.findall(text or "")}


ap = argparse.ArgumentParser()
ap.add_argument("--archive", required=True)
ap.add_argument("--phone-db", required=True)
ap.add_argument("--phone-mirror", required=True)
ap.add_argument("--pc-folder", required=True)
a = ap.parse_args()

ph = sqlite3.connect(f"file:{a.phone_db}?mode=ro", uri=True)
db_ids = Counter()
for (uri,) in ph.execute("SELECT extra_uri FROM messages WHERE extra_uri IS NOT NULL AND extra_uri != ''"):
    for i in ids_of(uri):
        db_ids[i] += 1
print("phone database: addresses with an id:", len(db_ids), " (an id used by more than one message:", sum(v > 1 for v in db_ids.values()), ")")

mirror = {}
with open(Path(a.phone_mirror) / "manifest.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        for i in ids_of(os.path.basename(row["remote_path"])):
            mirror.setdefault(i, []).append(row["remote_path"])
print("phone media copy: file names with an id:", len(mirror), " of 2,544 files")
print("   ids found in BOTH the database and the copy:", len(set(db_ids) & set(mirror)))
print("   database ids with no file in the copy:", len(set(db_ids) - set(mirror)),
      " | copied files whose id the database does not know:", len(set(mirror) - set(db_ids)))
folders = Counter()
for i in set(db_ids) & set(mirror):
    folders[tuple(sorted({"hidden .image/.video" if "/.image/" in p or "/.video/" in p else "other" for p in mirror[i]}))] += 1
print("   matched files by folder:", folders.most_common(4))

pc_ids = {}
with open(Path(a.pc_folder) / "media_index.csv", newline="", encoding="utf-8-sig") as fh:
    for row in csv.DictReader(fh):
        for i in ids_of(row["orig_path"]) | ids_of(row["saved_path"]):
            pc_ids.setdefault(i, []).append(row["EventID"])
print("PC media index: rows with an id in the name:", len(pc_ids), " of 3,680")
print("   ids shared with the phone database:", len(set(pc_ids) & set(db_ids)),
      " | with the phone media copy:", len(set(pc_ids) & set(mirror)))
arc = sqlite3.connect(f"file:{a.archive}?mode=ro", uri=True)
arc_ids = set()
for (p,) in arc.execute("SELECT media_path FROM message WHERE media_path IS NOT NULL AND media_path != ''"):
    arc_ids |= ids_of(p)
print("archive media paths with an id:", len(arc_ids), " shared with the phone copy:", len(arc_ids & set(mirror)))
