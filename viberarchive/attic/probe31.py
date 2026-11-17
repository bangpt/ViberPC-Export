"""Read-only inventory of the Viber folders: sizes, duplicates (by content), key files, and where the archive's links point.

Run from d:\\Projects\\Viber\\ViberPC-Export:
    python probe31.py                       (scans d:\\Projects\\Viber and D:\\ViberRecovery)
    python probe31.py "E:\\other" ...       (scan these folders instead)
    python probe31.py --no-hash             (sizes only, much faster)
Nothing is changed. It writes inventory.csv (path, size, modified, sha256) beside this script.
"""
import collections
import csv
import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

DEFAULT_ROOTS = [r"d:\Projects\Viber", r"D:\ViberRecovery"]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}
KEY_NAMES = {"viber_export.db", "viber_messages", "archive.db", "manifest.csv", "media_index.csv", "viber_export.db-wal",
             "viber_messages-wal", "archive.db-wal"}


def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024


def walk(root):
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            path = Path(folder) / name
            try:
                st = path.stat()
            except OSError:
                continue
            yield path, st.st_size, st.st_mtime


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_hash = "--no-hash" not in sys.argv
    roots = [Path(r) for r in (args or DEFAULT_ROOTS) if Path(r).exists()]
    for missing in [r for r in (args or DEFAULT_ROOTS) if not Path(r).exists()]:
        print("not found, skipped:", missing)
    files = []
    for root in roots:
        print("scanning", root, "...", flush=True)
        files += [(root, p, s, m) for p, s, m in walk(root)]
    print(f"{len(files):,} files, {human(sum(f[2] for f in files))} in total\n")

    print("== Size by folder (two levels down) ==")
    table = collections.defaultdict(lambda: [0, 0])
    for root, path, size, _ in files:
        parts = path.relative_to(root).parts[:-1][:2]
        key = str(root / Path(*parts)) if parts else str(root) + "  (files directly here)"
        table[key][0] += 1
        table[key][1] += size
    for key, (count, size) in sorted(table.items(), key=lambda kv: -kv[1][1])[:40]:
        print(f"  {human(size):>10}  {count:>8,} files  {key}")

    print("\n== Key files ==")
    for _, path, size, mtime in sorted(files, key=lambda f: str(f[1])):
        if path.name in KEY_NAMES:
            print(f"  {human(size):>10}  {time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime))}  {path}")

    hashes = {}
    if do_hash:
        by_size = collections.defaultdict(list)
        for _, path, size, _ in files:
            if size:
                by_size[size].append(path)
        todo = [p for group in by_size.values() if len(group) > 1 for p in group]
        print(f"\nhashing {len(todo):,} files that share a size with another file ...", flush=True)
        for number, path in enumerate(todo, 1):
            try:
                hashes[path] = sha256(path)
            except OSError:
                pass
            if number % 2000 == 0:
                print(f"  {number:,} / {len(todo):,}", flush=True)
        groups = collections.defaultdict(list)
        sizes = {p: s for _, p, s, _ in files}
        for path, digest in hashes.items():
            groups[(sizes[path], digest)].append(path)
        dupes = {k: v for k, v in groups.items() if len(v) > 1}
        wasted = sum(k[0] * (len(v) - 1) for k, v in dupes.items())
        print(f"\n== Duplicates (identical content) ==\n  {len(dupes):,} sets, {human(wasted)} would be freed by keeping one copy of each")
        pairs = collections.Counter()
        for (size, _), paths in dupes.items():
            tops = sorted({str(next((r / Path(*p.relative_to(r).parts[:1]) for r in roots if r in p.parents), p.parent))
                           for p in paths})
            pairs[tuple(tops)] += size * (len(paths) - 1)
        print("  folders sharing copies (bytes that are duplicated):")
        for tops, size in pairs.most_common(15):
            print(f"    {human(size):>10}  " + "  <->  ".join(tops))
        print("  biggest duplicated files:")
        for (size, _), paths in sorted(dupes.items(), key=lambda kv: -kv[0][0] * (len(kv[1]) - 1))[:12]:
            print(f"    {human(size):>10} x{len(paths)}  " + "  |  ".join(str(p) for p in paths[:3]))

    print("\n== Where the archive's links point ==")
    for _, path, _, _ in files:
        if path.name == "archive.db":
            try:
                con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
                print(" ", path)
                prefix = collections.Counter(
                    "/".join(Path(p).parts[:4]) for (p,) in con.execute("SELECT original_path FROM message_media"))
                for pre, n in prefix.most_common(8):
                    print(f"    {n:>6,} photo links under {pre}")
                for row in con.execute("SELECT id, source, label, path FROM source_snapshot"):
                    print("    snapshot", row)
                con.close()
            except sqlite3.Error as error:
                print("   could not read", path, error)

    out = Path(__file__).with_name("inventory.csv")
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["path", "size", "modified", "sha256"])
        for _, path, size, mtime in files:
            writer.writerow([path, size, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)), hashes.get(path, "")])
    print(f"\nwrote {out}. Paste everything above (the printed part) back to Claude.")


if __name__ == "__main__":
    main()
