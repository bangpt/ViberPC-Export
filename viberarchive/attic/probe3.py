import sqlite3, sys
from datetime import datetime, timezone, timedelta
HN = timezone(timedelta(hours=7))
day = lambda ms: datetime.fromtimestamp(ms/1000, HN).strftime("%Y-%m-%d")
con = sqlite3.connect(sys.argv[1])
q = lambda s: con.execute(s).fetchall()

print("Status, Direction, EventType, count, first day, last day:")
for s, d, t, n, a, b in q("select m.Status, e.Direction, e.Type, count(*), min(e.TimeStamp), max(e.TimeStamp) from Messages m join Events e on e.EventID=m.EventID group by 1,2,3"):
    print(s, d, t, n, day(a), day(b))

by_token = {}
for eid, tok in con.execute("select EventID, Token from Events where Token is not null"):
    by_token.setdefault(str(tok), []).append(eid)
type_of = dict(con.execute("select EventID, Type from Events"))
one = many = none = 0
target_types = {}
for eid, body in con.execute("select m.EventID, m.Body from Messages m join Events e on e.EventID=m.EventID where e.Type=3"):
    hits = [x for x in by_token.get(str(body).strip(), []) if x != eid]
    if not hits:
        none += 1
    elif len(hits) == 1:
        one += 1
        target_types[type_of[hits[0]]] = target_types.get(type_of[hits[0]], 0) + 1
    else:
        many += 1
print("reaction rows -> target via Events.Token: one", one, "many", many, "none", none, "target event types", target_types)
print("SelfReaction set:", q("select count(*) from Messages where SelfReaction is not null and SelfReaction<>''")[0][0])
print("MembersReactions set:", q("select count(*) from Messages where MembersReactions is not null and MembersReactions<>''")[0][0])
print("PGIsLiked>0:", q("select count(*) from Messages where PGIsLiked>0")[0][0])
print("Info has 1on1reactions:", q("select count(*) from Messages where Info like '%1on1reactions%'")[0][0])