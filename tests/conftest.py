"""Shared fixtures for offline vsum tests. No real platform network access."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_vsum():
    path = PROJECT_ROOT / "scripts" / "vsum.py"
    loader = importlib.machinery.SourceFileLoader("vsum_module", str(path))
    spec = importlib.util.spec_from_file_location("vsum_module", path, loader=loader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def vsum():
    return load_vsum()


@pytest.fixture(scope="session")
def ffmpeg():
    path = shutil.which("ffmpeg")
    if not path:
        pytest.skip("ffmpeg not available")
    return path


@pytest.fixture(scope="session")
def sample_video(tmp_path_factory, ffmpeg):
    """A 2-second synthetic mp4 so frame extraction runs against real media."""
    out = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        [
            ffmpeg, "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=128x96:rate=10",
            "-pix_fmt", "yuv420p", str(out),
        ],
        check=True, capture_output=True,
    )
    assert out.stat().st_size > 0
    return out


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


def packet_path_from_stdout(stdout: str) -> Path:
    """Parse the packet path from the CLI's own output; no directory-order guessing."""
    match = re.search(r"^packet: (.+)$", stdout, re.MULTILINE)
    assert match, f"no packet line in stdout:\n{stdout}"
    return Path(match.group(1))


def write_packet(tmp_path: Path, packet: dict, *, with_marker_media: Path | None = None) -> Path:
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    if with_marker_media is not None:
        (with_marker_media / "vsum-run.json").write_text(
            json.dumps({"packet": str(path.resolve()), "run_dir": packet["artifacts"]["run_dir"]}),
            encoding="utf-8",
        )
    return path


def valid_article(body: str, url: str = "https://example.com/watch?v=abc123") -> str:
    frontmatter = f"""---
title: "Test Video"
source: "{url}"
author:
  - "someone"
published: "2026-01-02"
created: "2026-09-09"
description: "test"
tags:
  - "clippings"
---

"""
    return frontmatter + body


def base_packet(tmp_path: Path, *, video: Path | None = None, media_dir: Path | None = None) -> dict:
    run_id = uuid.uuid4().hex
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    packet = {
        "schema_version": "0.3",
        "run_id": run_id,
        "artifacts": {
            "source_dir": str(tmp_path / "source"),
            "run_dir": str(run_dir),
            "video_file": str(video) if video else None,
        },
        "source": {
            "webpage_url": "https://example.com/watch?v=abc123",
            "uploader": "someone",
            "upload_date": "20260102",
        },
        "read": {
            "status": "pending",
            "intent": "测试目的",
            "input": str(tmp_path / "transcript.txt"),
            "output": str(tmp_path / "article" / "Test.md"),
            "assets": str(tmp_path / "article" / "images" / "example-com-abc123" / run_id),
            "instructions": "READABLE.md",
        },
        "media": {"dir": str(media_dir) if media_dir else None, "status": "kept_for_read"},
    }
    packet["artifacts"] = {k: v for k, v in packet["artifacts"].items() if v}
    return packet
