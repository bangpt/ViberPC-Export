"""Link photos and videos to archive messages (never changes messages; only fills message_media).

    python archive.py link-media --archive archive/archive.db --pc-index ..\\ViberPCExport\\media_index.csv \\
        --phone-manifest d:\\Projects\\Viber\\inbox\\phone_media\\manifest.csv

Kinds of link, each with a confidence:
  exact_sticker_id  the sticker's id is the file name in a Viber .stickers pack folder (--stickers).
  exact_event   the PC export saved this file for exactly this message (media_index.csv EventID).
  exact_id      the phone message names a download id that is part of a PC media file name.
  time_match    a file copied from the phone whose modified time is within a few seconds after the message
                (one file per message, closest first). Good but not proof.
"""
import bisect
import csv
import re
from pathlib import Path

from . import schema

HEX_RE = re.compile(r"[0-9a-f]{64}")
MEDIA_KINDS = ("image", "video")
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".image", ".bmp", ".heic"}
VIDEO_EXT = {".mp4", ".mov", ".3gp", ".mkv", ".video", ".webm"}
WINDOW_BEFORE_S = 3      # file time may be this much before the message time
WINDOW_AFTER_S = 10      # ... or this much after it (typical offset is +1 to +3)
TYPICAL_OFFSET_S = 2


def _resolve(raw, base):
    path = Path(raw)
    if path.is_absolute() and path.exists():
        return path
    candidate = base / raw
    return candidate if candidate.exists() else (path if path.exists() else None)


def _pc_links(arc, index_csv):
    """(message_id, path, confidence) from the PC media index, plus a hex-id lookup for phone-only messages."""
    base = Path(index_csv).parent
    snap = arc.execute("SELECT id FROM source_snapshot WHERE source LIKE 'pc-%' ORDER BY id LIMIT 1").fetchone()
    by_event = {}
    if snap:
        for mid, event_id in arc.execute(
                "SELECT entity_id, local_event_id FROM source_record WHERE entity = 'message' AND snapshot_id = ?",
                (snap[0],)):
            by_event[event_id] = mid
    links, by_hex = [], {}
    with open(index_csv, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            saved = row.get("saved_path") or ""
            if not saved or row.get("kind") not in MEDIA_KINDS + ("sticker",):
                continue
            path = _resolve(saved, base)
            if path is None:
                continue
            quality = "exact_event" if row.get("status") in ("original", "sticker") else "exact_event_thumb"
            mid = by_event.get(int(row["EventID"]))
            if mid:
                links.append((mid, str(path), quality))
            found = HEX_RE.search(saved) or HEX_RE.search(row.get("orig_path") or "")
            if found and row.get("status") == "original":
                by_hex.setdefault(found.group(0), str(path))
    return links, by_hex


def _phone_files(manifest):
    base = Path(manifest).parent
    by_name = {}
    files = []
    with open(manifest, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        suffix = Path(row["remote_path"]).suffix.lower()
        if suffix not in IMAGE_EXT and suffix not in VIDEO_EXT:
            continue
        path = _resolve(row["local_path"], base)
        if path is None:
            if not by_name:
                by_name = {p.name: p for p in base.rglob("*") if p.is_file()}
            path = by_name.get(Path(row["local_path"].replace("\\", "/")).name)
        if path is not None:
            files.append((int(row["mtime"]), str(path), suffix in VIDEO_EXT))
    return files


def link_pairs(messages, files):
    """Greedy one-to-one pairing by closeness to the typical offset; returns [(message_id, path, delta)]."""
    candidates = []
    stamps = [f[0] for f in files]
    order = sorted(range(len(files)), key=lambda i: stamps[i])
    sorted_stamps = [stamps[i] for i in order]
    for mid, kind, seconds in messages:
        low = bisect.bisect_left(sorted_stamps, seconds - WINDOW_BEFORE_S)
        high = bisect.bisect_right(sorted_stamps, seconds + WINDOW_AFTER_S)
        for pos in range(low, high):
            idx = order[pos]
            if files[idx][2] != (kind == "video"):
                continue
            delta = sorted_stamps[pos] - seconds
            candidates.append((abs(delta - TYPICAL_OFFSET_S), delta, mid, idx))
    candidates.sort()
    used_msg, used_file, pairs = set(), set(), []
    for _, delta, mid, idx in candidates:
        if mid in used_msg or idx in used_file:
            continue
        used_msg.add(mid)
        used_file.add(idx)
        pairs.append((mid, files[idx][1], delta))
    return pairs


STICKER_FILE_RE = re.compile(r"^(?:r\d+_)?0*(\d+)(?:_orig)?\.png$")


def _sticker_files(folder):
    """{sticker id: path} from a Viber .stickers folder (pack folders holding files like r144_00154500_orig.png)."""
    found = {}
    for path in Path(folder).rglob("*.png"):
        match = STICKER_FILE_RE.match(path.name)
        if match:
            found.setdefault(int(match.group(1)), str(path))
    return found


def link_media(archive_path, pc_index=None, phone_manifest=None, stickers=None):
    """Fill message_media; returns counts. Safe to run again (existing links are kept)."""
    arc = schema.connect(archive_path)
    stats = {"exact_event": 0, "exact_event_thumb": 0, "exact_id": 0, "time_match": 0, "photo_video_messages": 0}
    arc.execute("DELETE FROM message_media")
    insert = ("INSERT OR IGNORE INTO message_media (message_id, sha256, original_path, confidence)"
              " VALUES (?, NULL, ?, ?)")
    linked = set()
    by_hex = {}
    if pc_index:
        links, by_hex = _pc_links(arc, pc_index)
        for mid, path, quality in links:
            arc.execute(insert, (mid, path, quality))
            stats[quality] += 1
            linked.add(mid)
    rows = arc.execute("SELECT id, kind, media_path, COALESCE(sent_ms, composed_ms) FROM message"
                       " WHERE kind IN ('image', 'video')").fetchall()
    stats["photo_video_messages"] = len(rows)
    for mid, _, media_path, _ in rows:
        found = HEX_RE.search(media_path or "")
        if mid not in linked and found and found.group(0) in by_hex:
            arc.execute(insert, (mid, by_hex[found.group(0)], "exact_id"))
            stats["exact_id"] += 1
            linked.add(mid)
    if stickers:
        by_id = _sticker_files(stickers)
        stats["exact_sticker_id"] = 0
        for mid, sid in arc.execute("SELECT id, sticker_id FROM message WHERE kind = 'sticker' AND sticker_id"):
            if mid not in linked and sid in by_id:
                arc.execute(insert, (mid, by_id[sid], "exact_sticker_id"))
                stats["exact_sticker_id"] += 1
                linked.add(mid)
    stats["sticker_messages"] = arc.execute("SELECT count(*) FROM message WHERE kind = 'sticker'").fetchone()[0]
    stats["sticker_without_id"] = arc.execute(
        "SELECT count(*) FROM message WHERE kind = 'sticker' AND sticker_id IS NULL").fetchone()[0]
    if phone_manifest:
        files = _phone_files(phone_manifest)
        todo = [(mid, kind, ms / 1000.0) for mid, kind, _, ms in rows if mid not in linked]
        for mid, path, _ in link_pairs(todo, files):
            arc.execute(insert, (mid, path, "time_match"))
            stats["time_match"] += 1
    arc.commit()
    stats["without_file"] = arc.execute(
        "SELECT count(*) FROM message WHERE kind IN ('image', 'video', 'sticker')"
        " AND id NOT IN (SELECT message_id FROM message_media)").fetchone()[0]
    arc.close()
    return stats
