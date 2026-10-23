"""Backup of the archive with restic, to Google Drive (through rclone) and Backblaze B2.

    python archive.py backup --config D:\\ViberArchive\\config          # back up to every repository
    python archive.py backup --config ... --verify                      # restore the latest backup and compare
    python archive.py backup --config ... --status                      # list the snapshots in each repository

The settings live in <config>/backup.json (see the README). restic encrypts on this computer before anything leaves it.
Before each run a consistent copy of archive.db is made with SQLite's backup command into <root>/derived/_stage, with a
manifest (SHA-256 and row counts) so that a restore can be compared with what was uploaded. The live archive.db and
its -wal/-shm files are skipped, because the copy replaces them. The password and key files must be outside the root:
a backup that contains its own password is no protection.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path

TABLES = ("message", "message_version", "reaction", "source_snapshot")
TAG = "viberarchive"


class BackupError(Exception):
    """Something the person has to fix (a missing setting, restic not installed, a failed upload)."""


def load_config(config_dir):
    """Read <config>/backup.json into a dict with absolute paths."""
    path = Path(config_dir) / "backup.json"
    if not path.is_file():
        raise BackupError(f"{path} not found. See the README, 'Backup', for what it contains.")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    root = Path(raw.get("root") or Path(config_dir).resolve().parent).resolve()
    cfg = {
        "root": root,
        "include": [root / name for name in raw.get("include", ["sources", "archive", "config"])],
        "db": root / raw.get("archive_db", "archive/archive.db"),
        "stage": root / raw.get("stage", "derived/_stage"),
        "state": root / raw.get("state", "derived/backup_state.json"),
        "keep": raw.get("keep"),
        "restic": raw.get("restic", "restic"),
        "repos": raw.get("repos") or [],
    }
    if not cfg["repos"]:
        raise BackupError("backup.json has no 'repos'.")
    for repo in cfg["repos"]:
        if not repo.get("name") or not repo.get("repo") or not repo.get("password_file"):
            raise BackupError("every repo needs 'name', 'repo' and 'password_file'.")
        for key in ("password_file", "env_file"):
            if repo.get(key):
                file = Path(repo[key]).expanduser()
                if not file.is_file():
                    raise BackupError(f"{key} of {repo['name']} not found: {file}")
                if root in file.resolve().parents:
                    raise BackupError(f"{key} of {repo['name']} is inside {root}; keep it outside that folder.")
    if not cfg["db"].is_file():
        raise BackupError(f"archive database not found: {cfg['db']}")
    return cfg


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _counts(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        found = {}
        for table in TABLES:
            try:
                found[table] = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # nosec: fixed names
            except sqlite3.OperationalError:
                continue
        return found
    finally:
        conn.close()


def stage_database(cfg):
    """Consistent copy of archive.db plus manifest.json in the stage folder; returns the manifest."""
    stage = cfg["stage"]
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    source = sqlite3.connect(f"file:{cfg['db']}?mode=ro", uri=True)
    target = sqlite3.connect(stage / "archive.db")
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    copy = stage / "archive.db"
    manifest = {"made": time.strftime("%Y-%m-%d %H:%M:%S"), "sha256": _sha256(copy), "counts": _counts(copy)}
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def _env(repo):
    env = dict(os.environ)
    if repo.get("env_file"):
        for line in Path(repo["env_file"]).expanduser().read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"')
    return env


def _command(cfg, repo, args):
    restic = cfg["restic"]
    base = list(restic) if isinstance(restic, list) else [restic]
    return base + ["-r", repo["repo"], "--password-file", str(Path(repo["password_file"]).expanduser())] + args


def _run(command, env, show):
    if show:
        print("   $", " ".join(command))
    try:
        return subprocess.run(command, env=env, check=False, capture_output=True, text=True)
    except FileNotFoundError as err:
        raise BackupError("restic was not found. Install it (winget install restic.restic) or set 'restic' in "
                          "backup.json to its full path.") from err


def _keep_args(keep):
    args = []
    for period in ("last", "daily", "weekly", "monthly", "yearly"):
        if keep and keep.get(period):
            args += [f"--keep-{period}", str(keep[period])]
    return args


def _backup_args(cfg):
    paths = [str(cfg["stage"])] + [str(p) for p in cfg["include"] if p.exists()]
    skip = [str(cfg["db"]) + suffix for suffix in ("", "-wal", "-shm", "-journal")]
    args = ["backup", "--tag", TAG, "--host", TAG]
    for item in skip:
        args += ["--exclude", item]
    return args + paths


def _record(cfg, name, ok):
    state = {}
    if cfg["state"].is_file():
        state = json.loads(cfg["state"].read_text(encoding="utf-8"))
    state[name] = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "ok": ok} if ok else state.get(name, {})
    cfg["state"].parent.mkdir(parents=True, exist_ok=True)
    cfg["state"].write_text(json.dumps(state, indent=1), encoding="utf-8")


def backup(config_dir, dry_run=False):
    """Back up to every repository. Returns {repo name: 'ok' or the error text}."""
    cfg = load_config(config_dir)
    manifest = {"sha256": "(dry run)", "counts": {}} if dry_run else stage_database(cfg)
    print(f"Archive copy: sha256 {manifest['sha256'][:16]}…  rows {manifest['counts']}")
    results = {}
    for repo in cfg["repos"]:
        name, env = repo["name"], _env(repo)
        print(f"== {name}  ({repo['repo']})")
        if dry_run:
            print("   $", " ".join(_command(cfg, repo, _backup_args(cfg))))
            results[name] = "dry run"
            continue
        if _run(_command(cfg, repo, ["cat", "config"]), env, False).returncode != 0:
            made = _run(_command(cfg, repo, ["init"]), env, True)
            if made.returncode != 0:
                results[name] = f"cannot open or create the repository: {made.stderr.strip()[-400:]}"
                continue
        done = _run(_command(cfg, repo, _backup_args(cfg)), env, True)
        if done.returncode != 0:
            results[name] = f"restic backup failed: {done.stderr.strip()[-400:]}"
            continue
        if cfg["keep"]:
            _run(_command(cfg, repo, ["forget", "--tag", TAG, "--host", TAG, "--prune"] + _keep_args(cfg["keep"])),
                 env, True)
        _record(cfg, name, True)
        results[name] = "ok"
    for name, text in results.items():
        print(f"{name:<12} {text}")
    return results


def status(config_dir):
    """Print the snapshots of each repository; returns the number of repositories that could not be read."""
    cfg = load_config(config_dir)
    bad = 0
    for repo in cfg["repos"]:
        print(f"== {repo['name']}")
        done = _run(_command(cfg, repo, ["snapshots", "--tag", TAG]), _env(repo), False)
        print(done.stdout.strip() or done.stderr.strip())
        bad += done.returncode != 0
    return bad


def verify(config_dir):
    """Restore the newest backup of each repository to a temporary folder and compare it with what was uploaded."""
    cfg = load_config(config_dir)
    live = _counts(cfg["db"])
    failed = 0
    for repo in cfg["repos"]:
        print(f"== {repo['name']}")
        with tempfile.TemporaryDirectory(prefix="viber-restore-") as tmp:
            done = _run(_command(cfg, repo, ["restore", "latest", "--tag", TAG, "--target", tmp,
                                             "--include", str(cfg["stage"])]), _env(repo), True)
            files = list(Path(tmp).rglob("manifest.json"))
            if done.returncode != 0 or not files:
                print(f"   FAILED: nothing restored. {done.stderr.strip()[-300:]}")
                failed += 1
                continue
            manifest = json.loads(files[0].read_text(encoding="utf-8"))
            copy = files[0].parent / "archive.db"
            problems = []
            if _sha256(copy) != manifest["sha256"]:
                problems.append("the restored archive.db differs from the uploaded copy (SHA-256)")
            conn = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                problems.append("SQLite integrity check failed")
            conn.close()
            restored = _counts(copy)
            if restored != manifest["counts"]:
                problems.append(f"row counts {restored} differ from the manifest {manifest['counts']}")
            print("   restored copy from", manifest["made"], "rows", restored)
            if restored != live:
                print(f"   note: the live archive now has {live}; it changed after that backup")
            for problem in problems:
                print("   FAILED:", problem)
            failed += bool(problems)
            if not problems:
                print("   OK: the restore matches what was uploaded")
    return failed
