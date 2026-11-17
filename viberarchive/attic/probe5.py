import sqlite3, sys, json
from collections import Counter
from datetime import datetime, timezone, timedelta
HN = timezone(timedelta(hours=7))
iso = lambda ms: datetime.fromtimestamp(ms/1000, HN).strftime("%Y-%m-%d %H:%M")
con = sqlite3.connect(sys.argv[1])
target_ts = {str(t): ts for t, ts in con.execute(
    "select Token, TimeStamp from Events where Type=0 and Token is not null")}
rows = con.execute(
    "select e.TimeStamp, e.Direction, m.Body, m.Info from Events e "
    "join Messages m on m.EventID=e.EventID where e.Type=3 "
    "order by e.TimeStamp, e.SortOrder, e.Seq").fetchall()

bad, final = [], {}
for ts, d, body, info in rows:
    try:
        x = json.loads(info)["1on1reactions"]
        rid = str(x.get("reaction") or x.get("reaction_v1") or "none")
    except Exception:
        bad.append((ts, d, body, info))
        continue
    final[(str(body).strip(), d)] = rid

print("unparsed reaction rows:", len(bad), "directions:", Counter(b[1] for b in bad))
print("  Info empty:", sum(1 for b in bad if not b[3]))
shapes = Counter()
for b in bad:
    try:
        v = json.loads(b[3])
        shapes[tuple(sorted(v)) if isinstance(v, dict) else type(v).__name__] += 1
    except Exception:
        shapes["not json"] += 1
print("  Info shapes:", shapes.most_common(8))
print("  by year:", sorted(Counter(datetime.fromtimestamp(b[0]/1000, HN).year for b in bad).items()))
print("  target found:", sum(1 for b in bad if str(b[2]).strip() in target_ts))

print("most recent targets per (direction, reaction id):")
best = {}
for (tok, d), rid in final.items():
    if rid == "none" or tok not in target_ts:
        continue
    best.setdefault((d, rid), []).append(target_ts[tok])
for k in sorted(best):
    print(" ", k, len(best[k]), [iso(t) for t in sorted(best[k])[-2:]])