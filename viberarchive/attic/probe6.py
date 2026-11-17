import sqlite3, sys, json
from collections import Counter
con = sqlite3.connect(sys.argv[1])
tok = {str(t): eid for eid, t in con.execute(
    "select EventID, Token from Events where Type=0 and Token is not null")}
flags = {eid: (mr, lk) for eid, mr, lk in con.execute(
    "select EventID, MembersReactions, PGIsLiked from Messages")}
rows = con.execute("select m.Body, m.Info from Events e join Messages m on m.EventID=e.EventID "
                   "where e.Type=3 and e.Direction=1").fetchall()
parsed, bad = set(), []
for body, info in rows:
    t = str(body).strip()
    try:
        json.loads(info)["1on1reactions"]
        parsed.add(t)
    except Exception:
        bad.append(t)
c, ids = Counter(), Counter()
for t in bad:
    e = tok.get(t)
    if e is None:
        c["no target"] += 1
        continue
    mr, lk = flags[e]
    c["MembersReactions set" if mr else "MembersReactions empty"] += 1
    c["PGIsLiked>0" if (lk or 0) > 0 else "PGIsLiked=0"] += 1
    c["target also has a parsed row" if t in parsed else "only unparsed rows"] += 1
    if mr:
        try:
            ids.update(json.loads(mr).keys())
        except Exception:
            ids["unparsed"] += 1
print(dict(c))
print("ids in MembersReactions:", dict(ids))