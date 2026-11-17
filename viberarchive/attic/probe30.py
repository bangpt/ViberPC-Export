"""Where do the edit_ref_missing messages sit? Run from the ViberPC-Export folder: python probe30.py"""
import collections
import datetime
import sqlite3

con = sqlite3.connect("archive/archive.db")
rows = con.execute("""SELECT id, chat_key, direction, composed_ms, source, version_count, kind, substr(text, 1, 50)
  FROM message WHERE flags LIKE '%edit_ref_missing%' ORDER BY composed_ms""").fetchall()
tz = datetime.timezone(datetime.timedelta(hours=7))


def when(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, tz)


print("total:", len(rows))
print("by source:", collections.Counter((r[4] or "")[:8] for r in rows))
print("by direction:", collections.Counter(r[2] for r in rows))
print("by year:", sorted(collections.Counter(when(r[3]).year for r in rows).items()))
print("by chat:", collections.Counter(r[1] for r in rows))
print("by month (top 12):", collections.Counter(when(r[3]).strftime("%Y-%m") for r in rows).most_common(12))
first = con.execute("SELECT min(composed_ms), max(composed_ms) FROM message").fetchone()
print("archive range:", when(first[0]).date(), "to", when(first[1]).date())
gaps = []
for mid, chat, _, ms, *_ in rows:
    prev = con.execute("SELECT max(composed_ms) FROM message WHERE chat_key=? AND composed_ms<?", (chat, ms)).fetchone()[0]
    gaps.append((ms - prev) / 1000 if prev else None)
known = sorted(g for g in gaps if g is not None)
if known:
    print("seconds since previous message in chat: median %.0f, p90 %.0f" % (known[len(known) // 2], known[int(len(known) * .9)]))
print("first 12 and last 12:")
for r in rows[:12] + rows[-12:]:
    print("  ", when(r[3]).strftime("%Y-%m-%d %H:%M"), r[4], r[2], r[6], repr(r[7]))
