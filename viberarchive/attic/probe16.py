"""Third phone/PC comparison. Read-only, prints counts only (no text, names or numbers from messages).
    python probe16.py phone_messages_db viber_export.db
Answers: (1) is send_type the same as the PC Direction? (2) are the 'phone-only' and 'PC-only' messages the
same messages under different tokens? (3) what do the PC reaction rows look like in the phone table?"""
import re
import sqlite3
import sys
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=7))
ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)


def tk(v):
    return None if v is None or str(v).strip() == "" else str(v).strip()


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def yr(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, tz).strftime("%Y")
    except (OverflowError, OSError, ValueError, TypeError):
        return "?"


P = {}
for tok, typ, ts, d, body in pc.execute(
        "SELECT e.Token, e.Type, e.TimeStamp, e.Direction, m.Body FROM Events e "
        "LEFT JOIN Messages m ON m.EventID = e.EventID WHERE e.Token IS NOT NULL"):
    if tk(tok):
        P[tk(tok)] = (typ, ts, d, norm(body))
H = {}
for tok, ms, st, mime, flag, lk, body in ph.execute(
        "SELECT token, msg_date, send_type, extra_mime, flag, likes_count, body FROM messages WHERE token > 0"):
    H[str(tok)] = (ms, st, mime, flag, lk, norm(body))

print("== (1) phone send_type vs PC Direction, on shared tokens (content rows)")
print(sorted(Counter((H[t][1], P[t][2]) for t in H if t in P and P[t][0] == 0).items()))

print("\n== (2) are phone-only and PC-only the same messages under different tokens?")
pc_only = [(t, v) for t, v in P.items() if t not in H and v[0] == 0]
ph_only = [(t, v) for t, v in H.items() if t not in P]
print("PC-only content rows:", len(pc_only), " phone-only rows:", len(ph_only))
idx = defaultdict(list)
for t, (typ, ts, d, body) in pc_only:
    idx[(d, body)].append((ts, t))
for k in idx:
    idx[k].sort()
for window in (10, 120, 3600):
    used = set()
    pairs, diffs, tokdiff = Counter(), Counter(), Counter()
    for t, (ms, st, mime, flag, lk, body) in sorted(ph_only, key=lambda x: x[1][0]):
        if not body:
            continue
        lst = idx.get((st, body))
        if not lst:
            continue
        i = bisect_left(lst, (ms, ""))
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(lst) and lst[j][1] not in used:
                dt = abs(lst[j][0] - ms) / 1000
                if dt <= window and (best is None or dt < best[0]):
                    best = (dt, lst[j][1], j)
        if best:
            used.add(best[1])
            pairs[yr(ms)] += 1
            diffs[round(best[0])] += 1
            tokdiff[int(t) - int(best[1])] += 1
    print(f"window {window}s: paired {sum(pairs.values())}, by year {sorted(pairs.items())}")
    print("   time gap seconds (top 6):", diffs.most_common(6), " token difference (top 4):", tokdiff.most_common(4))
    print("   still PC-only:", len(pc_only) - len(used))

print("\n== (3) PC reaction rows (Type 3) as they appear in the phone table")
rx = [t for t, v in P.items() if v[0] == 3 and t in H]
print("PC reaction rows found in phone:", len(rx))
print("(body empty?, extra_mime, send_type, likes_count) top 6:",
      Counter((H[t][5] == "", H[t][2], H[t][1], H[t][4]) for t in rx).most_common(6))
print("flag values (top 6):", Counter(H[t][3] for t in rx).most_common(6))
print("PC Direction vs phone send_type:", sorted(Counter((P[t][2], H[t][1]) for t in rx).items()))
