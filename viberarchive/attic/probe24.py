"""Which emoticon-only messages exist, and where does Viber keep its emoticon pictures? Read-only."""
import os, re, sqlite3, sys
from collections import Counter

db = sys.argv[1] if len(sys.argv) > 1 else r"archive\archive.db"
arc = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
pat = re.compile(r"^(\(\w+\)|[:;=8B][-']?[)(DPpOo|*/\\]|<3)$")
count = Counter(t.strip() for (t,) in arc.execute("SELECT text FROM message WHERE kind='text' AND length(text) <= 12")
                if t and pat.match(t.strip()))
print("emoticon-only messages (text: count):")
for text, n in count.most_common(40):
    print(f"  {text:<14}{n:>6}")
roots = [os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", ""),
         r"C:\Program Files\Viber", r"C:\Program Files (x86)\Viber", os.path.expanduser(r"~\AppData\Local\Viber")]
print("\nPNG/SVG/WEBP files whose path mentions viber and smiley/teeth/emoticon/emoji:")
seen = 0
for root in filter(os.path.isdir, roots):
    for base, _, names in os.walk(root):
        if "viber" not in base.lower():
            continue
        for name in names:
            low = (base + name).lower()
            if name.lower().endswith((".png", ".svg", ".webp", ".gif")) and re.search(r"smil|teeth|emoti|emoji", low):
                print("  ", os.path.join(base, name))
                seen += 1
                if seen >= 60:
                    sys.exit()
print("\nfound:", seen)
