"""Profile the phone `messages` table without printing any message text. Read-only.
    python probe14.py phone_messages_db [viber_export.db]
Prints value counts of the small code columns, how filled the other columns are, how token and
msg_date relate, and (if you pass the PC export) how many phone tokens exist in the PC export."""
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=7))
ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
q = lambda sql, *a: ph.execute(sql, a).fetchall()  # noqa: E731

print("== small code columns: value -> rows (top 12)")
for c in ("conversation_type", "send_type", "extra_mime", "status", "flag", "deleted", "unread", "opened",
          "sync_read", "my_reaction", "likes_count", "extra_status", "timebomb", "event_count"):
    rows = q(f'SELECT {c}, count(*) FROM messages GROUP BY 1 ORDER BY 2 DESC LIMIT 12')
    print(f"{c}: " + ", ".join(f"{v}->{n}" for v, n in rows))
print("\n== bit patterns (distinct values, top 12)")
for c in ("extra_flags", "extra_flags2"):
    rows = q(f'SELECT {c}, count(*) FROM messages GROUP BY 1 ORDER BY 2 DESC LIMIT 12')
    print(f"{c}: " + ", ".join(f"{v}->{n}" for v, n in rows))

print("\n== how filled (non-empty rows)")
for c in ("body", "description", "msg_info", "msg_info_bin", "quoted_message_data", "my_reaction_extended",
          "reference_token", "extra_uri", "destination_uri", "sticker_id", "spans", "message_global_id",
          "read_message_time", "comment_thread_id", "seq", "user_id"):
    n = q(f"SELECT count(*) FROM messages WHERE {c} IS NOT NULL AND {c} != '' AND {c} != 0")[0][0]
    print(f"{c}: {n}")

print("\n== time columns")
def t(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, tz).strftime("%d/%m/%Y %H:%M:%S") if ms else None
    except (OverflowError, OSError, ValueError, TypeError):
        return "(not a time)"
mn, mx, same, near = q("SELECT min(token), max(token), sum(token=order_key), sum(abs(token-msg_date)<1000) FROM messages")[0]
print("token min/max:", mn, mx, "=", t(mn), "..", t(mx))
print("rows where token = order_key:", same, "; rows where |token - msg_date| < 1 s:", near)
print("rows where token is null/0:", q("SELECT count(*) FROM messages WHERE token IS NULL OR token=0")[0][0])
print("distinct tokens:", q("SELECT count(DISTINCT token) FROM messages")[0][0], "of", q("SELECT count(*) FROM messages")[0][0])
d = Counter()
for (x,) in q("SELECT token-msg_date FROM messages WHERE token>0 AND msg_date>0 LIMIT 200000"):
    d[max(-5000, min(5000, x // 1000))] += 1
print("token - msg_date in whole seconds (top 8):", d.most_common(8))
print("rows per year:", q("SELECT strftime('%Y', msg_date/1000, 'unixepoch', '+7 hours'), count(*) FROM messages GROUP BY 1"))
print("rows per conversation_type x deleted:", q("SELECT conversation_type, deleted, count(*) FROM messages GROUP BY 1,2"))

if len(sys.argv) > 2:
    pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)
    print("\n== overlap with the PC export (Events.Token, content and reaction rows)")
    ptok = {str(r[0]).strip() for r in pc.execute("SELECT Token FROM Events WHERE Token IS NOT NULL AND Type IN (0,3)")}
    pho = {str(r[0]) for r in ph.execute("SELECT token FROM messages WHERE token>0")}
    print("PC tokens:", len(ptok), "phone tokens:", len(pho), "in both:", len(ptok & pho))
    print("phone only:", len(pho - ptok), "PC only:", len(ptok - pho))
    by = Counter()
    for (tok, ms) in ph.execute("SELECT token, msg_date FROM messages WHERE token>0"):
        if str(tok) not in ptok:
            by[(t(ms) or "?")[6:10]] += 1
    print("phone-only by year:", sorted(by.items()))
    ptime = {str(r[0]).strip(): r[1] for r in pc.execute("SELECT Token, TimeStamp FROM Events WHERE Type=0 AND Token IS NOT NULL")}
    diffs = Counter()
    for (tok, ms) in ph.execute("SELECT token, msg_date FROM messages WHERE token>0"):
        p = ptime.get(str(tok))
        if p is not None:
            diffs[round(ms / 1000 - (p if p < 1e11 else p / 1000))] += 1
    print("phone msg_date minus PC TimeStamp, seconds (top 10; check the PC unit if all look huge):", diffs.most_common(10))
