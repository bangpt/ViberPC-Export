"""Backup: the restic command lines, the staged database copy, the restore comparison (with a stand-in restic)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

from tests import fixture_export
from viberarchive import __main__ as cli
from viberarchive import backup, pcimport

STUB = '''
import json, shutil, sys
from pathlib import Path
log = Path(sys.argv[1])
args = sys.argv[2:]
with open(log, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\\n")
repo = Path(args[args.index("-r") + 1])
cmd = args[[i for i, a in enumerate(args) if a in ("cat", "init", "backup", "restore", "forget", "snapshots")][0]]
if cmd == "cat":
    sys.exit(0 if (repo / "config").exists() else 10)
if cmd == "init":
    repo.mkdir(parents=True, exist_ok=True); (repo / "config").write_text("x"); sys.exit(0)
if cmd == "backup":
    paths = [a for a in args[args.index("backup"):] if Path(a).is_absolute() and Path(a).exists()]
    (repo / "last.json").write_text(json.dumps(paths)); sys.exit(0)
if cmd == "restore":
    target = Path(args[args.index("--target") + 1]); src = Path(args[args.index("--include") + 1])
    shutil.copytree(src, target / "restored"); sys.exit(0)
if cmd == "snapshots":
    print("ID  Time  Host"); sys.exit(0)
sys.exit(0)
'''


@pytest.fixture(name="setup")
def setup_fixture(tmp_path):
    export = tmp_path / "viber_export.db"
    fixture_export.standard(str(export))
    arc_path = tmp_path / "built.db"
    pcimport.import_pc(str(arc_path), str(export), "pc-old", exclude_peers=["84999000999"])
    root = tmp_path / "ViberArchive"
    (root / "archive").mkdir(parents=True)
    (root / "sources").mkdir()
    (root / "config").mkdir()
    (root / "derived").mkdir()
    (root / "sources" / "phone.csv").write_text("x", encoding="utf-8")
    shutil.copy(arc_path, root / "archive" / "archive.db")
    (root / "config" / "names.json").write_text("{}", encoding="utf-8")
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "pw.txt").write_text("pw", encoding="utf-8")
    stub = tmp_path / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp_path / "log.txt"
    config = {"restic": [sys.executable, str(stub), str(log)], "keep": {"daily": 7, "monthly": 12},
              "repos": [{"name": "one", "repo": str(tmp_path / "repo1"), "password_file": str(secrets / "pw.txt")},
                        {"name": "two", "repo": str(tmp_path / "repo2"), "password_file": str(secrets / "pw.txt")}]}
    (root / "config" / "backup.json").write_text(json.dumps(config), encoding="utf-8")
    return root, log, tmp_path


def test_backup_stages_a_copy_and_uploads_to_every_repository(setup):
    root, log, tmp = setup
    results = backup.backup(root / "config")
    assert results == {"one": "ok", "two": "ok"}
    manifest = json.loads((root / "derived" / "_stage" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["message"] > 0 and len(manifest["sha256"]) == 64
    sent = json.loads((tmp / "repo1" / "last.json").read_text(encoding="utf-8"))
    assert str(root / "derived" / "_stage") in sent and str(root / "sources") in sent
    assert str(root / "derived") not in sent and str(root / "_retire") not in sent
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert any("--exclude" in c and str(root / "archive" / "archive.db") in c for c in calls)
    assert any("forget" in c and "--keep-daily" in c for c in calls)
    assert json.loads((root / "derived" / "backup_state.json").read_text(encoding="utf-8"))["two"]["ok"]


def test_verify_compares_the_restore_and_detects_damage(setup, capsys):
    root, _, tmp = setup
    backup.backup(root / "config")
    assert backup.verify(root / "config") == 0
    assert "the restore matches" in capsys.readouterr().out
    # damage the stage copy that the stub "restores" from
    with open(root / "derived" / "_stage" / "archive.db", "ab") as handle:
        handle.write(b"junk")
    assert backup.verify(root / "config") == 2
    assert "SHA-256" in capsys.readouterr().out
    assert tmp.exists()


def test_password_inside_the_root_is_refused(setup):
    root, _, _ = setup
    config = json.loads((root / "config" / "backup.json").read_text(encoding="utf-8"))
    (root / "config" / "pw.txt").write_text("pw", encoding="utf-8")
    config["repos"][0]["password_file"] = str(root / "config" / "pw.txt")
    (root / "config" / "backup.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(backup.BackupError, match="outside"):
        backup.load_config(root / "config")


def test_a_failing_repository_does_not_stop_the_other(setup):
    root, _, tmp = setup
    config = json.loads((root / "config" / "backup.json").read_text(encoding="utf-8"))
    config["repos"][0]["repo"] = str(tmp / "nope" / "deeper" / "x")
    (tmp / "nope").write_text("a file, so init cannot create a folder", encoding="utf-8")
    (root / "config" / "backup.json").write_text(json.dumps(config), encoding="utf-8")
    results = backup.backup(root / "config")
    assert results["two"] == "ok" and results["one"].startswith("cannot open")


def test_missing_settings_and_missing_restic_are_explained(tmp_path, setup, capsys):
    with pytest.raises(backup.BackupError, match="backup.json"):
        backup.load_config(tmp_path)
    root, _, _ = setup
    config = json.loads((root / "config" / "backup.json").read_text(encoding="utf-8"))
    config["restic"] = "restic-that-does-not-exist"
    (root / "config" / "backup.json").write_text(json.dumps(config), encoding="utf-8")
    assert cli.main(["backup", "--config", str(root / "config")]) == 1
    assert "restic was not found" in capsys.readouterr().out
    assert cli.main(["backup", "--config", str(root / "config"), "--dry-run"]) == 0
    assert Path(root / "derived").is_dir()
