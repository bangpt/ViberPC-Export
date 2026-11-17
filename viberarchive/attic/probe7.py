import sqlite3, sys, json
from collections import Counter
from datetime import datetime, timezone, timedelta
HN = timezone(timedelta(hours=7))
iso = lambda ms: datetime.fromtimestamp(ms/1000, HN).strftime("%Y-%m-%d %H:%M:%S")
con = sqlite3.connect(sys.argv[1])

shape = Counter()
for d, info in con.execute("select e.Direction, m.Info from Events e join Messages m "
                           "on m.EventID=e.EventID where e.Type=3"):
    try:
        x = json.loads(info)["1on1reactions"]
    except Exception:
        shape[(d, "unparsed", "-", "-")] += 1
        continue
    keys = tuple(sorted(k for k in x if k.startswith("reaction")))
    shape[(d, keys, str(x.get("reaction")), str(x.get("reaction_v1")))] += 1
print("(direction, keys, reaction, reaction_v1) -> rows")
for k, n in sorted(shape.items(), key=lambda kv: str(kv[0])):
    print(k, n)

rx = {}
for ts, d, body, info in con.execute(
        "select e.TimeStamp, e.Direction, m.Body, m.Info from Events e join Messages m "
        "on m.EventID=e.EventID where e.Type=3 order by e.TimeStamp, e.SortOrder, e.Seq"):
    rx.setdefault(str(body).strip(), []).append((ts, d, info))

def minute(s):
    a = int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=HN).timestamp() * 1000)
    return a, a + 60000

for label in ("2026-09-25 11:15", "2026-09-25 11:04"):
    a, b = minute(label)
    print("== messages in minute", label)
    for ts, d, tok, st, mr, lk in con.execute(
            "select e.TimeStamp, e.Direction, e.Token, m.Status, m.MembersReactions, "
            "m.PGIsLiked from Events e join Messages m on m.EventID=e.EventID "
            "where e.Type=0 and e.TimeStamp>=? and e.TimeStamp<? "
            "order by e.TimeStamp, e.SortOrder, e.Seq", (a, b)):
        print(iso(ts), "dir", d, "status", st, "MembersReactions", mr, "PGIsLiked", lk)
        for rts, rd, info in rx.get(str(tok), []):
            try:
                x = {k: v for k, v in json.loads(info)["1on1reactions"].items()
                     if k.startswith("reaction")}
            except Exception:
                x = "unparsed"
            print("    reaction row", iso(rts), "dir", rd, x)