"""Data folder for the Viber Archive app, which builds the viewer's pages itself from a small database.

    python archive.py viewer-db --archive archive/archive.db --out viewer --emoticons <Viber .emoticons folder>

Writes <out>/viewer.db plus the pictures the pages use: media/ (photos, videos and stickers, named by message id),
emoticons/ and icons/. Copy the whole folder to the phone (or point the desktop app at it). Media files are hard
links to the originals when they are on the same drive, so the folder costs almost no extra space on this computer.

viewer.db holds only what the pages need, already resolved from the full archive: display names, the quoted text of
replies, which photo belongs to which message, the reactions that count, and whether a message is only in the PC
export or only on the phone. The full history (every version, every source record) stays in archive.db.
The app renders the same HTML as the 'html' command, so the two can be compared page by page.
"""
import json
import os
import shutil
import sqlite3
import time
import unicodedata
from pathlib import Path

from . import emoticons, htmlview
from .htmlview import KIND_LABEL, MOVIE_EXT, PICTURE_EXT, _hidden, _t

VIEWER_SCHEMA = 1

DDL = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE chat (
    idx INTEGER PRIMARY KEY,        -- the N in chatN/, chats in the order of the start page
    chat_key TEXT NOT NULL, kind TEXT NOT NULL, name TEXT NOT NULL,
    messages INTEGER NOT NULL, first_ms INTEGER NOT NULL, last_ms INTEGER NOT NULL
);
CREATE TABLE emoticon (name TEXT PRIMARY KEY, file TEXT NOT NULL);   -- pictures in emoticons/
CREATE TABLE message (
    rid INTEGER PRIMARY KEY,        -- display order: chat by chat, then time
    chat INTEGER NOT NULL,
    month TEXT NOT NULL,            -- YYYY-MM in the viewer's time zone
    day TEXT NOT NULL,              -- YYYY-MM-DD
    id TEXT NOT NULL, direction TEXT NOT NULL, author TEXT,
    who TEXT,                       -- sender name shown in group chats
    composed_ms INTEGER NOT NULL, sent_ms INTEGER,
    kind TEXT,                      -- after a photo or video sent as a file is treated as one
    text TEXT, caption TEXT,
    label TEXT,                     -- placeholder text when the media file is missing
    fname TEXT,                     -- the media's original file name
    media TEXT,                     -- address of the file relative to a month page, or NULL
    exact INTEGER,                  -- 1 when the media was matched exactly, 0 when by time
    emoticon TEXT,                  -- the message is just this emoticon
    quote_who TEXT, quote_text TEXT,  -- the message this one replies to (NULL when not a reply)
    tick TEXT, flags TEXT NOT NULL, edited INTEGER NOT NULL,
    react_me INTEGER, react_peer INTEGER,
    hidden INTEGER NOT NULL,        -- a failed send that was redone
    src INTEGER NOT NULL,           -- 1 only in the PC export, 2 only on the phone, 0 otherwise
    sname TEXT, stext TEXT,         -- author and text for search (NULL: not searchable)
    sfold TEXT                      -- stext lower-cased without accents (đ -> d), as the search compares it
);
CREATE INDEX message_days ON message(chat, month, day, hidden, src);
"""


def fold(text):
    """The search's accent-insensitive form: no combining marks, đ as d, lower case (same as the app and app.js)."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not "̀" <= c <= "ͯ")
    return text.replace("đ", "d").replace("Đ", "d").lower()


class Exporter(htmlview.Viewer):  # pylint: disable=too-few-public-methods
    """Reuses the viewer's lookups (names, photos, reactions, sources) and stores their results instead of HTML."""

    def __init__(self, archive_path, out_dir, **options):
        super().__init__(archive_path, out_dir, media_mode="copy", **options)
        self.linked = self.copied = 0

    def _place_media(self, mid):
        """Put the message's media file into <out>/media (hard link when possible); returns its page address."""
        path, confidence = self.photos[mid]
        source = Path(path)
        suffix = source.suffix.lower()
        target = self.out / "media" / f"{mid}{suffix if suffix != '.image' else '.jpg'}"
        if not target.exists():
            try:
                os.link(source, target)
                self.linked += 1
            except OSError:
                shutil.copy2(source, target)
                self.copied += 1
        return "../media/" + target.name, confidence.startswith("exact")

    def _row(self, row, kind_chat):  # pylint: disable=too-many-locals
        (mid, direction, author, composed, sent, kind, text, caption, reply, media, tick, flags, version_count) = row
        who = self.names.get(author, author or "?") if kind_chat == "group" and direction == "in" else None
        quote_who = quote_text = None
        if reply and kind not in ("system", "reaction"):
            try:
                data = json.loads(reply) or {}
            except ValueError:
                data = {}
            data = data if isinstance(data, dict) else {}
            earlier = self.authors.get(str(data.get("token"))) if data.get("token") is not None else None
            quote_text = emoticons.to_emoji(data.get("text") or (earlier[2] if earlier else ""))[:200]
            quote_who = self._quote_author(data.get("token"), kind_chat)
        label = fname = src = exact = emoticon = None
        if kind in ("system", "reaction"):
            pass
        elif kind in KIND_LABEL and kind != "link":
            caption = "" if (caption or "").startswith(("content://", "file://")) else caption
            fname = "" if "://" in (media or "") else (media or "").replace("\\", "/").rsplit("/", 1)[-1]
            suffix = Path(fname).suffix.lower()
            if kind == "file" and suffix in PICTURE_EXT:
                kind = "image"
            elif kind == "file" and suffix in MOVIE_EXT:
                kind = "video"
            label = KIND_LABEL[kind] + (f" ({fname})" if fname and kind == "file" else "")
            if mid in self.photos and Path(self.photos[mid][0]).exists():
                src, exact = self._place_media(mid)
        elif kind == "text":
            emoticon = self.pack.whole(text)
        chips = self.reactions.get(mid, {})
        source = 0
        if self.have_both:
            pcs, phs = mid in self.in_pc, mid in self.in_phone
            source = 1 if pcs and not phs else (2 if phs and not pcs else 0)
        sname = stext = sfold = None
        if not _hidden(row) and row[5] not in ("system", "reaction", "sticker"):
            body = (row[6] if row[5] in ("text", "link") else row[7]) or ""
            if body.strip() and not body.startswith(("content://", "file://")):
                sname = "You" if direction == "out" else self.names.get(author, author or "?")
                stext, sfold = body, fold(body)
        return (row[3], mid, direction, author, who, composed, sent, kind, text, caption, label, fname, src,
                None if exact is None else int(exact), emoticon, quote_who, quote_text, tick, flags or "[]",
                int(version_count > 1), chips.get("me"), chips.get("peer"), int(_hidden(row)), source,
                sname, stext, sfold)

    def export(self):
        """Write viewer.db and the media, emoticon and icon folders. Returns counts."""
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "media").mkdir(exist_ok=True)
        self.pack.publish(self.out / "emoticons")
        if self.icons:
            (self.out / "icons").mkdir(exist_ok=True)
            for role, path in self.icons.items():
                shutil.copy2(path, self.out / "icons" / f"{role}.png")
        final = self.out / "viewer.db"
        temp = self.out / "viewer.db.part"
        temp.unlink(missing_ok=True)
        db = sqlite3.connect(temp)
        db.executescript(DDL)
        meta = {"schema": VIEWER_SCHEMA, "stamp": int(time.time()), "bubble_time": self.bubble_time,
                "have_both": int(self.have_both), "icons": json.dumps(list(self.icons)),
                "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        db.executemany("INSERT INTO meta VALUES (?, ?)", [(k, str(v)) for k, v in meta.items()])
        db.executemany("INSERT INTO emoticon VALUES (?, ?)",
                       [(name, emoticons.slug(name) + ".png") for name in self.pack.files])
        chats = self.arc.execute(
            "SELECT c.chat_key, c.kind, c.title, count(m.id), min(m.composed_ms), max(m.composed_ms) FROM chat c"
            " JOIN message m ON m.chat_key = c.chat_key GROUP BY c.chat_key ORDER BY 4 DESC").fetchall()
        total = 0
        for index, (key, kind, title, count, first, last) in enumerate(chats, 1):
            db.execute("INSERT INTO chat VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (index, key, kind, self.chat_name(key, kind, title), count, first, last))
            rows = self.arc.execute(
                "SELECT id, direction, author, composed_ms, sent_ms, kind, text, caption, reply_json, media_path,"
                " tick, flags, version_count FROM message WHERE chat_key = ? ORDER BY composed_ms, sort_order, seq,"
                " id", (key,)).fetchall()
            needed = set()
            for row in rows:
                if row[8]:
                    try:
                        token = (json.loads(row[8]) or {}).get("token")
                    except (ValueError, AttributeError):
                        token = None
                    if token is not None:
                        needed.add(str(token))
            self.authors = {t: (d, a, x[:200] if t in needed else "") for t, d, a, x in self.arc.execute(
                "SELECT token, direction, author, text FROM message WHERE chat_key = ? AND token IS NOT NULL", (key,))}
            out = []
            for row in rows:
                values = self._row(row, kind)
                out.append((index, _t(values[0], "%Y-%m"), _t(values[0], "%Y-%m-%d")) + values[1:])
            db.executemany("INSERT INTO message (chat, month, day, id, direction, author, who, composed_ms, sent_ms,"
                           " kind, text, caption, label, fname, media, exact, emoticon, quote_who, quote_text, tick,"
                           " flags, edited, react_me, react_peer, hidden, src, sname, stext, sfold)"
                           " VALUES (" + ", ".join("?" * 29) + ")", out)
            total += len(rows)
        db.commit()
        db.execute("ANALYZE")
        db.commit()
        db.close()
        self.arc.close()
        os.replace(temp, final)
        return {"chats": len(chats), "messages": total, "media_linked": self.linked, "media_copied": self.copied,
                "emoticons": len(self.pack.files), "icons": len(self.icons),
                "size_mb": round(final.stat().st_size / 1048576, 1)}


def build(archive_path, out_dir, **options):
    """Write the app's data folder; returns the counts."""
    return Exporter(archive_path, out_dir, **options).export()
