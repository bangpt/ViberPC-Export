import sqlite3, sys, json
from collections import Counter
from datetime import datetime, timezone, timedelta
HN = timezone(timedelta(hours=7))
iso = lambda ms: datetime.fromtimestamp(ms/1000, HN).strftime("%Y-%m-%d %H:%M")
con = sqlite3.connect(sys.argv[1])
q = lambda s: con.execute(s).fetchall()

rows = q("select e.EventID, e.TimeStamp, e.Direction, m.Body, m.Info from Events e "
         "join Messages m on m.EventID=e.EventID where e.Type=3 "
         "order by e.TimeStamp, e.SortOrder, e.Seq")
tok = {str(t): eid for eid, t in con.execute(
    "select EventID, Token from Events where Type=0 and Token is not null")}
flags = {eid: (mr, liked, sr) for eid, mr, liked, sr in con.execute(
    "select EventID, MembersReactions, PGIsLiked, SelfReaction from Messages")}

def rid_of(info):
    try:
        d = json.loads(info)["1on1reactions"]
        return str(d.get("reaction") or d.get("reaction_v1") or "none")
    except Exception:
        return "unparsed"

print("reaction ids by direction:", sorted(Counter((r[2], rid_of(r[4])) for r in rows).items()))
state, rowsper = {}, Counter()
for eid, ts, d, body, info in rows:
    t = tok.get(str(body).strip())
    if t is None:
        continue
    state[(t, d)] = rid_of(info)
    rowsper[(t, d)] += 1
print("target/direction pairs:", len(state), "with more than one row:",
      sum(1 for v in rowsper.values() if v > 1))
active = {k for k, v in state.items() if v not in ("none", "unparsed", "0")}
print("active final reactions by direction:", Counter(k[1] for k in active))
for d in (0, 1):
    tg = {k[0] for k in active if k[1] == d}
    print("direction", d, "targets", len(tg),
          "| MembersReactions set:", sum(1 for t in tg if flags[t][0]),
          "| PGIsLiked>0:", sum(1 for t in tg if (flags[t][1] or 0) > 0),
          "| SelfReaction set:", sum(1 for t in tg if flags[t][2]))
print("Status 129 outgoing content:", [iso(r[0]) for r in q(
    "select e.TimeStamp from Events e join Messages m on m.EventID=e.EventID "
    "where e.Type=0 and m.Status=129 order by 1")])