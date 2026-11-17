#!/usr/bin/env python3
"""Incremental, append-only copy of Viber media from an Android phone over adb.

    python viber_phone_sync.py status --mirror D:\\Projects\\Viber\\inbox\\phone_media
    python viber_phone_sync.py pull   --mirror D:\\Projects\\Viber\\inbox\\phone_media

Needs Android platform-tools (adb) on PATH, USB debugging on, and the phone
authorised for this computer (`adb devices` must say "device").

Rules
  * Files are only ever added. Nothing local is overwritten or deleted.
  * A file counts as "already copied" when its remote path, size and modified
    time match a row in <mirror>/manifest.csv.
  * A remote file that changed since it was copied is pulled into
    <mirror>/_changed/<UTC stamp>/ instead of replacing the earlier copy.
  * A file that already exists locally under the expected name with the same
    size is adopted into the manifest without pulling it again.
  * Folders named cache and video_samples are skipped (pass --include-cache to copy them).
  * Hidden files and folders (names starting with ".") are skipped, except the
    folders where Viber keeps older media: .image and .video. Their thumbnails
    (.thumbnails) are copied only with --thumbnails. Pass --include-hidden to
    copy every hidden path.
  * Safe to interrupt: run `pull` again and it carries on.

Other options
  --root LABEL=/remote/path   replace the default roots (repeat for several)
  --limit N                   pull at most N files (use it for a first trial)
  --thumbnails                also copy the .thumbnails folder
  --jobs N                    parallel adb pulls (default 4)
  --serial ID                 pick a device when more than one is connected
  --adb PATH                  adb executable if it is not on PATH
"""
import argparse
import csv
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOTS = {
    "com.viber.voip": "/sdcard/Android/data/com.viber.voip",
    "ViberPictures": "/sdcard/Pictures/Viber",
    "ViberMovies": "/sdcard/Movies/Viber",
}
KEEP_HIDDEN = {".image", ".video"}
SKIP_DIRS = {"cache", "video_samples"}
FIELDS = ["label", "remote_path", "size", "mtime", "local_path", "pulled_at_utc"]


def run_adb(opts, args):
    cmd = [opts.adb] + (["-s", opts.serial] if opts.serial else []) + args
    try:
        return subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError:
        sys.exit("adb was not found. Install Android platform-tools and add it to "
                 "PATH, or pass --adb <full path to adb>.")


def text(raw):
    return raw.decode("utf-8", "replace").replace("\r", "")


def check_device(opts):
    out = text(run_adb(opts, ["devices"]).stdout)
    rows = [ln.split("\t") for ln in out.splitlines()[1:] if "\t" in ln]
    ready = [r[0] for r in rows if r[1].strip() == "device"]
    if not ready:
        sys.exit("No usable phone found. `adb devices` says:\n" + out +
                 "\nUnlock the phone, accept the 'Allow USB debugging' prompt and retry.")
    if len(ready) > 1 and not opts.serial:
        sys.exit("More than one device is connected; pass --serial. Found: " + ", ".join(ready))


def list_remote(opts, root):
    """Return [(remote_path, size, mtime_epoch)] or None if the folder is absent."""
    probe = text(run_adb(opts, ["exec-out", f"test -d '{root}' && echo YES || echo NO"]).stdout)
    if probe.strip() != "YES":
        return None
    sh = f"find '{root}' -type f -exec stat -c '%s|%Y|%n' {{}} +"
    res = run_adb(opts, ["exec-out", sh])
    files, bad = [], 0
    for line in text(res.stdout).split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].startswith(root):
            files.append((parts[2], int(parts[0]), int(parts[1])))
        else:
            bad += 1
    if bad and not files:
        sys.exit(f"Could not read the file list for {root}.\n" +
                 text(res.stderr or res.stdout)[:500] +
                 "\nTry:  adb shell ls -lR " + root + " | more   and tell me what it prints.")
    return files


def load_manifest(path):
    done, paths = set(), set()
    if path.exists():
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                done.add((row["remote_path"], int(row["size"]), int(row["mtime"])))
                paths.add(row["remote_path"])
    return done, paths


def day(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%d")


def mb(n):
    return f"{n / 1_048_576:,.1f} MB"


def skip_hidden(opts, parts):
    """True when the path sits under a hidden folder (or is a hidden file) that is not wanted."""
    if not opts.include_cache and any(p in SKIP_DIRS for p in parts[:-1]):
        return True
    if opts.include_hidden:
        return False
    for part in parts:
        if not part.startswith("."):
            continue
        if part == ".thumbnails":
            return not opts.thumbnails
        if part in KEEP_HIDDEN:
            continue
        return True
    return False


def build_plan(opts, mirror):
    done, known = load_manifest(mirror / "manifest.csv")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    plan, adopt, report = [], [], []
    seen_remote = set()
    for label, root in opts.roots.items():
        files = list_remote(opts, root)
        if files is None:
            report.append({"label": label, "root": root, "missing": True})
            continue
        total = Counter()
        subs = Counter()
        oldest = newest = None
        n_new = b_new = n_adopt = 0
        for remote, size, mtime in files:
            rel = remote[len(root):].lstrip("/")
            if skip_hidden(opts, rel.split("/")):
                continue
            seen_remote.add(remote)
            total["files"] += 1
            total["bytes"] += size
            parts = rel.split("/")
            subs["/".join(parts[:-1][:2]) if len(parts) > 1 else "(top level)"] += 1
            oldest = mtime if oldest is None else min(oldest, mtime)
            newest = mtime if newest is None else max(newest, mtime)
            if (remote, size, mtime) in done:
                continue
            if remote in known:
                local = mirror / "_changed" / stamp / label / Path(*rel.split("/"))
            else:
                local = mirror / label / Path(*rel.split("/"))
                if local.exists() and local.stat().st_size == size:
                    adopt.append((label, remote, size, mtime, local))
                    n_adopt += 1
                    continue
            plan.append((label, remote, size, mtime, local))
            n_new += 1
            b_new += size
        report.append({"label": label, "root": root, "missing": False,
                       "files": total["files"], "bytes": total["bytes"],
                       "oldest": oldest, "newest": newest, "subs": subs,
                       "new": n_new, "new_bytes": b_new, "adopt": n_adopt})
    gone = len([p for p in known if p not in seen_remote])
    return plan, adopt, report, gone


def print_report(report, gone):
    for r in report:
        print(f"\n[{r['label']}]  {r['root']}")
        if r["missing"]:
            print("   NOT FOUND on the phone. Look for the real folder with:\n"
                  "   adb shell ls /sdcard /sdcard/Android/data\n"
                  "   then pass  --root " + r["label"] + "=/the/real/path")
            continue
        print(f"   {r['files']:,} files, {mb(r['bytes'])}, modified {day(r['oldest'])} to {day(r['newest'])}"
              if r["files"] else "   empty")
        for name, n in r["subs"].most_common(8):
            print(f"      {name}: {n:,} files")
        print(f"   to pull: {r['new']:,} files ({mb(r['new_bytes'])}); "
              f"already present locally (size match): {r['adopt']:,}")
    if gone:
        print(f"\n{gone:,} files in the manifest are no longer on the phone. "
              "They stay in your mirror.")


def do_pull(opts, mirror, plan, adopt):
    mirror.mkdir(parents=True, exist_ok=True)
    manifest = mirror / "manifest.csv"
    fresh = not manifest.exists()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    pulled = failed = 0
    failures = []

    def work(item):
        label, remote, size, mtime, local = item
        local.parent.mkdir(parents=True, exist_ok=True)
        res = run_adb(opts, ["pull", "-a", remote, str(local)])
        good = res.returncode == 0 and local.exists() and local.stat().st_size == size
        return item, good, text(res.stderr).strip()

    with open(manifest, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, FIELDS)
        if fresh:
            writer.writeheader()
        for label, remote, size, mtime, local in adopt:
            writer.writerow({"label": label, "remote_path": remote, "size": size, "mtime": mtime,
                             "local_path": str(local), "pulled_at_utc": "adopted " + stamp})
        with ThreadPoolExecutor(max_workers=opts.jobs) as pool:
            for n, (item, good, err) in enumerate(pool.map(work, plan), 1):
                label, remote, size, mtime, local = item
                if good:
                    writer.writerow({"label": label, "remote_path": remote, "size": size,
                                     "mtime": mtime, "local_path": str(local),
                                     "pulled_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})
                    fh.flush()
                    pulled += 1
                else:
                    failed += 1
                    failures.append((remote, err[:120]))
                if n % 200 == 0 or n == len(plan):
                    print(f"   {n:,}/{len(plan):,} done ({failed} failed)")
    print(f"\nPulled {pulled:,}, adopted {len(adopt):,}, failed {failed:,}.")
    for remote, err in failures[:10]:
        print("   FAILED:", remote, "|", err)
    if failures:
        print("Run `pull` again; failed files are retried.")
    else:
        print("Run `status`: it should now report 0 files to pull.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "pull"])
    ap.add_argument("--mirror", required=True, help="local folder that holds the media copy and manifest.csv")
    ap.add_argument("--root", action="append", metavar="LABEL=/remote/path")
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--serial")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--include-hidden", action="store_true")
    ap.add_argument("--thumbnails", action="store_true")
    ap.add_argument("--include-cache", action="store_true")
    opts = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    opts.roots = dict(DEFAULT_ROOTS)
    if opts.root:
        opts.roots = {}
        for item in opts.root:
            label, _, path = item.partition("=")
            if not label or not path.startswith("/"):
                sys.exit(f"--root needs LABEL=/absolute/remote/path, got: {item}")
            opts.roots[label] = path.rstrip("/")
    mirror = Path(opts.mirror)
    check_device(opts)
    plan, adopt, report, gone = build_plan(opts, mirror)
    print_report(report, gone)
    if opts.command == "status":
        return
    if opts.limit is not None:
        plan = plan[:opts.limit]
    if not plan and not adopt:
        print("\nNothing new to pull.")
        return
    print(f"\nPulling {len(plan):,} files, adopting {len(adopt):,} ...")
    do_pull(opts, mirror, plan, adopt)


if __name__ == "__main__":
    main()
