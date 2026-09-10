"""run pipeline behavior with fully mocked platform calls: packet contract, default download, media lifecycle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from conftest import packet_path_from_stdout


@pytest.fixture
def offline_run(vsum, monkeypatch, tmp_path):
    """Mock every remote touch; caller configures per-test behavior."""
    state = {"metadata_calls": 0, "subtitle_calls": 0, "download_calls": 0}

    def fake_metadata(url, cookies=None):
        state["metadata_calls"] += 1
        return {
            "id": "abc123",
            "title": "Test Video",
            "duration": 120,
            "webpage_url": url,
            "subtitles": {},
            "automatic_captions": {},
            "formats": [],
        }

    def fake_subtitles(url, source_dir, cookies, meta):
        state["subtitle_calls"] += 1
        return None

    def fake_download(url, media_dir, cookies=None):
        state["download_calls"] += 1
        if state.get("download_fails"):
            raise vsum.BriefError("simulated download failure")
        media_dir.mkdir(parents=True, exist_ok=True)
        video = media_dir / "video.mp4"
        video.write_bytes(b"fake-video-bytes")
        return video

    monkeypatch.setattr(vsum, "dump_metadata", fake_metadata)
    monkeypatch.setattr(vsum, "try_download_subtitles", fake_subtitles)
    monkeypatch.setattr(vsum, "download_video", fake_download)
    monkeypatch.setattr(vsum, "ensure_video_file", lambda p: p.resolve())
    return state


def run_cli(vsum, tmp_path, transcript, extra, capsys):
    """Run `vsum run` and return (code, packet dict) with the packet path taken from stdout."""
    out = tmp_path / "out"
    clippings = tmp_path / "clippings"
    tmp_media = tmp_path / "tmpmedia"
    argv = [
        "run", "https://example.com/watch?v=abc123",
        "--transcript", str(transcript),
        "--out-dir", str(out),
        "--readable-out-dir", str(clippings),
        "--tmp-dir", str(tmp_media),
        *extra,
    ]
    code = vsum.main(argv)
    captured = capsys.readouterr()
    packet_path = packet_path_from_stdout(captured.out)
    return code, json.loads(packet_path.read_text(encoding="utf-8")), packet_path


def test_no_read_no_read_object_and_no_intent_key(vsum, offline_run, tmp_path, capsys):
    transcript = tmp_path / "t.txt"
    transcript.write_text("hello world content\n", encoding="utf-8")
    code, packet, _ = run_cli(vsum, tmp_path, transcript, ["--no-download"], capsys)
    assert code == 0
    assert "read" not in packet
    assert "intent" not in packet
    assert packet["pipeline"]["video_download"] == "skipped"
    assert offline_run["download_calls"] == 0


def test_read_bare_flag_pending_packet_contract(vsum, offline_run, tmp_path, capsys):
    transcript = tmp_path / "t.txt"
    transcript.write_text("hello world content\n", encoding="utf-8")
    code, packet, _ = run_cli(vsum, tmp_path, transcript, ["--read"], capsys)
    assert code == 0
    read = packet["read"]
    assert read["status"] == "pending"
    assert read["intent"] == vsum.DEFAULT_READ_INTENT
    input_path = Path(read["input"])
    assert input_path.is_absolute() and input_path.exists()
    output_path = Path(read["output"])
    assert output_path.is_absolute() and output_path == output_path.resolve()
    assert Path(read["instructions"]).name == "READABLE.md"
    # assets dir follows the images/<source-dir>/<run-dir> convention next to the article
    assets = Path(read["assets"])
    assert assets.parent.parent == output_path.parent / "images"
    assert assets.name == Path(packet["artifacts"]["run_dir"]).name
    # output is a target only: never registered as a generated artifact
    assert "article" not in packet["artifacts"]
    assert read["output"] not in packet["artifacts"].values()
    # plain text source: no fake timeline
    assert read["segments"] is None
    assert "without timing" in read["segments_note"]
    assert "segments" not in packet["artifacts"]


def test_read_custom_intent_and_media_kept_for_pending(vsum, offline_run, tmp_path, capsys):
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    code, packet, _ = run_cli(vsum, tmp_path, transcript, ["--read", "重点解释设计取舍"], capsys)
    assert code == 0
    assert packet["read"]["intent"] == "重点解释设计取舍"
    assert packet["media"]["status"] == "kept_for_read"
    assert Path(packet["media"]["dir"]).exists()
    assert (Path(packet["media"]["dir"]) / "vsum-run.json").exists()


def test_default_download_triggers_even_with_transcript(vsum, offline_run, tmp_path, capsys):
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    code, packet, _ = run_cli(vsum, tmp_path, transcript, [], capsys)
    assert code == 0
    assert offline_run["download_calls"] == 1
    assert packet["pipeline"]["video_download"] == "ok"
    assert packet["media"]["status"] == "cleaned"
    assert not Path(packet["media"]["dir"] or "/nonexistent").exists()


def test_video_file_reuses_local_no_download(vsum, offline_run, tmp_path, capsys):
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    local_video = tmp_path / "user-video.mp4"
    local_video.write_bytes(b"user-video")
    code, packet, _ = run_cli(vsum, tmp_path, transcript, ["--video-file", str(local_video)], capsys)
    assert code == 0
    assert offline_run["download_calls"] == 0
    assert packet["artifacts"]["video_file"] == str(local_video)
    assert local_video.exists()


def test_download_failure_visible_artifacts_kept(vsum, offline_run, tmp_path, capsys):
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    offline_run["download_fails"] = True
    code, packet, _ = run_cli(vsum, tmp_path, transcript, ["--read"], capsys)
    assert code == 1
    assert packet["pipeline"]["video_download"] == "failed"
    assert "simulated download failure" in packet["media"]["error"]
    # transcript artifacts survive
    assert Path(packet["artifacts"]["transcript_text"]).exists()
    assert packet["read"]["status"] == "pending"


def test_openai_key_present_changes_nothing(vsum, offline_run, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(vsum, "openai_response", None, raising=False)  # must not exist anymore
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    code, packet, _ = run_cli(vsum, tmp_path, transcript, ["--read"], capsys)
    assert code == 0
    assert "readable_provider" not in packet.get("pipeline", {})
    assert "transcript_readable" not in packet.get("artifacts", {})


def test_no_download_without_any_transcript_fails_clearly(vsum, offline_run, tmp_path):
    out = tmp_path / "out"
    code = vsum.main([
        "run", "https://example.com/watch?v=abc123",
        "--no-download", "--out-dir", str(out),
        "--readable-out-dir", str(tmp_path / "clippings"),
        "--tmp-dir", str(tmp_path / "tmpmedia"),
        "--asr", "none",
    ])
    assert code == 1


def test_run_dirs_are_unique_per_run(vsum, offline_run, tmp_path, capsys):
    """Regression: packet path comes from stdout, so each run reads its own packet."""
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    _, packet1, path1 = run_cli(vsum, tmp_path, transcript, ["--keep-media"], capsys)
    _, packet2, path2 = run_cli(vsum, tmp_path, transcript, ["--keep-media"], capsys)
    assert path1 != path2
    assert packet1["artifacts"]["run_dir"] != packet2["artifacts"]["run_dir"]
    assert packet1["media"]["dir"] != packet2["media"]["dir"]
    assert Path(packet1["media"]["dir"]).exists() and Path(packet2["media"]["dir"]).exists()
    # each packet's artifacts point back at its own run
    assert Path(packet1["artifacts"]["run_dir"]) in path1.parents
    assert Path(packet2["artifacts"]["run_dir"]) in path2.parents
