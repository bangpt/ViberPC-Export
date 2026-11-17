"""Find where the 9:03 PM display time could come from. Read-only, no message text.
    python probe12.py .\\ViberPCExport\\viber_export.db
For the outgoing messages 20:55-21:06 on 15/07/2025 prints every numeric column of Events
and Messages, every numeric value inside Info (as key=value), and each number that
looks like a time (epoch seconds or milliseconds) converted to Hanoi time."""
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=7))


def as_time(v):
    for div, tag in ((1000, "ms"), (1, "s")):
        x = v / div
        if 1.5e9 < x < 1.9e9:
            return datetime.fromtimestamp(x, tz).strftime("%d/%m %H:%M:%S") + f"[{tag}]"
    return None


def flat(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flat(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from flat(v, f"{prefix}{i}.")
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        yield prefix[:-1], obj


con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
rows = con.execute(
    "SELECT e.*, m.Info AS m_Info, m.Status AS m_Status, m.Type AS m_Type, length(m.Body) AS len "
    "FROM Events e JOIN Messages m ON m.EventID=e.EventID WHERE e.Type=0 AND e.Direction=1 "
    "AND strftime('%d/%m/%Y %H:%M', e.TimeStamp/1000,'unixepoch','+7 hours') BETWEEN '15/07/2025 20:55' AND '15/07/2025 21:06' "
    "ORDER BY e.TimeStamp").fetchall()
for r in rows:
    d = dict(r)
    info = d.pop("m_Info", None)
    print("\n" + datetime.fromtimestamp(d["TimeStamp"] / 1000, tz).strftime("%H:%M:%S"), "len", d.pop("len"))
    for k, v in d.items():
        if isinstance(v, (int, float)) and k != "EventID":
            t = as_time(v)
            print(f"   {k} = {v}" + (f"   -> {t}" if t else ""))
    if info:
        try:
            for k, v in flat(json.loads(info)):
                t = as_time(v)
                print(f"   Info.{k} = {v}" + (f"   -> {t}" if t else ""))
        except ValueError:
            print("   Info is not JSON, length", len(info))
