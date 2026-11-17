"""Messages with PC status 129: is each one followed by the same text sent again? Read-only.
usage: python probe28.py archive\\archive.db
"""
import sqlite3, sys
from collections import Counter
from datetime import datetime, timezone, timedelta

arc = sqlite3.connect(f"file:{sys.argv[1] if len(sys.argv) > 1 else 'archive/archive.db'}?mode=ro", uri=True)
tz = timezone(timedelta(hours=7))
rows = arc.execute("SELECT id, chat_key, composed_ms, text, tick, source, kind FROM message WHERE status = 129").fetchall()
print("messages with status 129:", len(rows), " by source:", dict(Counter(r[5] for r in rows)),
      " by kind:", dict(Counter(r[6] for r in rows)))
phone_ids = {r[0] for r in arc.execute("SELECT entity_id FROM source_record WHERE entity='message' AND snapshot_id IN"
                                       " (SELECT id FROM source_snapshot WHERE source LIKE 'phone%')")}
kinds = Counter()
for mid, chat, ms, text, tick, source, kind in rows:
    twin = arc.execute("SELECT id, composed_ms, status, tick FROM message WHERE chat_key = ? AND direction = 'out' AND id <> ?"
                       " AND text = ? AND composed_ms BETWEEN ? AND ? ORDER BY composed_ms LIMIT 1",
                       (chat, mid, text, ms - 600000, ms + 600000)).fetchone()
    if twin:
        kinds["same text sent again within 10 min"] += 1
        delta = round((twin[1] - ms) / 1000)
        on_phone = twin[0] in phone_ids
        print(f"  {datetime.fromtimestamp(ms/1000, tz):%Y-%m-%d %H:%M:%S}  first on phone: {mid in phone_ids!s:5}  "
              f"twin {delta:+5d}s  twin status {twin[2]}  twin on phone: {on_phone}")
    else:
        kinds["no twin"] += 1
        print(f"  {datetime.fromtimestamp(ms/1000, tz):%Y-%m-%d %H:%M:%S}  first on phone: {mid in phone_ids!s:5}  NO twin  tick {tick}")
print(dict(kinds))
