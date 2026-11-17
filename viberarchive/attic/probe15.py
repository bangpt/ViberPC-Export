"""Second profile of the phone `messages` table. Read-only, no message text, names or numbers.
    python probe15.py phone_messages_db viber_export.db
Prints: which tokens differ between phone and PC (by year, type, kind), the key names (not values)
inside msg_info / quoted_message_data, what reference_token points to, and how the phone's reaction
columns line up with the PC reaction rows."""
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=7))
ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)


def year(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, tz).strftime("%Y")
    except (OverflowError, OSError, ValueError, TypeError):
        return "?"


def pyear(ts):
    ts = ts or 0
    return year(ts if ts > 1e11 else ts * 1000)


def tk(v):
    return None if v is None or str(v).strip() == "" else str(v).strip()


ptype, pyr = {}, {}
for tok, typ, ts in pc.execute("SELECT Token, Type, TimeStamp FROM Events WHERE Token IS NOT NULL"):
    if tk(tok):
        ptype[tk(tok)] = typ
        pyr[tk(tok)] = pyear(ts)
rows = ph.execute("SELECT token, msg_date, send_type, extra_mime, likes_count, my_reaction, reference_token, "
                  "msg_info, quoted_message_data, flag, read_message_time FROM messages").fetchall()
ptoks = {str(r[0]) for r in rows}

print("== PC-only tokens by PC Event.Type and year")
c = Counter((ptype[t], pyr[t]) for t in ptype if t not in ptoks)
print(sorted(c.items()))
print("== phone-only tokens by year, send_type, extra_mime (top 15)")
c = Counter((year(r[1]), r[2], r[3]) for r in rows if str(r[0]) not in ptype)
print(c.most_common(15))
print("phone-only with a non-empty body? (count only):",
      ph.execute("SELECT count(*) FROM messages WHERE body IS NOT NULL AND body != ''").fetchone()[0], "total non-empty")


def keys(raw, depth=0):
    try:
        obj = json.loads(raw)
    except (TypeError, ValueError):
        return ("(not json)",)
    if isinstance(obj, dict):
        return tuple(sorted(str(k)[:30] for k in obj))
    return ("(" + type(obj).__name__ + ")",)


print("\n== msg_info: key sets (top 15)")
c = Counter(keys(r[7]) for r in rows)
for k, n in c.most_common(15):
    print(n, k)
sub = Counter()
for r in rows:
    try:
        obj = json.loads(r[7])
    except (TypeError, ValueError):
        continue
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, dict):
                sub[(str(k)[:30], tuple(sorted(str(x)[:30] for x in v)))] += 1
print("nested objects inside msg_info (top 15):")
for k, n in sub.most_common(15):
    print(n, k)

print("\n== quoted_message_data: shapes (top 8)")
c = Counter(keys(r[8]) if r[8] not in ("", "{}", "[]", "null") else "(empty)" for r in rows)
for k, n in c.most_common(8):
    print(n, k)

print("\n== reference_token (non-zero rows)")
ref = [r for r in rows if r[6]]
print("rows:", len(ref), " pointing at a phone token:", sum(str(r[6]) in ptoks for r in ref),
      " at a PC token:", sum(str(r[6]) in ptype for r in ref))
print("by extra_mime:", Counter(r[3] for r in ref).most_common(6), " by send_type:", Counter(r[2] for r in ref))
print("msg_info key sets for those rows:", Counter(keys(r[7]) for r in ref).most_common(5))

print("\n== reactions")
print("my_reaction x likes_count:", sorted(Counter((r[5], r[4]) for r in rows).items()))
tg = Counter()
for (body,) in pc.execute("SELECT m.Body FROM Events e JOIN Messages m ON m.EventID=e.EventID WHERE e.Type=3"):
    tg[tk(body)] += 1
tg.pop(None, None)
liked = {str(r[0]) for r in rows if r[4]}
mine = {str(r[0]) for r in rows if r[5]}
print("PC reaction targets:", len(tg), " of those with likes_count>0 on phone:", len(set(tg) & liked),
      " with my_reaction>0:", len(set(tg) & mine))
print("phone likes_count>0 rows:", len(liked), " not among PC reaction targets:", len(liked - set(tg)))
print("phone my_reaction>0 rows:", len(mine), " not among PC reaction targets:", len(mine - set(tg)))
print("\n== read_message_time min/max:",
      ph.execute("SELECT min(read_message_time), max(read_message_time) FROM messages WHERE read_message_time>0").fetchone())
