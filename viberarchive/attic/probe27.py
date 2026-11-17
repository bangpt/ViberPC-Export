"""Show every trace of one message text in the archive, the PC export and the phone database. Read-only.
usage: python probe27.py archive\\archive.db ..\\ViberPCExport\\viber_export.db D:\\ViberRecovery\\DatabaseCopy\\viber_messages "some words"
"""
import json, sqlite3, sys

arc_path, pc_path, ph_path, needle = sys.argv[1:5]
def ro(p):
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True); c.row_factory = sqlite3.Row; return c
def edit_bits(info):
    try:
        d = json.loads(info) if info else {}
    except ValueError:
        return "?"
    return {k: d[k] for k in ("edit", "editedWithToken") if k in d}
like = f"%{needle}%"

print("== archive: messages")
arc = ro(arc_path)
for r in arc.execute("SELECT id, token, direction, composed_ms, sent_ms, kind, version_count, flags, source FROM message "
                     "WHERE text LIKE ? OR id IN (SELECT message_id FROM message_version WHERE text LIKE ?)", (like, like)):
    print(dict(r))
    for v in arc.execute("SELECT ver_token, version, composed_ms, text FROM message_version WHERE message_id = ? ORDER BY version", (r["id"],)):
        print("     version", dict(v))

print("\n== PC export: Events+Messages")
pc = ro(pc_path)
for r in pc.execute("SELECT e.EventID, e.Token, e.TimeStamp, e.Direction, m.Info, m.Body FROM Events e JOIN Messages m ON m.EventID = e.EventID WHERE m.Body LIKE ?", (like,)):
    print({"EventID": r["EventID"], "Token": r["Token"], "ts": r["TimeStamp"], "dir": r["Direction"], "edit": edit_bits(r["Info"])})

print("\n== phone database: messages")
ph = ro(ph_path)
for r in ph.execute("SELECT _id, token, msg_date, send_type, msg_info, body FROM messages WHERE body LIKE ?", (like,)):
    print({"_id": r["_id"], "token": r["token"], "msg_date": r["msg_date"], "send_type": r["send_type"], "edit": edit_bits(r["msg_info"])})
