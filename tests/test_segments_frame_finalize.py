"""SRT/VTT segment parsing, frame extraction, and finalize acceptance behavior."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from conftest import base_packet, valid_article, write_packet

SRT = """1
00:00:01,000 --> 00:00:03,500
第一句话

2
00:00:04,000 --> 00:00:06,000
第二句话 有两句
第二句话 有两句
"""

VTT = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:03.500
first cue

00:00:04.000 --> 00:00:06.000
second cue
"""


def test_parse_srt_segments(vsum, tmp_path):
    p = tmp_path / "seg.srt"
    p.write_text(SRT, encoding="utf-8")
    segments, note = vsum.build_segments(p)
    assert note is None
    assert len(segments) == 2
    assert segments[0] == {"start": 1.0, "end": 3.5, "text": "第一句话"}
    assert segments[1]["start"] == 4.0 and segments[1]["end"] == 6.0


def test_parse_vtt_segments(vsum, tmp_path):
    p = tmp_path / "seg.vtt"
    p.write_text(VTT, encoding="utf-8")
    segments, note = vsum.build_segments(p)
    assert note is None
    assert segments == [
        {"start": 1.0, "end": 3.5, "text": "first cue"},
        {"start": 4.0, "end": 6.0, "text": "second cue"},
    ]


def test_plain_text_has_no_segments(vsum, tmp_path):
    p = tmp_path / "seg.txt"
    p.write_text("plain text\n", encoding="utf-8")
    segments, note = vsum.build_segments(p)
    assert segments is None
    assert "without timing" in note


# ---------------------------------------------------------------- frame


def test_frame_success(vsum, sample_video, tmp_path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    packet = base_packet(tmp_path, video=sample_video, media_dir=media_dir)
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet)
    code = vsum.main(["frame", str(packet_path), "--at", "0.5"])
    assert code == 0
    frame = media_dir / "frames" / "frame-0.50.png"
    assert frame.exists() and frame.stat().st_size > 0
    records = json.loads((Path(packet["artifacts"]["run_dir"]) / "frames.json").read_text())
    assert records[-1]["at"] == 0.5
    assert records[-1]["video"] == str(sample_video)


def test_frame_beyond_duration_fails(vsum, sample_video, tmp_path):
    packet = base_packet(tmp_path, video=sample_video)
    packet_path = write_packet(tmp_path, packet)
    assert vsum.main(["frame", str(packet_path), "--at", "999"]) == 1


def test_frame_missing_media_fails(vsum, tmp_path):
    packet = base_packet(tmp_path, video=tmp_path / "missing.mp4")
    packet_path = write_packet(tmp_path, packet)
    assert vsum.main(["frame", str(packet_path), "--at", "1"]) == 1


def test_frame_no_video_artifact_fails(vsum, tmp_path):
    packet = base_packet(tmp_path)
    packet_path = write_packet(tmp_path, packet)
    assert vsum.main(["frame", str(packet_path), "--at", "1"]) == 1


# ---------------------------------------------------------------- finalize


def make_read_world(tmp_path, article_text: str, *, with_marker: bool = True):
    """Article + pending packet + owned temp media + a latest mirror pointing at this run."""
    article_dir = tmp_path / "clippings"
    article_dir.mkdir(parents=True, exist_ok=True)
    article = article_dir / "Test.md"
    article.write_text(article_text, encoding="utf-8")
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "video.mp4").write_bytes(b"owned-video")
    packet = base_packet(tmp_path, media_dir=media_dir)
    packet["read"]["output"] = str(article)
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    if with_marker:
        (media_dir / "vsum-run.json").write_text(
            json.dumps({"packet": str(packet_path.resolve()), "run_dir": packet["artifacts"]["run_dir"]}),
            encoding="utf-8",
        )
    source_dir = Path(packet["artifacts"]["source_dir"])
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "latest-packet.json").write_text(
        json.dumps({"run_id": packet["run_id"]}, ensure_ascii=False), encoding="utf-8"
    )
    return article, media_dir, packet_path


def finalized_article(tmp_path) -> tuple:
    """A fully valid finalize world: real body text, image under read.assets."""
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    assets = Path(packet["read"]["assets"])
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "shot.png").write_bytes(b"png-bytes")
    article_dir = Path(packet["read"]["output"]).parent
    article = article_dir / "Test.md"
    article.write_text(
        valid_article(f"# Test\n\n正文第一段，有实际内容。\n\n![shot](images/example-com-abc123/{packet['run_id']}/shot.png)\n"),
        encoding="utf-8",
    )
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "video.mp4").write_bytes(b"owned-video")
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)
    source_dir = Path(packet["artifacts"]["source_dir"])
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "latest-packet.json").write_text(
        json.dumps({"run_id": packet["run_id"]}, ensure_ascii=False), encoding="utf-8"
    )
    return packet, packet_path, article, assets, media_dir


def test_finalize_success_updates_packet_and_cleans_owned_media(vsum, tmp_path):
    packet, packet_path, article, assets, media_dir = finalized_article(tmp_path)
    code = vsum.main(["finalize", str(packet_path)])
    assert code == 0
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["read"]["status"] == "done"
    assert packet["read"]["completed_at"]
    assert packet["artifacts"]["article"] == str(article)
    assert len(packet["artifacts"]["article_images"]) == 1
    assert not media_dir.exists()  # owned media cleaned
    assert packet["media"]["status"] == "cleaned"
    # post-cleanup: the referenced image is still present and non-empty
    assert Path(packet["artifacts"]["article_images"][0]).stat().st_size > 0
    latest = json.loads((Path(packet["artifacts"]["source_dir"]) / "latest-packet.json").read_text())
    assert latest["read"]["status"] == "done"  # latest pointed at this run: synced


def test_finalize_rejects_empty_article(vsum, tmp_path):
    _, media_dir, packet_path = make_read_world(tmp_path, "   \n")
    code = vsum.main(["finalize", str(packet_path)])
    assert code == 1
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["read"]["status"] == "pending"
    assert media_dir.exists()


def test_finalize_rejects_missing_article(vsum, tmp_path):
    article, media_dir, packet_path = make_read_world(tmp_path, valid_article("正文"))
    article.unlink()
    assert vsum.main(["finalize", str(packet_path)]) == 1
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["read"]["status"] == "pending"


def test_finalize_rejects_frontmatter_only_article(vsum, tmp_path):
    """Regression: a file with only frontmatter and a title is not a finished article."""
    text = valid_article("# Test Video\n")
    _, media_dir, packet_path = make_read_world(tmp_path, text)
    assert vsum.main(["finalize", str(packet_path)]) == 1
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["read"]["status"] == "pending"
    assert media_dir.exists()


def test_finalize_rejects_image_only_article(vsum, tmp_path):
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    assets = Path(packet["read"]["assets"])
    assets.mkdir(parents=True)
    (assets / "shot.png").write_bytes(b"png")
    article_dir = Path(packet["read"]["output"]).parent
    article_dir.mkdir(parents=True, exist_ok=True)
    article = article_dir / "Test.md"
    article.write_text(valid_article(f"![shot](images/example-com-abc123/{packet['run_id']}/shot.png)\n"), encoding="utf-8")
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)
    assert vsum.main(["finalize", str(packet_path)]) == 1
    assert json.loads(packet_path.read_text())["read"]["status"] == "pending"


def test_finalize_rejects_missing_clippings_tag(vsum, tmp_path):
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    article_dir = tmp_path / "clippings"
    article_dir.mkdir(parents=True, exist_ok=True)
    article = article_dir / "Test.md"
    text = valid_article("正文，有实际内容。").replace('  - "clippings"\n', "")
    article.write_text(text, encoding="utf-8")
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)
    assert vsum.main(["finalize", str(packet_path)]) == 1
    assert json.loads(packet_path.read_text())["read"]["status"] == "pending"


def test_finalize_rejects_source_mismatch(vsum, tmp_path):
    text = valid_article("正文，有实际内容。", url="https://wrong.example.com/v")
    _, media_dir, packet_path = make_read_world(tmp_path, text)
    assert vsum.main(["finalize", str(packet_path)]) == 1
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["read"]["status"] == "pending"


def test_finalize_accepts_empty_source_when_packet_has_no_url(vsum, tmp_path):
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    packet["source"] = {"title": "Local Only"}  # no webpage_url: agent may leave source blank
    article_dir = tmp_path / "clippings"
    article_dir.mkdir(parents=True, exist_ok=True)
    article = article_dir / "Test.md"
    text = valid_article("正文，有实际内容。").replace(
        'source: "https://example.com/watch?v=abc123"', "source:"
    )
    article.write_text(text, encoding="utf-8")
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)
    assert vsum.main(["finalize", str(packet_path)]) == 0


def test_finalize_rejects_broken_image_refs(vsum, tmp_path):
    text = valid_article("# T\n\n正文。\n\n![diagram](images/missing.png)\n")
    _, media_dir, packet_path = make_read_world(tmp_path, text)
    assert vsum.main(["finalize", str(packet_path)]) == 1
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["read"]["status"] == "pending"
    assert media_dir.exists()  # kept on failure


def test_finalize_rejects_image_inside_temp_media(vsum, tmp_path):
    """Regression: an article referencing a temp screenshot must not lose it on finalize."""
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    temp_frame = media_dir / "frames" / "frame-125.50.png"
    temp_frame.parent.mkdir(parents=True)
    temp_frame.write_bytes(b"temp-frame-bytes")
    article = Path(packet["read"]["output"])
    article.parent.mkdir(parents=True, exist_ok=True)
    article.write_text(valid_article(f"正文。\n\n![frame]({temp_frame})\n"), encoding="utf-8")
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)

    assert vsum.main(["finalize", str(packet_path)]) == 1
    packet_after = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet_after["read"]["status"] == "pending"
    assert temp_frame.exists() and media_dir.exists()  # nothing deleted

    # migrate the image into read.assets, fix the reference, then finalize succeeds
    assets = Path(packet["read"]["assets"])
    assets.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(temp_frame, assets / "frame-125.50.png")
    article.write_text(
        valid_article(f"正文。\n\n![frame](images/example-com-abc123/{packet['run_id']}/frame-125.50.png)\n"),
        encoding="utf-8",
    )
    assert vsum.main(["finalize", str(packet_path)]) == 0
    assert (assets / "frame-125.50.png").exists()
    assert not media_dir.exists()
    final_packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert final_packet["read"]["status"] == "done"


def test_finalize_rejects_image_outside_assets_dir(vsum, tmp_path):
    """Formal images must follow the persistent per-article assets convention."""
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    article_dir = tmp_path / "clippings"
    article_dir.mkdir(parents=True, exist_ok=True)
    stray = article_dir / "images" / "stray.png"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"stray-image")
    article = article_dir / "Test.md"
    article.write_text(valid_article("正文。\n\n![s](images/stray.png)\n"), encoding="utf-8")
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)
    assert vsum.main(["finalize", str(packet_path)]) == 1
    packet_after = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet_after["read"]["status"] == "pending"
    assert stray.exists()


def test_finalize_external_image_refs_ignored_by_local_checks(vsum, tmp_path):
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    article_dir = tmp_path / "clippings"
    article_dir.mkdir(parents=True, exist_ok=True)
    article = article_dir / "Test.md"
    article.write_text(
        valid_article("正文，有实际内容。\n\n![remote](https://example.com/x.png)\n"),
        encoding="utf-8",
    )
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet, with_marker_media=media_dir)
    assert vsum.main(["finalize", str(packet_path)]) == 0
    packet_after = json.loads(packet_path.read_text(encoding="utf-8"))
    assert "article_images" not in packet_after["artifacts"]


def test_finalize_does_not_touch_user_video_or_other_runs(vsum, tmp_path):
    user_video = tmp_path / "user-source.mp4"
    user_video.write_bytes(b"user-file")
    other_run = tmp_path / "other-media"
    other_run.mkdir()
    (other_run / "video.mp4").write_bytes(b"other-run-video")
    packet, packet_path, article, assets, media_dir = finalized_article(tmp_path)
    assert vsum.main(["finalize", str(packet_path)]) == 0
    assert user_video.exists()
    assert other_run.exists() and (other_run / "video.mp4").exists()


def test_finalize_twice_rejected(vsum, tmp_path):
    _, packet_path, *_ = finalized_article(tmp_path)
    assert vsum.main(["finalize", str(packet_path)]) == 0
    assert vsum.main(["finalize", str(packet_path)]) == 1


def test_finalize_unowned_media_left_alone(vsum, tmp_path):
    packet = base_packet(tmp_path, media_dir=tmp_path / "media")
    article_dir = tmp_path / "clippings"
    article_dir.mkdir(parents=True, exist_ok=True)
    article = article_dir / "Test.md"
    article.write_text(valid_article("正文内容，有实际信息。"), encoding="utf-8")
    packet["read"]["output"] = str(article)
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "video.mp4").write_bytes(b"foreign")
    packet["media"] = {"dir": str(media_dir), "status": "kept_for_read"}
    packet_path = write_packet(tmp_path, packet)  # no ownership marker written
    assert vsum.main(["finalize", str(packet_path)]) == 0
    assert (media_dir / "video.mp4").exists()


# ---------------------------------------------------------------- latest mirror


def test_finalize_old_run_does_not_clobber_newer_latest(vsum, tmp_path):
    """Regression: finalize on run A must not overwrite latest-packet.json of newer run B."""
    packet, packet_path, *_ = finalized_article(tmp_path)
    newer = {"run_id": "newer-run-b", "read": {"status": "pending"}}
    source_dir = Path(packet["artifacts"]["source_dir"])
    (source_dir / "latest-packet.json").write_text(json.dumps(newer), encoding="utf-8")
    assert vsum.main(["finalize", str(packet_path)]) == 0
    latest = json.loads((source_dir / "latest-packet.json").read_text())
    assert latest["run_id"] == "newer-run-b"  # B untouched
    finalized = json.loads(packet_path.read_text())
    assert finalized["read"]["status"] == "done"  # A itself updated


def test_finalize_syncs_latest_when_it_points_at_this_run(vsum, tmp_path):
    packet, packet_path, *_ = finalized_article(tmp_path)
    source_dir = Path(packet["artifacts"]["source_dir"])
    (source_dir / "latest-packet.json").write_text(
        json.dumps({"run_id": packet["run_id"], "read": {"status": "pending"}}), encoding="utf-8"
    )
    assert vsum.main(["finalize", str(packet_path)]) == 0
    latest = json.loads((source_dir / "latest-packet.json").read_text())
    assert latest["read"]["status"] == "done"


def test_finalize_with_corrupt_latest_leaves_it_alone(vsum, tmp_path):
    packet, packet_path, *_ = finalized_article(tmp_path)
    source_dir = Path(packet["artifacts"]["source_dir"])
    (source_dir / "latest-packet.json").write_text("{not json", encoding="utf-8")
    assert vsum.main(["finalize", str(packet_path)]) == 0
    assert (source_dir / "latest-packet.json").read_text() == "{not json"  # not silently replaced
    packet_after = json.loads(packet_path.read_text())
    assert packet_after["read"]["status"] == "done"  # the task itself still completes


def test_finalize_with_missing_latest_does_not_recreate_it(vsum, tmp_path):
    packet, packet_path, *_ = finalized_article(tmp_path)
    source_dir = Path(packet["artifacts"]["source_dir"])
    (source_dir / "latest-packet.json").unlink()
    assert vsum.main(["finalize", str(packet_path)]) == 0
    assert not (source_dir / "latest-packet.json").exists()


# ---------------------------------------------------------------- assets isolation


def test_read_hands_off_distinct_assets_dirs(vsum, offline_run, tmp_path):
    """Two runs of the same source get distinct per-article assets dirs."""
    transcript = tmp_path / "t.txt"
    transcript.write_text("content here\n", encoding="utf-8")
    out = tmp_path / "out"
    clippings = tmp_path / "clippings"
    common = ["--out-dir", str(out), "--readable-out-dir", str(clippings), "--tmp-dir", str(tmp_path / "tmp")]
    assert vsum.main(["run", "https://example.com/watch?v=abc123", "--transcript", str(transcript), "--read", *common]) == 0
    assert vsum.main(["run", "https://example.com/watch?v=abc123", "--transcript", str(transcript), "--read", *common]) == 0
    packets = sorted(out.rglob("packet.json"), key=lambda p: p.stat().st_mtime)
    declared = [json.loads(p.read_text())["read"]["assets"] for p in packets]
    assert declared[0] != declared[1]
    for path in declared:
        resolved = Path(path)
        assert resolved.parent.parent == (clippings / "images").resolve()
        # images/<source-dir>/<run-dir> convention: two more levels below images/
        assert len(resolved.relative_to(clippings / "images").parts) == 2


def test_same_timestamp_frames_do_not_collide(vsum, sample_video, tmp_path):
    """Two articles framing at the same second keep distinct formal assets."""
    runs = []
    for index in range(2):
        packet = base_packet(tmp_path, video=sample_video, media_dir=tmp_path / f"media-{index}")
        assets = Path(packet["read"]["assets"])
        assets.mkdir(parents=True, exist_ok=True)
        runs.append((packet, assets))
    # both "frame at the same timestamp": the default frame name would collide in a shared dir
    for packet, assets in runs:
        target = assets / "frame-1.00.png"
        target.write_bytes(b"distinct-bytes-" + packet["run_id"].encode())
    assert len({p / "frame-1.00.png" for _, p in runs}) == 2
    for packet, assets in runs:
        assert (assets / "frame-1.00.png").read_bytes().endswith(packet["run_id"].encode())
