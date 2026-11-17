"""How do phone columns map to PC columns? Read-only; prints counts of code values only, no text.
    python probe18.py phone_messages_db viber_export.db
Uses the messages that exist in both, to learn which phone values correspond to PC Event.Type,
Message.Type and Message.Status (the tick)."""
import json
import sqlite3
import sys
from collections import Counter

ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)


def tk(v):
    return None if v is None or str(v).strip() == "" else str(v).strip()


def has(info, key):
    try:
        return key in json.loads(info)
    except (TypeError, ValueError):
        return False


P = {}
for tok, et, mt, st, d, body, sticker, payload, dur in pc.execute(
        "SELECT e.Token, e.Type, m.Type, m.Status, e.Direction, m.Body, m.StickerID, m.PayloadPath, m.Duration "
        "FROM Events e LEFT JOIN Messages m ON m.EventID = e.EventID WHERE e.Token IS NOT NULL"):
    if tk(tok):
        P[tk(tok)] = (et, mt, st, d, bool(tk(body)), bool(sticker) and str(sticker) != "0", bool(tk(payload)), dur)
H = {}
for tok, mime, flag, st, xst, rmt, uri, dur, stk, info, body, xflags in ph.execute(
        "SELECT token, extra_mime, flag, status, extra_status, read_message_time, extra_uri, extra_duration, "
        "sticker_id, msg_info, body, extra_flags FROM messages WHERE token > 0"):
    H[str(tok)] = (mime, flag, st, xst, rmt, bool(uri), dur, bool(stk) and str(stk) != "0", info, bool(body), xflags)
S = [t for t in H if t in P]
print("shared:", len(S))

print("\n== PC (Event.Type, Message.Type) -> phone extra_mime   [rows]")
for k, n in sorted(Counter((P[t][0], P[t][1], H[t][0]) for t in S).items(), key=lambda x: -x[1])[:30]:
    print(n, k)

print("\n== PC Event.Type -> phone has 1on1reactions in msg_info / body filled")
print(sorted(Counter((P[t][0], has(H[t][8], "1on1reactions"), H[t][9]) for t in S).items()))

print("\n== PC Event.Type 3 (reaction) vs 0 (content): phone flag top values")
for et in (0, 3):
    print(et, Counter(H[t][1] for t in S if P[t][0] == et).most_common(8))
    print(et, "extra_flags", Counter(H[t][10] for t in S if P[t][0] == et).most_common(6))

print("\n== PC Message.Status (outgoing, content) -> phone (status, extra_status, read_message_time>0)")
for k, n in sorted(Counter((P[t][2], H[t][2], H[t][3], (H[t][4] or 0) > 1) for t in S
                           if P[t][0] == 0 and P[t][3] == 1).items(), key=lambda x: -x[1])[:15]:
    print(n, k)
print("PC Message.Status (incoming, content) -> phone (status, extra_status):")
for k, n in sorted(Counter((P[t][2], H[t][2], H[t][3]) for t in S
                           if P[t][0] == 0 and P[t][3] == 0).items(), key=lambda x: -x[1])[:8]:
    print(n, k)

print("\n== media: PC has payload path vs phone has extra_uri; sticker agreement")
print(sorted(Counter((P[t][6], H[t][5]) for t in S if P[t][0] == 0).items()))
print(sorted(Counter((P[t][5], H[t][7]) for t in S if P[t][0] == 0).items()))
print("duration present PC vs phone:", sorted(Counter((bool(P[t][7]), bool(H[t][6])) for t in S if P[t][0] == 0).items()))
print("\n== the 3 standalone PC events and PC-only Type 0 after 2022: Message.Type counts")
print(Counter(P[t][1] for t in P if t not in H and P[t][0] == 0).most_common(8))
