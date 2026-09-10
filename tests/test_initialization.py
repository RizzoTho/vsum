"""Installation preferences and relocation, without network or global executables."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from conftest import PROJECT_ROOT, packet_path_from_stdout


@pytest.fixture(autouse=True)
def isolated_config(vsum, monkeypatch, tmp_path):
    monkeypatch.setattr(vsum, "CONFIG_PATH", tmp_path / "installation" / ".env")
    vsum.CONFIG_PATH.parent.mkdir()
    for key in vsum.CONFIG_DEFAULTS:
        monkeypatch.delenv(key, raising=False)


def test_init_preserves_existing_configuration(vsum):
    assert vsum.main(["init", "--readable-out-dir", "/notes/My Vault"]) == 0
    original = vsum.CONFIG_PATH.read_bytes()
    assert vsum.read_config()["VSUM_READABLE_ROOT"] == "/notes/My Vault"
    assert vsum.main(["init", "--readable-out-dir", "/different"]) == 1
    assert vsum.CONFIG_PATH.read_bytes() == original


def test_init_does_not_persist_environment(vsum, monkeypatch):
    monkeypatch.setenv("VSUM_READABLE_ROOT", "/temporary-override")
    assert vsum.main(["init"]) == 0
    assert vsum.read_config()["VSUM_READABLE_ROOT"] == "wiki/Clippings"


def test_init_rejects_multiline_values_without_creating_file(vsum):
    assert vsum.main(["init", "--readable-out-dir", "notes\nVSUM_OUT_ROOT=elsewhere"]) == 1
    assert not vsum.CONFIG_PATH.exists()


@pytest.mark.parametrize("content", [
    "UNKNOWN_SETTING=value\n",
    "VSUM_OUT_ROOT=\n",
    'VSUM_OUT_ROOT="unfinished\n',
    "VSUM_OUT_ROOT=one\nVSUM_OUT_ROOT=two\n",
    "VSUM_OUT_ROOT=path with spaces\n",
])
def test_invalid_config_fails_visibly(vsum, content, capsys):
    vsum.CONFIG_PATH.write_text(content)
    assert vsum.main(["doctor"]) == 1
    assert str(vsum.CONFIG_PATH) in capsys.readouterr().err


def test_values_are_literal_data(vsum, tmp_path):
    marker = tmp_path / "must-not-exist"
    value = f"$(touch {marker})"
    assert vsum.main(["init", "--readable-out-dir", value]) == 0
    assert vsum.read_config()["VSUM_READABLE_ROOT"] == value
    assert not marker.exists()


def test_precedence_and_calling_workspace(vsum, monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    # An unrelated project .env must not even be parsed.
    (workspace / ".env").write_text("OTHER_APP_SECRET=irrelevant\nVSUM_OUT_ROOT=wrong\n")
    vsum.CONFIG_PATH.write_text("VSUM_OUT_ROOT=local-output\nVSUM_READABLE_ROOT=local-notes\n")
    monkeypatch.setenv("VSUM_READABLE_ROOT", "environment-notes")
    args = vsum.build_parser().parse_args(["run", "u", "--whisper-model", "tiny"])
    vsum.configure_run(args)
    assert args.out_dir == workspace / "local-output"
    assert args.readable_out_dir == workspace / "environment-notes"
    assert args.whisper_model == "tiny"
    args = vsum.build_parser().parse_args(["run", "u", "--readable-out-dir", "explicit-notes"])
    vsum.configure_run(args)
    assert args.readable_out_dir == workspace / "explicit-notes"


def test_blank_environment_fails(vsum, monkeypatch):
    monkeypatch.setenv("VSUM_OUT_ROOT", " ")
    assert vsum.main(["doctor"]) == 1


def test_doctor_reports_missing_dependencies_without_installing(vsum, monkeypatch, capsys):
    monkeypatch.setattr(vsum.shutil, "which", lambda name: None)
    assert vsum.main(["doctor"]) == 1
    output = capsys.readouterr().out
    assert "yt-dlp: MISSING (required)" in output
    assert "ffmpeg: not installed (optional)" in output
    assert not vsum.CONFIG_PATH.exists()


def test_doctor_optional_dependencies_do_not_block(vsum, monkeypatch):
    monkeypatch.setattr(vsum.shutil, "which", lambda name: "/tools/yt-dlp" if name == "yt-dlp" else None)
    assert vsum.main(["doctor"]) == 0


def test_relocated_package_initializes_and_runs_from_other_workspace(tmp_path):
    installed = tmp_path / "installed skill"
    (installed / "scripts").mkdir(parents=True)
    (installed / "references").mkdir()
    for relative in ("scripts/vsum.py", "SKILL.md", "references/READABLE.md"):
        shutil.copyfile(PROJECT_ROOT / relative, installed / relative)
    workspace = tmp_path / "separate workspace"
    workspace.mkdir()
    (workspace / ".env").write_text("UNRELATED=other-app\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("VSUM_")}
    script = installed / "scripts/vsum.py"
    init = subprocess.run([sys.executable, str(script), "init"], cwd=workspace, env=env, capture_output=True, text=True)
    assert init.returncode == 0, init.stderr
    assert (installed / ".env").is_file()
    assert (workspace / ".env").read_text() == "UNRELATED=other-app\n"
    # Load the actual relocated script in a separate Python process. Stub only
    # platform I/O; exercise real config loading, packet writing and resources.
    harness = '''
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("relocated_vsum", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.dump_metadata = lambda *args: {"id": "local", "title": "Local video"}
pathlib.Path("source.txt").write_text("A complete local transcript for packaging verification.")
raise SystemExit(m.main(["run", "https://example.com/video", "--transcript", "source.txt", "--no-download", "--read"]))
'''
    result = subprocess.run([sys.executable, "-c", harness, str(script)], cwd=workspace, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    packet_path = packet_path_from_stdout(result.stdout)
    packet = json.loads(packet_path.read_text())
    assert packet_path.is_relative_to(workspace / "outputs/vsum")
    assert Path(packet["read"]["output"]).is_relative_to(workspace / "wiki/Clippings")
    assert Path(packet["read"]["instructions"]) == installed / "references/READABLE.md"
    assert not (installed / "outputs").exists()
    assert packet["read"]["status"] == "pending"


def test_missing_writing_contract_fails_before_network(vsum, monkeypatch, tmp_path):
    monkeypatch.setattr(vsum, "READABLE_INSTRUCTIONS", tmp_path / "missing.md")

    def unexpected_network(*args):
        pytest.fail("network called before validating the writing contract")

    monkeypatch.setattr(vsum, "dump_metadata", unexpected_network)
    assert vsum.main(["run", "https://example.com/video", "--read"]) == 1
