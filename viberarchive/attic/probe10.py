import sqlite3, sys, json
from collections import Counter
from datetime import datetime, timezone, timedelta
HN = timezone(timedelta(hours=7))
iso = lambda ms: datetime.fromtimestamp(ms/1000, HN).strftime("%Y-%m-%d %H:%M")
con = sqlite3.connect(sys.argv[1])

by_eid, by_tok = {}, {}
for eid, t, ty, ts, d in con.execute("select EventID, Token, Type, TimeStamp, Direction from Events"):
    by_eid[eid] = (ts, d, ty)
    by_tok[str(t).strip()] = eid

edits = {}
for eid, info in con.execute(
        "select m.EventID, m.Info from Messages m join Events e on e.EventID=m.EventID "
        "where e.Type=0 and m.Info like '%\"edit\"%'"):
    try:
        d = json.loads(info)
    except Exception:
        continue
    if isinstance(d, dict) and isinstance(d.get("edit"), dict):
        edits[eid] = d["edit"]

print("all edit key sets:", Counter(tuple(sorted(e)) for e in edits.values()).most_common(12))

target_of = {}
for eid, e in edits.items():
    t = by_tok.get(str(e["token"]).strip()) if "token" in e else None
    if t is not None and t != eid:
        target_of[eid] = t
print("edit events pointing to another edit event:", sum(1 for t in target_of.values() if t in edits))
print("edits per original (count of edits -> originals):",
      sorted(Counter(Counter(target_of.values()).values()).items()))

miss = [eid for eid, e in edits.items() if "token" in e and eid not in target_of]
print("edit.token not found:", len(miss), "| by year:",
      sorted(Counter(datetime.fromtimestamp(by_eid[m][0]/1000, HN).year for m in miss).items()))

ew = Counter()
for eid, e in edits.items():
    if "editedWithToken" in e:
        t = by_tok.get(str(e["editedWithToken"]).strip())
        ew["no such event" if t is None else
           ("event type %s" % by_eid[t][2], "later" if by_eid[t][0] > by_eid[eid][0] else "earlier")] += 1
print("editedWithToken points to:", dict(ew))

rows = sorted(((by_eid[e][0] - by_eid[t][0], e, t) for e, t in target_of.items()), reverse=True)
print("edits with the longest gap (original time -> edit time):")
for gap, e, t in rows[:4]:
    print("  ", iso(by_eid[t][0]), "->", iso(by_eid[e][0]))