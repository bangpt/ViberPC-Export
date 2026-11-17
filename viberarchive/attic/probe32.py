"""Which files exist ONLY in the folders I plan to retire? Reads inventory.csv written by probe31 (no hashing, no changes).

Run from d:\\Projects\\Viber\\ViberPC-Export:   python probe32.py
"""
import collections
import csv
import sys
from pathlib import Path

KEEP = [r"d:\projects\viber\viberpcexport\media", r"d:\viberrecovery\files\files", r"d:\projects\viber\inbox\phone_media"]
RETIRE = [r"d:\projects\viber\viberphone\com.viber.voip", r"d:\projects\viber\viberphone\viberpictures",
          r"d:\projects\viber\viberphone\vibermovies", r"d:\projects\viber\viberphone\viber messages"]
LOOK = [r"d:\viberrecovery\databasecopy", r"d:\projects\viber\appbackup", r"d:\projects\viber\viberphone\viber messages",
        r"d:\projects\viber\viberpcexport", r"d:\projects\viber\viberpc-export\export",
        r"d:\projects\viber\viberpc-export\attic"]


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.0f} {unit}" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024


def norm(path):
    return path.replace("/", "\\").lower()


def under(path, prefix):
    return path == prefix or path.startswith(prefix + "\\")


def main():
    csv_path = Path(sys.argv[1] if len(sys.argv) > 1 else "inventory.csv")
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows.append((row["path"], norm(row["path"]), int(row["size"]), row["sha256"]))
    keep_index = {(size, digest) for _, low, size, digest in rows if digest and any(under(low, k) for k in KEEP)}
    print(f"{len(rows):,} files read; {len(keep_index):,} distinct hashed files in the folders I keep\n")

    for folder in RETIRE:
        mine = [r for r in rows if under(r[1], folder)]
        if not mine:
            print(f"== {folder}: nothing found\n")
            continue
        twin = [r for r in mine if r[3] and (r[2], r[3]) in keep_index]
        solo = [r for r in mine if not (r[3] and (r[2], r[3]) in keep_index)]
        print(f"== {folder}\n   {len(mine):,} files, {human(sum(r[2] for r in mine))}; "
              f"{len(twin):,} have an identical copy in the folders I keep; "
              f"{len(solo):,} files ({human(sum(r[2] for r in solo))}) exist only here")
        by_part = collections.defaultdict(lambda: [0, 0])
        for orig, low, size, _ in solo:
            parts = low[len(folder):].strip("\\").split("\\")[:-1][:3]
            key = "\\".join(parts) or "(top)"
            by_part[key][0] += 1
            by_part[key][1] += size
        for key, (count, size) in sorted(by_part.items(), key=lambda kv: -kv[1][1])[:14]:
            print(f"      only here: {human(size):>10}  {count:>6,} files  {key}")
        ext = collections.Counter(Path(r[1]).suffix or "(none)" for r in solo)
        print("      types only here:", ", ".join(f"{e} {n:,}" for e, n in ext.most_common(8)))
        for orig, _, size, _ in sorted(solo, key=lambda r: -r[2])[:6]:
            print(f"      big: {human(size):>10}  {orig}")
        print()

    print("== What is in the folders I could not judge ==")
    for folder in LOOK:
        mine = [r for r in rows if under(r[1], folder)]
        direct = [r for r in mine if "\\" not in r[1][len(folder):].strip("\\")]
        print(f"-- {folder}: {len(mine):,} files, {human(sum(r[2] for r in mine))}")
        for orig, _, size, _ in sorted(direct, key=lambda r: -r[2])[:12]:
            print(f"      {human(size):>10}  {Path(orig).name}")
        subs = collections.Counter(r[1][len(folder):].strip("\\").split("\\")[0] for r in mine
                                   if "\\" in r[1][len(folder):].strip("\\"))
        if subs:
            print("      subfolders:", ", ".join(f"{k} ({n:,})" for k, n in subs.most_common(8)))
    loose = [r for r in rows if r[1].count("\\") == 3 and under(r[1], r"d:\projects\viber")]
    print(f"-- loose files directly in d:\\Projects\\Viber ({len(loose)}):")
    print("      " + ", ".join(Path(r[0]).name for r in sorted(loose, key=lambda r: r[1])))


if __name__ == "__main__":
    main()
