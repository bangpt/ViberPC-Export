<h1 align="center">📤 ViberPC-Export</h1>

<p align="center">
    Read and export <strong>your own</strong> Viber Desktop (ViberPC) message history on
    <strong>your own</strong> Windows computer — into a clean, readable chronological log.
    No key required; it uses the running Viber's already-unlocked SQLCipher engine.
</p>

<p align="center">
    <a href="https://github.com/r0073rr0r/ViberPC-Export/actions/workflows/tests.yml"><img src="https://github.com/r0073rr0r/ViberPC-Export/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
    <a href="https://github.com/r0073rr0r/ViberPC-Export/actions/workflows/pylint.yml"><img src="https://github.com/r0073rr0r/ViberPC-Export/actions/workflows/pylint.yml/badge.svg" alt="Pylint"></a>
    <a href="LICENSE"><img src="https://img.shields.io/github/license/r0073rr0r/ViberPC-Export" alt="License: GPL-3.0"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="Platform: Windows">
    <a href="https://github.com/r0073rr0r/ViberPC-Export/commits/main"><img src="https://img.shields.io/github/last-commit/r0073rr0r/ViberPC-Export" alt="Last commit"></a>
    <a href="https://github.com/r0073rr0r/ViberPC-Export/issues"><img src="https://img.shields.io/github/issues/r0073rr0r/ViberPC-Export" alt="Issues"></a>
    <a href="https://github.com/r0073rr0r/ViberPC-Export/stargazers"><img src="https://img.shields.io/github/stars/r0073rr0r/ViberPC-Export?style=social" alt="GitHub Stars"></a>
</p>

> [!IMPORTANT]
> **Purpose and boundaries.** Strictly for accessing **your own** data on **your own**
> machine (backup, migration, personal archive). Not for other people's devices or
> accounts. Everything runs locally; nothing is sent anywhere.

---

## 📚 Documentation

This README is the short version. For step-by-step guides (including for non-technical
users), see the **[Wiki](https://github.com/r0073rr0r/ViberPC-Export/wiki)**:

- **[Installation](https://github.com/r0073rr0r/ViberPC-Export/wiki/Installation)** — from a fresh PC to a working tool
- **[Quick Start](https://github.com/r0073rr0r/ViberPC-Export/wiki/Quick-Start)** — export everything with one command
- **[Understanding the Output](https://github.com/r0073rr0r/ViberPC-Export/wiki/Understanding-the-Output)** — what each exported file is
- **[Command Reference](https://github.com/r0073rr0r/ViberPC-Export/wiki/Command-Reference)** — every command and option
- **[Extract the Key & Decrypt Offline](https://github.com/r0073rr0r/ViberPC-Export/wiki/Extract-the-Key-and-Decrypt-Offline)** — the `hookkey` + `open` path for older Viber
- **[Media & Voice Messages](https://github.com/r0073rr0r/ViberPC-Export/wiki/Media-and-Voice-Messages)** — photos, videos, voice notes
- **[Troubleshooting](https://github.com/r0073rr0r/ViberPC-Export/wiki/Troubleshooting)** · **[FAQ](https://github.com/r0073rr0r/ViberPC-Export/wiki/FAQ)**

---

## 🧠 How it works (short version)

Newer Viber versions **internally transform** the key, so `viber.db` cannot be opened with
plain SQLCipher even when you capture the "hexkey" Viber uses. That is why the main method
is different: while Viber runs, its **own engine already holds the DB unlocked**. The tool
attaches (via frida) to Viber's live Qt SQL connection and makes it export the decrypted
tables into an unencrypted file (`ATTACH DATABASE … KEY ''` + `CREATE TABLE AS SELECT`).
The readable log is then built from that clean file.

## 📦 Requirements

- Windows, **Python 3.10+**
- **Viber Desktop running and logged in** (for all "live" methods)
- `pip install -r requirements.txt`
  - `frida`, `frida-tools` — required
  - `sqlcipher3-wheels` — only for the offline `open` method

## ⚙️ Setup

1. `pip install -r requirements.txt`
   — or install it as a package to get the `viber-export` command:
   ```bash
   pip install .            # then use:  viber-export all
   pip install .[offline]   # also pull in sqlcipher3-wheels for the 'open' method
   ```
2. Copy `.env.example` to `.env` and fill in if needed (usually you need **nothing** — the
   path and account number are auto-detected):
   ```
   VIBER_DB=              # empty = auto-detect %APPDATA%\ViberPC\<number>\viber.db
   VIBER_SELF_NUMBER=     # empty = derived from the path
   ```
3. Check: `python viber.py doctor`

> [!NOTE]
> `.env` and everything under `export/` are in `.gitignore` — **your data never goes to GitHub.**

## 🚀 Usage

```bash
python viber.py all            # RECOMMENDED: export + media + log + html
# or step by step:
python viber.py export
python viber.py media
python viber.py log
python viber.py html
```

> If you installed it as a package (see [Setup](#️-setup)), use `viber-export all`
> instead of `python viber.py all`.

Output:
- `export/viber_export.db` — the whole decrypted Viber (Contact, Messages, Events, …)
- `export/media/<peer>/…` — the actual images, videos, files and stickers, copied per contact
- `export/media_index.csv` — which message each media file belongs to
- `export/viber_messages.txt` — a readable chronological log (text, images, videos, files, stickers, links, replies, reactions, edits)
- `export/viber_log.jsonl` — the same log as structured JSON, one event per line (ideal for feeding to an AI)
- `export/viber_chats.html` — a browsable chat view with embedded images (open it in a browser)

> [!NOTE]
> Viber does **not** store images inside `viber.db` — it only keeps the on-disk
> paths. `media` copies whatever still exists on disk; for received items that
> were never downloaded it saves the thumbnail instead.

If `export` says there was no activity, **open a chat in Viber** while the script is
waiting (this triggers a read from the DB) and run it again.

## 🗄️ Personal archive (fork addition)

This fork adds `viberarchive/`, an append-only SQLite archive built from the upstream export (it needs only the
Python standard library; Frida is needed only for the export step itself).

```
python viber.py export                                   # upstream: writes export/viber_export.db
python archive.py import-pc export/viber_export.db --source pc-new --label 2026-10-14 \
       --archive archive/archive.db --exclude-peer <number of a chat to leave out>
python archive.py check --archive archive/archive.db     # counts and invariants
```

- A message is identified by its original token, so importing the same export twice changes nothing and a
  newer export adds only what is new.
- Edit events become versions of the original message; the latest version is the one shown.
- Reaction rows are kept with their raw reaction id. The last row per target and reactor wins, and id 0 clears it.
- The complete raw `Events` and `Messages` rows are stored beside the normalized columns.

### One-off: the phone database

If you have a copy of the phone's `viber_messages` SQLite file, import it **after** the PC export. Its message
tokens equal the PC tokens, so the two are joined by token. The PC keeps the composed time; the phone's delivery
time is stored beside it, and messages that only the phone has are added (flagged `time_is_delivery`; outgoing
ones get tick `unknown`, because the phone keeps no usable tick status).

```
python archive.py import-phone-db D:\ViberRecovery\DatabaseCopy\viber_messages --label 2026-10-14 \
       --archive archive/archive.db --exclude-peer <number of a chat to leave out>
```

Then `python archive.py reconcile --archive archive/archive.db --out report` writes `reconciliation.md`, `gaps.csv`
and `findings.csv`: what each source gave, what was merged, every difference for the same message, and the
stretches where only one source has messages.

Then `python archive.py html --archive archive/archive.db --out site` writes a static viewer: open `site/index.html`.
There is one page per chat and month in the look of the Viber app, a month list and a date picker, reactions, replies,
edits (with all versions) and ticks. The two header checkboxes show where each message came from (only the PC, only
the phone) and both times plus flags; `--bubble-time sent` shows the phone's time in the bubbles instead of the
composed time. Media is shown as a labelled placeholder for now.

A copy of the phone file is kept in a `sources` folder beside the archive (`--keep-copy-in -` turns that off).
Back that folder up too: the file cannot be obtained again without root.

## 🧰 All methods

| Command | What it does | Needs Viber? | Needs the key? |
|---|---|:---:|:---:|
| `export` | export from the live connection **(recommended)** | ✅ | ❌ |
| `media` | copy images/videos/files/stickers into `export/media/` | ❌ | ❌ |
| `log` | full log (text, media, stickers, replies, reactions) + JSONL | ❌ | ❌ |
| `html` | browsable HTML chat view with embedded images | ❌ | ❌ |
| `all` | `export` + `media` + `log` + `html` | ✅ | ❌ |
| `carve` | pull messages from RAM (partial names) | ✅ | ❌ |
| `hookkey` | capture the SQLCipher key/salt | ✅ | — |
| `open` | offline SQLCipher open of a copy | ❌ | ✅ |
| `schema` | print the schema from memory | ✅ | ❌ |
| `doctor` | environment check | — | — |

Examples of the auxiliary methods:
```bash
python viber.py carve                 # if Qt injection doesn't work on your version
python viber.py hookkey --write-env    # write the captured key into .env
python viber.py open --method all      # older versions: open a copy with the key
python viber.py schema                 # if the schema changed in a new version
```

## 🔄 What if I close or update Viber?

- **Viber closed:** the "live" methods (`export`, `carve`, `hookkey`, `schema`) will not
  work — only a running Viber keeps the DB unlocked. Start it and sign in, then run again.
  An already-created `viber_export.db` stays readable (it is unencrypted).
- **Viber update:** the export relies on Qt6 symbols and the `viber.db` connection name.
  A major update may change those. Order of resilience:
  1. `python viber.py export` (usually still works),
  2. `python viber.py carve` (does not depend on Qt symbols),
  3. `python viber.py schema` to check whether the schema/columns differ,
  4. `hookkey` + `open` if that version uses a directly-usable key.
- The export is a **point-in-time snapshot**. For the latest messages, run `export` again.

## 🗂️ Structure

```
viber.py            # CLI (all commands)
viberkit/           # per-method logic
  config.py           .env + paths (outputs to export/)
  frida_export.py     live export  [main]
  model.py            shared read model (contacts, peer resolution)
  enrich.py           message typing (media/stickers/links) + reactions
  stickers.py         resolve sticker ids to cached PNGs
  export_media.py     copy media into export/media/
  build_log.py        full log (.txt + .jsonl) from the export
  build_html.py       browsable HTML chat view
  frida_carve.py      carving from RAM
  frida_hookkey.py    key capture
  sqlcipher_open.py   offline opening
  frida_schema.py     schema from memory
tests/              # pytest unit tests for the enrichment logic
export/             # your data (gitignored, empty in the repo)
attic/              # research notes + a probe tool (reference)
.env / .env.example # secrets (ignored) / template
```

`attic/NOTES.md` records the whole research journey (brute-forcing the key, the bcrypt
hook, keyhunt, various probes) and the conclusions; `attic/probe_qt.py` helps diagnose a
new Viber version. Not needed for normal use.

## 🩺 Troubleshooting

- **"Viber is not running"** — start and sign in to Viber Desktop.
- **`export` doesn't trigger** — open a chat while the script waits; it watches for a read
  on `viber.db`.
- **Viber freezes** — don't use experimental in-process result iteration; the main
  `export` only runs quick `exec()` calls and does not block.
- **`open` fails on every variant** — the key is probably transformed internally (newer
  versions). Use `export` or `carve`.
- **Empty/odd log** — check `VIBER_SELF_NUMBER` (it affects IN/OUT) and run `schema` to
  confirm the columns match what is expected.

## 🤝 Contributing

Contributions are welcome! Please read the [Contributing Guide](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md) first. CI lints on Python 3.10–3.13 and requires a
clean `pylint` run (10/10) with the repo's [`.pylintrc`](.pylintrc).

## 🔐 Security

Found a vulnerability? Please **do not** open a public issue — follow the
[Security Policy](SECURITY.md) to report it privately.

## ⚖️ Legal & License

This tool only accesses a local database that belongs to you, on your own machine. You are
responsible for using it in accordance with local laws and Viber's terms. Do not use it on
data that is not yours.

Licensed under the **GNU General Public License v3.0** — see [LICENSE](LICENSE).

<p align="center"><sub>Made with ❤️ by <a href="https://github.com/r0073rr0r">r0073rr0r</a></sub></p>

### Showing photos: `link-media`

```
python archive.py link-media --archive archive\archive.db ^
    --pc-index ..\ViberPCExport\media_index.csv ^
    --phone-manifest d:\Projects\Viber\inbox\phone_media\manifest.csv
python archive.py html --archive archive\archive.db --out site
```

`link-media` fills `message_media` (messages are not changed). PC photos link exactly (`exact_event`, and `exact_id` for
phone-only messages that share a download id with a PC file); files copied from the phone link by time
(`time_match`: file time 1 to 3 s after the message, one file per message). Run it again whenever new media arrive.
`html --media copy` puts a copy of each photo inside the site folder (self-contained, larger); the default points at the
files where they are. A photo with no file keeps the grey "Photo" placeholder.

Stickers: the archive now keeps each sticker's id (`message.sticker_id`). `link-media --stickers "<...>\.stickers"` links
stickers by id to the pack folders' `r144_<id>_orig.png` files (`exact_sticker_id`). Archives built before this change have
no sticker ids: rebuild them (delete archive.db, -wal and -shm; keep `archive\sources`) and run the imports again.

### Viewer navigation and names

- A floating label shows the date of the messages on screen; the date button (and its calendar) follows it. In the
  calendar, days without messages are dimmed and days found in only one source carry a blue (only PC) or orange
  (only phone) dot; "earlier / later difference" jumps between those days. The data is `chatN/days.js`.
- Chat names: `--chat-names names.json` with `{"direct:849...": "Her name", "notes": "My Notes"}` overrides; otherwise the
  chat title, then the contact name of the peer, `My Notes` for notes, else `Group chat`. The folder names `chat1`,
  `chat2`... are just the position in the list (largest chat first); they are not names.
- Search: the **Search** button in the top bar (or `/`) opens a sidebar on the left; `Esc` or ✕ hides it, and it stays
  open or closed as you move between pages. It searches that chat's text and photo captions, needs all the words you
  type, and lists matches newest first (a tick reverses that), 10, 25 or 50 to a page, with the words highlighted and
  page buttons or a page number at the bottom. Ticks: *whole word* (not part of a longer word) and *match accents*
  (otherwise `chi ay` finds `Chị ấy`); all are remembered. Click a result to open its month and flash the message.
  The result page you were on is kept while you move between months, so you can go back to the next result at once.
  The index is `chatN/search.js`, loaded the first time you use the box, so pages open as fast as before; a chat with
  hundreds of thousands of messages takes a second or two to load it. Hidden duplicates, system lines, reactions and
  stickers are not searched.
