import sqlite3, sys, json
from collections import Counter

con = sqlite3.connect(sys.argv[1])
q = lambda s: con.execute(s).fetchall()

n, null_t, distinct_t = q("select count(*), sum(Token is null or Token=''), count(distinct Token) from Events")[0]
print("events", n, "| Token empty", null_t, "| distinct tokens", distinct_t)
dups = "select Token from Events where Token is not null and Token<>'' group by Token having count(*)>1"
print("tokens shared by several events:", q(f"select count(*) from ({dups})")[0][0])
print("  by event Type:", q(f"select Type, count(*) from Events where Token in ({dups}) group by 1"))

tok = {}
for eid, t in con.execute("select EventID, Token from Events where Type=0 and Token is not null"):
    tok.setdefault(str(t).strip(), []).append(eid)
ts, dr = {}, {}
for eid, t, d in con.execute("select EventID, TimeStamp, Direction from Events"):
    ts[eid], dr[eid] = t, d

edits = []
for eid, info in con.execute(
        "select m.EventID, m.Info from Messages m join Events e on e.EventID=m.EventID "
        "where e.Type=0 and m.Info like '%\"edit\"%'"):
    try:
        d = json.loads(info)
    except Exception:
        continue
    if isinstance(d, dict) and "edit" in d:
        edits.append((eid, d["edit"]))
print("content events with an edit field:", len(edits))

shapes, links, gaps, originals = Counter(), Counter(), Counter(), set()
for eid, ed in edits:
    if not isinstance(ed, dict):
        shapes[type(ed).__name__] += 1
        continue
    shapes[tuple(sorted((k, type(v).__name__) for k, v in ed.items()))] += 1
    for k, v in ed.items():
        hit = [x for x in tok.get(str(v).strip(), []) if x != eid]
        if hit:
            links[k] += 1
            originals.add(hit[0])
            dt = (ts[eid] - ts[hit[0]]) / 1000
            b = ("before" if dt < 0 else "<1 min" if dt < 60 else "<1 h" if dt < 3600
                 else "<1 day" if dt < 86400 else ">=1 day")
            gaps[(k, b, "same sender" if dr[eid] == dr[hit[0]] else "other sender")] += 1
            break
print("edit field shapes:", shapes.most_common(5))
print("edit keys whose value is another message's Token:", dict(links))
print("edit -> original:", sorted(gaps.items(), key=str))

edit_ids, where, last = {e for e, _ in edits}, Counter(), {}
for body, d, info in con.execute(
        "select m.Body, e.Direction, m.Info from Events e join Messages m on m.EventID=e.EventID "
        "where e.Type=3 order by e.TimeStamp, e.SortOrder, e.Seq"):
    t = str(body).strip()
    hit = tok.get(t, [])
    if len(hit) == 1:
        h = hit[0]
        where["edit event" if h in edit_ids else "superseded original" if h in originals else "other"] += 1
    if d == 0:
        try:
            last[t] = json.loads(info)["1on1reactions"].get("reaction")
        except Exception:
            pass
print("reaction rows by target:", dict(where))

likes = dict(con.execute("select EventID, PGLikeCount from Messages"))
hers = [tok[t][0] for t, r in last.items() if r not in (0, None) and len(tok.get(t, [])) == 1]
print("her active reactions:", len(hers), "| of those with PGLikeCount>0:",
      sum(1 for e in hers if (likes.get(e) or 0) > 0))
print("outgoing messages with PGLikeCount>0:", q(
    "select count(*) from Messages m join Events e on e.EventID=m.EventID "
    "where e.Type=0 and e.Direction=1 and m.PGLikeCount>0")[0][0])