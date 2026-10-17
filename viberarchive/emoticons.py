"""Viber's text emoticons: the typed codes and the (name) forms are the same big picture in the app.

The archive keeps the text exactly as it was received. The viewer only changes how it is drawn: a message that is
nothing but an emoticon becomes a big picture (a PNG from --emoticons <folder> named <name>.png if you have one,
otherwise a standard emoji). Names and codes below are the common Viber set; extend EMOTICONS if one is missing.
"""
import re
import shutil
from pathlib import Path

# name: (typed codes, fallback emoji)
EMOTICONS = {
    "smiley": ((":)", ":-)", "=)"), "🙂"),
    "teeth": ((":D", ":-D", "=D"), "😁"),
    "sad": ((":(", ":-(", "=("), "🙁"),
    "wink": ((";)", ";-)"), "😉"),
    "tongue": ((":P", ":-P", ":p"), "😛"),
    "surprised": ((":O", ":-O", ":o"), "😮"),
    "cry": ((":'(",), "😢"),
    "neutral": ((":|", ":-|"), "😐"),
    "cool": (("B)", "B-)", "8)"), "😎"),
    "kiss": ((":*", ":-*"), "😘"),
    "heart": (("<3",), "❤️"),
    "yummi": ((), "😋"), "happy": ((), "😄"), "laugh": ((), "😂"), "inlove": ((), "😍"), "shy": ((), "😊"),
    "mad": ((), "😠"), "eyeroll": ((), "🙄"), "like": ((), "👍"), "oh": ((), "😮"), "sick": ((), "🤢"),
    "flirt": ((), "😘"), "owl": ((), "🦉"),
}
_BY_TEXT = {}
for _name, (_codes, _emoji) in EMOTICONS.items():
    _BY_TEXT[f"({_name})"] = _name
    for _code in _codes:
        _BY_TEXT[_code] = _name
_NAME_RE = re.compile(r"\((\w+)\)")


def lookup(text):
    """Canonical name when the whole message is one emoticon (either spelling), else None."""
    text = (text or "").strip()
    found = _BY_TEXT.get(text)
    if found:
        return found
    named = _NAME_RE.fullmatch(text)
    return named.group(1).lower() if named and named.group(1).lower() in EMOTICONS else None


def emoji(name):
    """Fallback emoji for a canonical name."""
    return EMOTICONS[name][1]


_SCALE_RE = re.compile(r"^\((.+)\)_scaled_(\d+)\.png$")
_INLINE_RE = re.compile(r"\(([^()\s]{1,30})\)")


def slug(name):
    """File-name-safe form of an emoticon name (the folder has names such as (!) and ($))."""
    return re.sub(r"[^0-9A-Za-z_-]", lambda m: f"x{ord(m.group(0)):02x}", name)


class Pack:
    """The pictures in Viber's .emoticons folder: files like (smiley)_scaled_88.png; the biggest size wins."""

    def __init__(self, folder=None, seen_icon=None):
        self.files = {}
        if folder and Path(folder).is_dir():
            best = {}
            for path in Path(folder).glob("*.png"):
                found = _SCALE_RE.match(path.name)
                if found and int(found.group(2)) >= best.get(found.group(1), (0, None))[0]:
                    best[found.group(1)] = (int(found.group(2)), path)
            self.files = {name: path for name, (_, path) in best.items()}
            if "seen" not in self.files:  # any file with "seen" in its name also works, e.g. seen.png
                plain = sorted(f for f in Path(folder).glob("*.png") if "seen" in f.name.lower())
                if plain:
                    self.files["seen"] = plain[-1]
        if seen_icon and Path(seen_icon).is_file():
            self.files["seen"] = Path(seen_icon)

    def has(self, name):
        """True when there is a picture for this name."""
        return name in self.files

    def publish(self, folder):
        """Copy the pictures into the site; returns the number copied."""
        folder = Path(folder)
        if self.files:
            folder.mkdir(parents=True, exist_ok=True)
        for name, path in self.files.items():
            shutil.copy2(path, folder / f"{slug(name)}.png")
        return len(self.files)

    def whole(self, text):
        """Canonical name when the whole message is one emoticon this pack (or the built-in list) knows."""
        found = lookup(text)
        if found:
            return found
        named = _INLINE_RE.fullmatch((text or "").strip())
        return named.group(1) if named and self.has(named.group(1)) else None

    def inline(self, escaped_text, small_class="emo"):
        """Replace (name) inside already-escaped text by a small picture when the pack has it."""
        def swap(match):
            name = match.group(1)
            if not self.has(name):
                return match.group(0)
            return f'<img class="{small_class}" src="../emoticons/{slug(name)}.png" alt="({name})" title="({name})">'
        return _INLINE_RE.sub(swap, escaped_text) if self.files else escaped_text
