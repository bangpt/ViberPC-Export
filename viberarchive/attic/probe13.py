"""Describe an unknown SQLite database without printing any content. Read-only.
    python probe13.py path\\to\\phone.db
Prints: each table's columns and row count, and for every integer column whose name looks like a
date or time, the first and last value converted to Hanoi time. No message text, no names, no numbers."""
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=7))


def as_time(v):
    for div in (1000, 1):
        x = v / div
        if 1.4e9 < x < 1.9e9:
            return datetime.fromtimestamp(x, tz).strftime("%d/%m/%Y %H:%M")
    return None


path = sys.argv[1]
with open(path, "rb") as fh:
    head = fh.read(16)
print("File header:", "SQLite format 3" if head.startswith(b"SQLite format 3") else repr(head[:16]))
if not head.startswith(b"SQLite format 3"):
    print("This is not a plain SQLite file (it may be encrypted or compressed). Stop here and tell me.")
    sys.exit(0)
con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
try:
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
except sqlite3.DatabaseError as exc:
    print("Cannot read it:", exc)
    sys.exit(0)
pat = re.compile(r"date|time|stamp|created|sent|received", re.I)
for t in tables:
    cols = [(r[1], r[2]) for r in con.execute(f'PRAGMA table_info("{t}")')]
    try:
        n = con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
    except sqlite3.DatabaseError as exc:
        print(f"\n{t}: unreadable ({exc})")
        continue
    print(f"\n{t}: {n:,} rows")
    print("   columns: " + ", ".join(f"{c} {ty}".strip() for c, ty in cols))
    if n == 0:
        continue
    for c, _ty in cols:
        if pat.search(c):
            lo, hi = con.execute(f'SELECT min("{c}"), max("{c}") FROM "{t}" WHERE typeof("{c}") IN ("integer","real")').fetchone()
            if lo is not None and as_time(lo) and as_time(hi):
                print(f"   {c}: {as_time(lo)}  to  {as_time(hi)}")
