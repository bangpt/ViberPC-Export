"""Can the phone's copied photos be matched to messages by time? Read-only; prints counts only.
    python probe23.py --phone-db viber_messages --phone-mirror <phone media folder>
For every photo or video message in the phone database, finds the copied file whose modified time is closest."""
import argparse
import csv
import sqlite3
from bisect import bisect_left
from collections import Counter
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--phone-db", required=True)
ap.add_argument("--phone-mirror", required=True)
a = ap.parse_args()

files = []
with open(Path(a.phone_mirror) / "manifest.csv", newline="", encoding="utf-8") as fh:
    for row in csv.DictReader(fh):
        ext = row["remote_path"].rsplit(".", 1)[-1].lower()
        if ext in ("jpg", "mp4"):
            files.append((int(row["mtime"]) * 1000, ext, "hidden" if "/." in row["remote_path"] else "gallery"))
files.sort()
times = [f[0] for f in files]
ph = sqlite3.connect(f"file:{a.phone_db}?mode=ro", uri=True)
msgs = sorted((r[0], r[1], r[2]) for r in ph.execute(
    "SELECT msg_date, extra_mime, send_type FROM messages WHERE extra_mime IN (1, 3) AND msg_date > 0"))
mtimes = [m[0] for m in msgs]
print("photo/video messages:", len(msgs), " copied jpg/mp4 files:", len(files))


def nearest(sorted_times, t):
    i = bisect_left(sorted_times, t)
    best = None
    for j in (i - 1, i):
        if 0 <= j < len(sorted_times) and (best is None or abs(sorted_times[j] - t) < abs(sorted_times[best] - t)):
            best = j
    return best


mine = {}
for k, (t, _mime, _dir) in enumerate(msgs):
    j = nearest(times, t)
    mine[k] = (j, times[j] - t)
back = {}
for j, ft in enumerate(times):
    k = nearest(mtimes, ft)
    back[j] = k
deltas = [d for _j, d in mine.values()]
for limit in (2_000, 10_000, 60_000, 600_000, 3_600_000):
    print(f"messages whose nearest file is within {limit // 1000} s: {sum(abs(d) <= limit for d in deltas):,}")
mutual = [(k, j, d) for k, (j, d) in mine.items() if back[j] == k]
print("mutual nearest pairs:", len(mutual), " of which within 10 s:", sum(abs(d) <= 10_000 for _k, _j, d in mutual),
      " within 60 s:", sum(abs(d) <= 60_000 for _k, _j, d in mutual))
print("signed offset file minus message, whole seconds (top 10):",
      Counter(round(d / 1000) for _k, _j, d in mutual if abs(d) <= 60_000).most_common(10))
print("matched files by folder:", Counter(files[j][2] for _k, j, d in mutual if abs(d) <= 10_000))
print("messages by direction among those matched (0 in, 1 out):",
      Counter(msgs[k][2] for k, _j, d in mutual if abs(d) <= 10_000))
print("photo messages by direction overall:", Counter(m[2] for m in msgs))
