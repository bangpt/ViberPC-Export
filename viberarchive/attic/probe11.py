"""Which stored timestamp does Viber display? Read-only.
    python probe11.py .\\ViberPCExport\\viber_export.db
Prints every time-like column of Events and Messages for the outgoing messages
between 20:55 and 21:06 (Hanoi time) on 15/07/2025. No message text."""
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
ev = [r[1] for r in con.execute("PRAGMA table_info(Events)")]
ms = [r[1] for r in con.execute("PRAGMA table_info(Messages)")]
pat = re.compile(r"time|date|stamp|sent|deliver|server|seen|read|created|modified", re.I)
tev = [c for c in ev if pat.search(c)]
tms = [c for c in ms if pat.search(c)]
print("Events time-like columns  :", tev)
print("Messages time-like columns:", tms)
tz = timezone(timedelta(hours=7))


def show(v):
    if isinstance(v, (int, float)) and v > 10**11:
        return datetime.fromtimestamp(v / 1000, tz).strftime("%H:%M:%S")
    if isinstance(v, (int, float)) and 10**9 < v < 10**11:
        return datetime.fromtimestamp(v, tz).strftime("%H:%M:%S") + "(s)"
    return str(v)


sel = ", ".join([f"e.{c}" for c in tev] + [f"m.{c}" for c in tms] + ["m.Status", "length(m.Body)"])
q = (f"SELECT {sel} FROM Events e JOIN Messages m ON m.EventID=e.EventID WHERE e.Type=0 AND e.Direction=1 "
     "AND strftime('%d/%m/%Y %H:%M', e.TimeStamp/1000,'unixepoch','+7 hours') BETWEEN '15/07/2025 20:55' AND '15/07/2025 21:06' "
     "ORDER BY e.TimeStamp")
print("\ncolumns: " + " | ".join([f"e.{c}" for c in tev] + [f"m.{c}" for c in tms] + ["Status", "len"]))
for row in con.execute(q):
    print("  ", " | ".join(show(v) for v in row))
