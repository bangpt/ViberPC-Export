"""Why do phone reaction rows not find their target? Read-only; prints counts and shapes only, no text.
    python probe19.py phone_messages_db viber_export.db archive.db"""
import json
import sqlite3
import sys
from collections import Counter

ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
arc = sqlite3.connect(f"file:{sys.argv[3]}?mode=ro", uri=True)


def shape(v):
    s = "" if v is None else str(v)
    return (type(v).__name__, len(s), "digits" if s.isdigit() else "other")


pcb = {}
for tok, body in pc.execute("SELECT e.Token, m.Body FROM Events e JOIN Messages m ON m.EventID=e.EventID WHERE e.Type=3"):
    pcb[str(tok).strip()] = body
rows = ph.execute("SELECT token, body, msg_info FROM messages WHERE msg_info LIKE '%1on1reactions%' AND token > 0").fetchall()
print("phone reaction-looking rows:", len(rows), " also PC reaction rows:", sum(str(r[0]) in pcb for r in rows))
print("body shape phone (top 5):", Counter(shape(r[1]) for r in rows).most_common(5))
print("body shape PC    (top 5):", Counter(shape(b) for b in pcb.values()).most_common(5))
same = Counter()
for tok, body, _ in rows:
    if tok_s := str(tok):
        if tok_s in pcb:
            p = pcb[tok_s]
            same["equal" if str(body).strip() == str(p).strip() else "different"] += 1
print("phone body vs PC body for the same row:", dict(same))
known = {r[0] for r in arc.execute("SELECT token FROM message WHERE token IS NOT NULL")}
print("archive message tokens:", len(known))
print("PC bodies found among archive tokens:", sum(str(b).strip() in known for b in pcb.values()), "of", len(pcb))
print("phone bodies found among archive tokens:", sum(str(r[1]).strip() in known for r in rows), "of", len(rows))
phone_tokens = {str(r[0]) for r in ph.execute("SELECT token FROM messages")}
print("phone bodies found among phone tokens:", sum(str(r[1]).strip() in phone_tokens for r in rows))
info_keys = Counter()
for _, _, info in rows:
    try:
        d = json.loads(info)["1on1reactions"]
        info_keys[tuple(sorted(d))] += 1
    except (TypeError, ValueError, KeyError):
        info_keys["unreadable"] += 1
print("1on1reactions key sets:", info_keys.most_common(5))
