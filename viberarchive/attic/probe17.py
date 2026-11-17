"""Match phone conversations to PC chats by shared message tokens. Read-only, no names or numbers printed.
    python probe17.py phone_messages_db viber_export.db
One line per phone conversation (numbered 1..n in size order): its type, message count, the PC chat it matches
best, how many messages are shared, how many exist only on one side, and how pure the match is."""
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

tz = timezone(timedelta(hours=7))
ph = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
pc = sqlite3.connect(f"file:{sys.argv[2]}?mode=ro", uri=True)


def tk(v):
    return None if v is None or str(v).strip() == "" else str(v).strip()


def ym(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, tz).strftime("%Y-%m")
    except (OverflowError, OSError, ValueError, TypeError):
        return "?"


pc_chat = {}
pc_count = Counter()
for tok, chat in pc.execute("SELECT Token, ChatID FROM Events WHERE Token IS NOT NULL"):
    if tk(tok):
        pc_chat[tk(tok)] = chat
        pc_count[chat] += 1
conv = defaultdict(list)
meta = {r[0]: r[1:] for r in ph.execute("SELECT _id, conversation_type, group_id, deleted, name IS NOT NULL AND name != '' FROM conversations")}
for tok, cid, ms in ph.execute("SELECT token, conversation_id, msg_date FROM messages WHERE token > 0"):
    conv[cid].append((str(tok), ms))
print("phone conversations with messages:", len(conv), "of", len(meta), " | PC chats with events:", len(pc_count))
print("conversations table columns used: type, group_id>0, deleted, has name\n")
print("# | type grp del named | phone msgs | PC chat msgs | shared | phone-only | PC-only | purity | phone first..last")
used = Counter()
for n, (cid, lst) in enumerate(sorted(conv.items(), key=lambda kv: -len(kv[1])), 1):
    votes = Counter(pc_chat[t] for t, _ in lst if t in pc_chat)
    best, hits = (votes.most_common(1) or [(None, 0)])[0]
    shared = hits
    used[best] += 1
    purity = hits / sum(votes.values()) if votes else 0
    mt = meta.get(cid, ("?", "?", "?", "?"))
    first = min(m for _, m in lst)
    last = max(m for _, m in lst)
    print(f"{n} | {mt[0]} {'Y' if mt[1] else 'n'} {mt[2]} {'Y' if mt[3] else 'n'} | {len(lst)} | {pc_count.get(best, 0)} | {shared} | "
          f"{len(lst) - sum(votes.values())} | {pc_count.get(best, 0) - shared} | {purity:.3f} | {ym(first)}..{ym(last)}")
print("\nPC chats not matched by any phone conversation:",
      [(c, pc_count[c]) for c in pc_count if c not in used])
print("PC chats matched by more than one phone conversation:", [c for c, k in used.items() if k > 1 and c is not None])
print("phone conversations with no PC match at all:", used.get(None, 0))
