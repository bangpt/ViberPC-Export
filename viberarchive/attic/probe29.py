"""Which messages still have no file? Run from the ViberPC-Export folder: python probe29.py"""
import sqlite3, collections, datetime
con = sqlite3.connect("archive/archive.db")
rows = con.execute("""SELECT id, kind, sticker_id, COALESCE(sent_ms, composed_ms), source FROM message
  WHERE kind IN ('image','video','sticker') AND id NOT IN (SELECT message_id FROM message_media)""").fetchall()
print("unlinked by kind:", collections.Counter(r[1] for r in rows))
print("unlinked by source:", collections.Counter((r[1], (r[4] or "")[:5]) for r in rows))
st = [r for r in rows if r[1] == "sticker"]
print("unlinked stickers with id:", sum(1 for r in st if r[2]), "without id:", sum(1 for r in st if not r[2]))
ids = collections.Counter(r[2] for r in st if r[2])
print("distinct missing sticker ids:", len(ids))
for sid, n in ids.most_common(40):
    print("  ", sid, n)
print("linked stickers by confidence:", con.execute("""SELECT mm.confidence, count(*) FROM message_media mm
  JOIN message m ON m.id = mm.message_id WHERE m.kind='sticker' GROUP BY 1""").fetchall())
for r in rows:
    if r[1] != "sticker":
        print("unlinked", r[1], datetime.datetime.utcfromtimestamp(r[3] / 1000 + 25200), r[4])
