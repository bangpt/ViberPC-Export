import sqlite3, sys, json
from datetime import datetime, timezone, timedelta
HN = timezone(timedelta(hours=7))
iso = lambda ms: datetime.fromtimestamp(ms/1000, HN).strftime("%Y-%m-%d %H:%M:%S")
con = sqlite3.connect(sys.argv[1])
tok = {str(t): ts for t, ts in con.execute(
    "select Token, TimeStamp from Events where Type=0 and Token is not null")}
last = {}
for d, body, info in con.execute(
        "select e.Direction, m.Body, m.Info from Events e join Messages m "
        "on m.EventID=e.EventID where e.Type=3 order by e.TimeStamp, e.SortOrder, e.Seq"):
    try:
        last[(str(body).strip(), d)] = json.loads(info)["1on1reactions"].get("reaction")
    except Exception:
        pass
for want in (4, 5):
    for d in (0, 1):
        hits = sorted(tok[t] for (t, dd), r in last.items() if dd == d and r == want and t in tok)
        for ts in hits[-3:]:
            lo = ts - ts % 60000
            n = con.execute("select count(*) from Events where Type=0 and TimeStamp>=? "
                            "and TimeStamp<?", (lo, lo + 60000)).fetchone()[0]
            print("id", want, "reactor", "her" if d == 0 else "you",
                  "| message at", iso(ts), "| messages in that minute:", n)