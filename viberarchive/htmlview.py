"""Static HTML viewer: one page per chat and month, in the look of the Viber app, for comparing with the real thing.

    python archive.py html --archive archive/archive.db --out site

Writes site/index.html (chats, and a month grid per chat), site/<chat>/<YYYY-MM>.html, style.css and app.js. Nothing is
loaded from the network; open index.html in a browser. Media is not embedded: a photo, video or file shows as a labelled
placeholder with its caption and original file name.
"""
import html
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import emoticons, schema

TZ = timezone(timedelta(hours=7))
REACTIONS = {1: "❤️", 2: "\U0001F602", 3: "\U0001F62E", 4: "\U0001F622", 5: "\U0001F621", 6: "\U0001F44D"}
KIND_LABEL = {"image": "Photo", "video": "Video", "file": "File", "voice": "Voice message", "sticker": "Sticker",
              "link": "Link", "system": "System message", "reaction": "Reaction"}
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
               "November", "December"]
SHOWN_FLAGS = ("edit_ref_missing", "status_129", "tick_unknown", "time_is_delivery", "phone_time_fixed", "no_token")
URL_RE = re.compile(r"(https?://[^\s<]+)")

CSS = """
:root{--bg:#1c1d33;--panel:#26273f;--in:#3b3c57;--out:#7360f2;--text:#f2f2f8;--dim:#a3a4be;--accent:#9b8cff;
--pill:#34355052;--warn:#ffb454}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.4 "Segoe UI",system-ui,-apple-system,sans-serif}
a{color:var(--accent)}
header.top{position:sticky;top:0;z-index:5;background:var(--panel);padding:8px 14px;display:flex;flex-wrap:wrap;
gap:10px;align-items:center;border-bottom:1px solid #00000040}
header.top h1{font-size:16px;margin:0 8px 0 0}
header.top a.nav{text-decoration:none;padding:4px 10px;border-radius:14px;background:var(--in);color:var(--text)}
header.top select,header.top input{background:var(--in);color:var(--text);border:0;border-radius:14px;padding:4px 10px}
header.top label{color:var(--dim);font-size:13px}
main{max-width:760px;margin:0 auto;padding:12px 10px 60px}
.day{text-align:center;margin:18px 0 8px}
.day span{background:var(--in);color:var(--dim);padding:3px 12px;border-radius:12px;font-size:13px}
.row{display:flex;margin:2px 0}
.row.out{justify-content:flex-end}
.bubble{position:relative;max-width:78%;padding:7px 11px 5px;border-radius:16px;background:var(--in);
word-wrap:break-word;overflow-wrap:anywhere}
.row.out .bubble{background:var(--out)}
.row.in .bubble{border-top-left-radius:6px}
.row.out .bubble{border-top-right-radius:6px}
.who{font-size:12px;color:var(--accent);margin-bottom:1px}
.txt{white-space:pre-wrap}
.meta{font-size:11px;color:#ffffffa8;text-align:right;margin-top:2px;white-space:nowrap}
.row.in .meta{color:var(--dim)}
.tick{margin-left:4px;letter-spacing:-3px}
.tick.sent{color:#ffffff80}
.tick.seen{color:#53d2fa}
.edited{font-size:11px;color:#ffffffb0;margin-right:6px}
.reacts{position:absolute;bottom:-12px;display:flex;gap:2px}
.row.out .reacts{left:6px}
.row.in .reacts{right:6px}
.react{background:var(--panel);border:1px solid #00000050;border-radius:11px;padding:0 6px;font-size:13px}
.row.has-react{margin-bottom:12px}
.quote{border-left:3px solid var(--accent);padding:2px 8px;margin:0 0 5px;background:#00000026;border-radius:4px;
font-size:13px;color:#ffffffd0;max-height:3.9em;overflow:hidden}
.row.bare .bubble{background:none;padding:0}
.row.bare .meta{display:inline-block;background:#00000070;border-radius:10px;padding:1px 9px;margin-top:4px;color:#fff}
.big{font-size:64px;line-height:1.15;text-align:center}
.stk{display:block;width:150px;height:150px;object-fit:contain}
.pic{display:block;max-width:100%;max-height:360px;border-radius:10px;margin-bottom:4px}
.media{background:#00000030;border-radius:10px;padding:14px 16px;margin-bottom:4px;text-align:center;font-size:13px}
.media small{display:block;color:var(--dim);word-break:break-all}
.system{text-align:center;color:var(--dim);font-size:13px;margin:6px 0}
.src{display:none;position:absolute;top:-4px;width:9px;height:9px;border-radius:50%}
.row.in .src{right:-12px}.row.out .src{left:-12px}
body.markers .src{display:block}
.src.pc{background:#4fc3f7}.src.phone{background:#ffb454}
.legend{display:none;font-size:12px;color:var(--dim)}
body.markers .legend{display:inline}
body.verify .alt{display:block}
.alt{display:none;font-size:10px;color:#ffffff80;text-align:right}
.flag{font-size:10px;color:var(--warn);text-align:right}
div.gridwrap{overflow-x:auto}
table.grid{border-collapse:collapse;margin:8px 0 22px}
table.grid th,table.grid td{padding:4px 8px;text-align:center;font-size:13px}
table.grid td a{display:block;padding:2px 6px;border-radius:6px;text-decoration:none;color:var(--text);background:var(--in)}
table.grid td.pc a{outline:2px solid #4fc3f7}table.grid td.phone a{outline:2px solid #ffb454}
.cards a{display:block;background:var(--panel);padding:10px 14px;margin:6px 0;border-radius:10px;
text-decoration:none;color:var(--text)}
.cards small{color:var(--dim)}
"""

JS = """
(function(){
var d=document, b=d.body, cfg=window.CHAT||{};
function save(k,v){try{localStorage.setItem(k,v?'1':'0')}catch(e){}}
function load(k){try{return localStorage.getItem(k)==='1'}catch(e){return false}}
var m=d.getElementById('markers'), v=d.getElementById('verify');
if(m){m.checked=load('markers');b.classList.toggle('markers',m.checked);
 m.onchange=function(){b.classList.toggle('markers',m.checked);save('markers',m.checked)}}
if(v){v.checked=load('verify');b.classList.toggle('verify',v.checked);
 v.onchange=function(){b.classList.toggle('verify',v.checked);save('verify',v.checked)}}
var fmt=new Intl.DateTimeFormat(undefined,{hour:'numeric',minute:'2-digit'});
d.querySelectorAll('time[data-ms]').forEach(function(e){e.textContent=fmt.format(new Date(+e.dataset.ms))});
var sel=d.getElementById('month');
if(sel){sel.onchange=function(){location.href=sel.value}}
var dt=d.getElementById('date');
if(dt&&cfg.months){dt.onchange=function(){
 var s=dt.value; if(!s)return; var ym=s.slice(0,7), best=null;
 cfg.months.forEach(function(x){ if(x<=ym) best=x; });
 if(!best) best=cfg.months[0];
 location.href=best+'.html'+(best===ym?'#d'+s:'');}}
})();
"""


def _t(ms, fmt):
    return datetime.fromtimestamp(ms / 1000, TZ).strftime(fmt)


def _stamp(ms, shown_as_pill=False):
    """A time that the browser re-formats in the system's own style; the text is the fallback."""
    cls = ' class="t pill"' if shown_as_pill else ' class="t"'
    return f'<time{cls} data-ms="{ms}">{_t(ms, "%I:%M %p")}</time>'


def _linkify(text):
    out = []
    for part in URL_RE.split(text):
        if URL_RE.fullmatch(part):
            href = html.escape(part, quote=True)
            out.append(f'<a href="{href}" target="_blank" rel="noreferrer">{html.escape(part)}</a>')
        else:
            out.append(html.escape(part))
    return "".join(out)


def _slug(index):
    return f"chat{index}"


class Viewer:  # pylint: disable=too-many-instance-attributes,too-few-public-methods
    """Reads the archive and writes the site."""

    def __init__(self, archive_path, out_dir, bubble_time="composed", media_mode="link", emoticon_dir=None):
        self.arc = schema.connect(archive_path)
        self.out = Path(out_dir)
        self.bubble_time = bubble_time
        self.media_mode = media_mode
        self.emoticon_dir = Path(emoticon_dir) if emoticon_dir else None
        self.big = False
        self.photos = {}
        for mid, path, confidence in self.arc.execute(
                "SELECT message_id, original_path, confidence FROM message_media ORDER BY confidence DESC"):
            self.photos[mid] = (path, confidence)
        self.names = {n: (name or n) for n, name in self.arc.execute("SELECT number, name FROM contact")}
        self.reactions = defaultdict(dict)
        for mid, who, rid in self.arc.execute("SELECT message_id, reactor, reaction_id FROM reaction_effective"):
            self.reactions[mid][who] = rid
        pc = [r[0] for r in self.arc.execute("SELECT id FROM source_snapshot WHERE source LIKE 'pc-%'")]
        ph = [r[0] for r in self.arc.execute("SELECT id FROM source_snapshot WHERE source LIKE 'phone%'")]
        self.in_pc = self._lineage(pc)
        self.in_phone = self._lineage(ph)
        self.have_both = bool(pc and ph)

    def _lineage(self, snapshot_ids):
        if not snapshot_ids:
            return set()
        marks = ",".join(map(str, snapshot_ids))
        return {r[0] for r in self.arc.execute(
            f"SELECT entity_id FROM source_record WHERE entity = 'message' AND snapshot_id IN ({marks})")}

    def _media_src(self, mid):
        """Address of the photo for this message, relative to a month page (two folders below the site root)."""
        path, confidence = self.photos[mid]
        source = Path(path)
        if self.media_mode == "copy":
            folder = self.out / "media"
            folder.mkdir(exist_ok=True)
            target = folder / f"{mid}{source.suffix.lower() if source.suffix.lower() != '.image' else '.jpg'}"
            if not target.exists():
                shutil.copy2(source, target)
            return "../media/" + target.name, confidence
        try:
            rel = os.path.relpath(source, self.out / "chatX").replace(os.sep, "/")
        except ValueError:  # other drive on Windows
            rel = source.resolve().as_uri()
        return rel, confidence

    def _emoticon_html(self, name):
        if self.emoticon_dir and (self.emoticon_dir / f"{name}.png").exists():
            return f'<img class="stk" src="../emoticons/{name}.png" alt="({name})" title="({name})">'
        return f'<div class="big" title="({name})">{emoticons.emoji(name)}</div>'

    def _media_html(self, mid, kind, label):
        if mid not in self.photos or not Path(self.photos[mid][0]).exists():
            return f'<div class="media">{html.escape(label)}</div>'
        src, confidence = self._media_src(mid)
        src = html.escape(src, quote=True)
        if kind == "sticker":
            return f'<img class="stk" src="{src}" alt="Sticker">'
        note = "" if confidence.startswith("exact") else ' title="matched by time, not proof"'
        if kind == "video":
            return f'<video class="pic" controls preload="none" src="{src}"{note}></video>'
        return f'<a href="{src}" target="_blank"><img class="pic" loading="lazy" src="{src}"{note} alt="Photo"></a>'

    # -- one message ---------------------------------------------------------------------------------------------
    def _bubble(self, row, kind_chat):  # pylint: disable=too-many-locals
        (mid, direction, author, composed, sent, kind, text, caption, reply, media, tick, flags, version_count) = row
        flag_list = json.loads(flags or "[]")
        shown = sent if (self.bubble_time == "sent" and sent) else composed
        if kind in ("system", "reaction"):
            return f'<div class="system" id="m{mid}">{html.escape(text or KIND_LABEL.get(kind, ""))}</div>'
        inner = []
        big = False
        if kind_chat == "group" and direction == "in":
            inner.append(f'<div class="who">{html.escape(self.names.get(author, author or "?"))}</div>')
        if reply:
            try:
                quote = (json.loads(reply) or {}).get("text") or ""
            except ValueError:
                quote = ""
            inner.append(f'<div class="quote">{html.escape(quote[:200]) or "Replied message"}</div>')
        if kind in KIND_LABEL and kind != "link":
            caption = "" if (caption or "").startswith(("content://", "file://")) else caption
            name = "" if "://" in (media or "") else (media or "").replace("\\", "/").rsplit("/", 1)[-1]
            label = KIND_LABEL[kind] + (f" ({name})" if name and kind != "sticker" else "")
            inner.append(self._media_html(mid, kind, label))
            big = kind == "sticker" and mid in self.photos and Path(self.photos[mid][0]).exists()
            if caption:
                inner.append(f'<div class="txt">{_linkify(caption)}</div>')
        else:
            name = emoticons.lookup(text) if kind == "text" else None
            if name:
                inner.append(self._emoticon_html(name))
                big = True
            else:
                inner.append(f'<div class="txt">{_linkify(text or "")}</div>')
        meta = []
        if version_count > 1:
            meta.append('<span class="edited">Edited</span>')
        meta.append(_stamp(shown))
        if direction == "out" and tick in ("seen", "sent"):
            meta.append(f'<span class="tick {tick}">✓✓</span>' if tick == "seen"
                        else '<span class="tick sent">✓</span>')
        inner.append(f'<div class="meta" title="{_t(shown, "%d/%m/%Y %H:%M:%S")}">{"".join(meta)}</div>')
        alt = f"composed {_t(composed, '%H:%M:%S')}" + (f" · phone {_t(sent, '%H:%M:%S')}" if sent else "")
        inner.append(f'<div class="alt">{alt}</div>')
        shown_flags = [f for f in flag_list if f in SHOWN_FLAGS]
        if shown_flags:
            inner.append(f'<div class="flag alt">{" · ".join(shown_flags)}</div>')
        chips = self.reactions.get(mid, {})
        if chips:
            body = "".join(f'<span class="react" title="{who}">{REACTIONS.get(rid, "?")}</span>'
                           for who, rid in sorted(chips.items()))
            inner.append(f'<div class="reacts">{body}</div>')
        marker = ""
        if self.have_both:
            pcs, phs = mid in self.in_pc, mid in self.in_phone
            marker = '<span class="src pc" title="only in the PC export"></span>' if pcs and not phs else (
                '<span class="src phone" title="only on the phone"></span>' if phs and not pcs else "")
        cls = "row out" if direction == "out" else "row in"
        if chips:
            cls += " has-react"
        if big:
            cls += " bare"
        return f'<div class="{cls}" id="m{mid}"><div class="bubble">{"".join(inner)}{marker}</div></div>'

    # -- pages -----------------------------------------------------------------------------------------------------
    def _page(self, title, head, body, depth, extra=""):
        up = "../" * depth
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<link rel="stylesheet" href="{up}style.css"></head><body>{head}{body}'
                f'{extra}<script src="{up}app.js"></script></body></html>')

    def run(self):
        """Write everything. Returns {'chats': n, 'pages': n, 'messages': n}."""
        self.out.mkdir(parents=True, exist_ok=True)
        (self.out / "style.css").write_text(CSS, encoding="utf-8")
        if self.emoticon_dir and self.emoticon_dir.is_dir():
            (self.out / "emoticons").mkdir(exist_ok=True)
            for png in self.emoticon_dir.glob("*.png"):
                shutil.copy2(png, self.out / "emoticons" / png.name)
        (self.out / "app.js").write_text(JS, encoding="utf-8")
        chats = self.arc.execute(
            "SELECT c.chat_key, c.kind, c.title, count(m.id), min(m.composed_ms), max(m.composed_ms) FROM chat c"
            " JOIN message m ON m.chat_key = c.chat_key GROUP BY c.chat_key ORDER BY 4 DESC").fetchall()
        summary = {"chats": len(chats), "pages": 0, "messages": 0}
        cards = []
        for index, (key, kind, title, count, first, last) in enumerate(chats, 1):
            months = self._write_chat(index, key, kind, title)
            summary["pages"] += len(months)
            summary["messages"] += count
            label = f"Chat {index}" + (f" · {title}" if title else "") + f" ({kind})"
            cards.append(f'<a href="{_slug(index)}/index.html">{html.escape(label)}<br><small>{count:,} messages · '
                         f"{_t(first, '%d/%m/%Y')} to {_t(last, '%d/%m/%Y')}</small></a>")
        head = '<header class="top"><h1>Viber archive</h1></header>'
        body = '<main><div class="cards">' + "".join(cards) + "</div></main>"
        (self.out / "index.html").write_text(self._page("Viber archive", head, body, 0), encoding="utf-8")
        self.arc.close()
        return summary

    def _write_chat(self, index, key, kind, title):
        rows = self.arc.execute(
            "SELECT id, direction, author, composed_ms, sent_ms, kind, text, caption, reply_json, media_path, tick,"
            " flags, version_count FROM message WHERE chat_key = ? ORDER BY composed_ms, sort_order, seq, id", (key,))
        folder = self.out / _slug(index)
        folder.mkdir(exist_ok=True)
        by_month = defaultdict(list)
        for row in rows:
            by_month[_t(row[3], "%Y-%m")].append(row)
        months = sorted(by_month)
        label = f"Chat {index}" + (f" · {title}" if title else "")
        for month in months:
            parts, day = [], None
            for row in by_month[month]:
                this_day = _t(row[3], "%Y-%m-%d")
                if this_day != day:
                    day = this_day
                    nice = _t(row[3], "%A, %d %B %Y")
                    parts.append(f'<div class="day" id="d{day}"><span>{nice}</span></div>')
                parts.append(self._bubble(row, kind))
            position = months.index(month)
            nav = []
            if position:
                nav.append(f'<a class="nav" href="{months[position - 1]}.html">‹</a>')
            options = "".join(
                f'<option value="{m}.html"{" selected" if m == month else ""}>{MONTH_NAMES[int(m[5:]) - 1]} {m[:4]}'
                f" ({len(by_month[m]):,})</option>" for m in months)
            nav.append(f'<select id="month">{options}</select>')
            if position < len(months) - 1:
                nav.append(f'<a class="nav" href="{months[position + 1]}.html">›</a>')
            head = (f'<header class="top"><h1><a class="nav" href="index.html">{html.escape(label)}</a></h1>'
                    f'{"".join(nav)}'
                    f'<input id="date" type="date" min="{months[0]}-01" max="{months[-1]}-31" value="{month}-01" '
                    'title="Jump to a date">'
                    '<label><input type="checkbox" id="markers"> source markers</label>'
                    '<label><input type="checkbox" id="verify"> times and flags</label>'
                    '<span class="legend"><span style="color:#4fc3f7">●</span> only PC · '
                    '<span style="color:#ffb454">●</span> only phone</span></header>')
            script = f"<script>window.CHAT={{months:{json.dumps(months)}}};</script>"
            (folder / f"{month}.html").write_text(
                self._page(f"{label} {month}", head, f"<main>{''.join(parts)}</main>", 1, script), encoding="utf-8")
        self._write_chat_index(folder, label, months, by_month)
        return months

    def _write_chat_index(self, folder, label, months, by_month):
        years = defaultdict(dict)
        for month in months:
            years[month[:4]][int(month[5:])] = month
        pc_only = defaultdict(int)
        phone_only = defaultdict(int)
        if self.have_both:
            for month in months:
                for row in by_month[month]:
                    in_pc, in_ph = row[0] in self.in_pc, row[0] in self.in_phone
                    if in_pc and not in_ph:
                        pc_only[month] += 1
                    elif in_ph and not in_pc:
                        phone_only[month] += 1
        lines = ['<table class="grid"><tr><th></th>' + "".join(f"<th>{m[:3]}</th>" for m in MONTH_NAMES) + "</tr>"]
        for year in sorted(years):
            cells = []
            for number in range(1, 13):
                month = years[year].get(number)
                if not month:
                    cells.append("<td></td>")
                    continue
                cls = "pc" if pc_only[month] else ("phone" if phone_only[month] else "")
                tip = f"{len(by_month[month]):,} messages"
                if pc_only[month] or phone_only[month]:
                    tip += f" · {pc_only[month]:,} only PC · {phone_only[month]:,} only phone"
                cells.append(f'<td class="{cls}"><a href="{month}.html" title="{tip}">'
                             f'{len(by_month[month]):,}</a></td>')
            lines.append(f"<tr><th>{year}</th>{''.join(cells)}</tr>")
        lines.append("</table>")
        note = ("<p class='legend' style='display:block'><span style='color:#4fc3f7'>●</span> "
                "a month with messages only in "
                "the PC export, <span style='color:#ffb454'>●</span> only on the phone (outlined cells).</p>")
        head = ('<header class="top"><h1><a class="nav" href="../index.html">All chats</a> '
                f'{html.escape(label)}</h1></header>')
        body = f"<main>{note}<div class='gridwrap'>{''.join(lines)}</div></main>"
        (folder / "index.html").write_text(self._page(label, head, body, 1), encoding="utf-8")


def build(archive_path, out_dir, bubble_time="composed", media_mode="link", emoticon_dir=None):
    """Write the site; returns the counts."""
    return Viewer(archive_path, out_dir, bubble_time, media_mode, emoticon_dir).run()
