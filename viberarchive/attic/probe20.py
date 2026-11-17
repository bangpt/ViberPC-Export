"""Where does a phone reaction row keep the token of the message it reacts to? Read-only; prints field names only.
    python probe20.py phone_messages_db viber_export.db
For the reaction rows that both sources have, the PC knows the target token. This looks for that same number in
every column and every JSON field of the phone row and counts which field holds it."""
import json
import sqlite3
import sys
from collections import Counter

ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
ph.row_factory = sqlite3.Row
pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
target = {str(t).strip(): str(b).strip() for t, b in pc.execute(
    "SELECT e.Token, m.Body FROM Events e JOIN Messages m ON m.EventID=e.EventID WHERE e.Type=3")}


def walk(obj, prefix):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{prefix}.{k}")
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, f"{prefix}[]")
    else:
        yield prefix, obj


hits, total, none = Counter(), 0, 0
paths_seen = Counter()
for row in ph.execute("SELECT * FROM messages WHERE msg_info LIKE '%1on1reactions%' AND token > 0"):
    want = target.get(str(row["token"]))
    if want is None:
        continue
    total += 1
    found = set()
    for col in row.keys():
        v = row[col]
        if isinstance(v, (bytes, bytearray)):
            continue
        if str(v).strip() == want:
            found.add(col)
        if col in ("msg_info", "quoted_message_data") and v:
            try:
                for path, val in walk(json.loads(v), col):
                    paths_seen[path] += 1
                    if str(val).strip() == want:
                        found.add(path)
            except (TypeError, ValueError):
                pass
    for f in found:
        hits[f] += 1
    if not found:
        none += 1
print("shared reaction rows examined:", total, " rows where the target token was found nowhere:", none)
print("fields that hold the target token (rows):", hits.most_common(10))
print("JSON paths present in reaction rows (top 25):")
for p, n in paths_seen.most_common(25):
    print("  ", n, p)
