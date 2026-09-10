#!/usr/bin/env python3
"""Create reusable video transcript packets from public media URLs or local files."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
READABLE_INSTRUCTIONS = PROJECT_ROOT / "references" / "READABLE.md"
CONFIG_PATH = PROJECT_ROOT / ".env"
CONFIG_DEFAULTS = {
    "VSUM_OUT_ROOT": "outputs/vsum",
    "VSUM_READABLE_ROOT": "wiki/Clippings",
    "VSUM_TMP_DIR": str(Path(tempfile.gettempdir()) / "vsum"),
    "VSUM_WHISPER_MODEL": "small",
}
CONFIG_FLAGS = {
    "VSUM_OUT_ROOT": "out_dir",
    "VSUM_READABLE_ROOT": "readable_out_dir",
    "VSUM_TMP_DIR": "tmp_dir",
    "VSUM_WHISPER_MODEL": "whisper_model",
}
DEFAULT_READ_INTENT = "将视频完整整理成可直接阅读的中文文章，保留核心观点、论证、例子和必要限定。"
SUBTITLE_LANG_PRIORITY = ("zh-Hans", "zh-CN", "zh-Hant", "zh-TW", "zh", "en-orig", "en")
BILIBILI_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
MEDIA_MARKER = "vsum-run.json"
# Removed CLI flags and their migration hints. They are rejected before parsing.
REMOVED_FLAGS = {
    "--intent": "阅读目的已并入 --read：python3 <skill-dir>/scripts/vsum.py run <url> --read [阅读目的]",
    "--readable": "内置 openai/basic 文章生成已移除。要成文请用 --read [目的]，由调用 agent 按 references/READABLE.md 写作。",
    "--readable-model": "内置 openai 文章生成已移除，该参数不再存在。成文请用 --read [目的]。",
    "--chunk-chars": "分块参数仅服务已移除的内置生成路径。成文请用 --read [目的]。",
    "--overlap-chars": "分块参数仅服务已移除的内置生成路径。成文请用 --read [目的]。",
}
ENVIRONMENT_CUES = (
    "music",
    "background music",
    "applause",
    "laughter",
    "noise",
    "silence",
    "音乐",
    "背景音乐",
    "掌声",
    "笑声",
    "噪音",
    "静默",
)
# whisper-large-v3 Chinese training-data contamination: these phrases surface
# during silence or outro music even though the audio never contains them.
# https://huggingface.co/openai/whisper-large-v3/discussions/165
KNOWN_HALLUCINATION_PHRASES = (
    "请不吝点赞订阅转发打赏支持明镜与点点栏目",
)
TRADITIONAL_CHAR_VARIANTS = {
    "请": "請",
    "点": "點",
    "赞": "贊讚",
    "订": "訂",
    "阅": "閱",
    "转": "轉",
    "发": "發",
    "赏": "賞",
    "镜": "鏡",
    "与": "與",
    "栏": "欄",
}


class BriefError(Exception):
    """User-facing pipeline error."""


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def log(message: str) -> None:
    eprint(f"[vsum] {message}")


def read_config() -> dict[str, str]:
    """Read only this installation's .env as data, never as shell code."""
    try:
        content = CONFIG_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError) as exc:
        raise BriefError(f"Cannot read configuration {CONFIG_PATH}: {exc}") from exc
    values: dict[str, str] = {}
    for number, line in enumerate(content.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition("=")
        key = key.strip()
        if not separator or key not in CONFIG_DEFAULTS or key in values:
            raise BriefError(f"{CONFIG_PATH}:{number}: unknown, duplicate, or malformed setting: {key}")
        try:
            parts = shlex.split(raw, comments=True)
        except ValueError as exc:
            raise BriefError(f"{CONFIG_PATH}:{number}: {exc}") from exc
        if len(parts) != 1 or not parts[0].strip():
            raise BriefError(f"{CONFIG_PATH}:{number}: expected one non-empty value; quote paths with spaces")
        values[key] = parts[0]
    return values


def effective_config() -> tuple[dict[str, str], dict[str, str]]:
    local = read_config()
    values, sources = {}, {}
    for key, default in CONFIG_DEFAULTS.items():
        if key in os.environ:
            value, source = os.environ[key], "environment"
        elif key in local:
            value, source = local[key], str(CONFIG_PATH)
        else:
            value, source = default, "default"
        if not value.strip():
            raise BriefError(f"{key} from {source} must not be blank")
        values[key], sources[key] = value, source
    return values, sources


def configure_run(args: argparse.Namespace) -> None:
    values, sources = effective_config()
    for key, attr in CONFIG_FLAGS.items():
        explicit = getattr(args, attr)
        value = explicit if explicit is not None else values[key]
        source = "argument" if explicit is not None else sources[key]
        if not str(value).strip():
            raise BriefError(f"{key} from {source} must not be blank")
        resolved = value if attr == "whisper_model" else Path(value).expanduser().resolve()
        setattr(args, attr, resolved)
        log(f"config: {key}={resolved} ({source})")


def run_doctor(args: argparse.Namespace) -> int:
    values, sources = effective_config()
    print(f"skill: {PROJECT_ROOT}")
    print(f"workspace: {Path.cwd()}")
    print(f"config: {CONFIG_PATH} ({'present' if CONFIG_PATH.exists() else 'not initialized; using defaults'})")
    for key, value in values.items():
        resolved = value if key == "VSUM_WHISPER_MODEL" else Path(value).expanduser().resolve()
        print(f"{key}: {resolved} ({sources[key]})")
    missing = False
    for name, required in (("yt-dlp", True), ("ffmpeg", False), ("whisper", False)):
        path = shutil.which(name)
        print(f"{name}: {path or ('MISSING (required)' if required else 'not installed (optional)')}")
        missing |= required and path is None
    for path in (PROJECT_ROOT / "SKILL.md", READABLE_INSTRUCTIONS):
        present = path.is_file() and path.stat().st_size > 0
        print(f"resource: {path} ({'OK' if present else 'MISSING'})")
        missing |= not present
    return 1 if missing else 0


def run_init(args: argparse.Namespace) -> int:
    lines = [
        "# vsum installation preferences. Parsed as data, not sourced by a shell.",
        "# Relative paths resolve from the calling workspace. Absolute paths stay fixed.",
        "# Arguments > process environment > this file > built-in defaults.",
    ]
    for key, attr in CONFIG_FLAGS.items():
        value = str(getattr(args, attr))
        if not value.strip() or "\n" in value or "\r" in value:
            raise BriefError(f"{key} must be a non-empty single-line value")
        lines.append(f"{key}={shlex.quote(value)}")
    try:
        with CONFIG_PATH.open("x", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except FileExistsError as exc:
        raise BriefError(f"Configuration already exists: {CONFIG_PATH}. Edit it explicitly; init never overwrites it.") from exc
    except OSError as exc:
        raise BriefError(f"Cannot initialize {CONFIG_PATH}: {exc}") from exc
    print(f"config: created {CONFIG_PATH}")
    print("next: run doctor from the intended workspace to verify dependencies and resolved paths")
    return 0


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def human_size(path: Path) -> str:
    if not path.exists():
        return "missing"
    size = path.stat().st_size
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def transcript_stats(text: str) -> str:
    lines = len([line for line in text.splitlines() if line.strip()])
    return f"{len(text)} chars, {lines} lines"


def run_command(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() if result.stderr else result.stdout.strip()
        raise BriefError(f"Command failed: {' '.join(cmd[:3])} ...\n{detail}")
    return result


def tool_path(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise BriefError(f"Missing tool: {name}")
    return found


def add_cookie_args(cmd: list[str], cookies_from_browser: str | None) -> list[str]:
    if cookies_from_browser:
        cmd.extend(["--cookies-from-browser", cookies_from_browser])
    return cmd


def add_platform_args(cmd: list[str], platform: str) -> list[str]:
    if platform == "bilibili":
        cmd.extend(["--user-agent", BILIBILI_USER_AGENT, "--referer", "https://www.bilibili.com/"])
    return cmd


def dump_metadata(url: str, cookies_from_browser: str | None) -> dict[str, Any]:
    log("metadata: yt-dlp probe started")
    yt_dlp = tool_path("yt-dlp")
    cmd = [
        yt_dlp,
        "--dump-single-json",
        "--no-warnings",
        "--skip-download",
    ]
    add_platform_args(cmd, platform_from_url(url))
    add_cookie_args(cmd, cookies_from_browser)
    cmd.append(url)
    result = run_command(cmd)
    try:
        meta = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BriefError(f"yt-dlp returned non-JSON output: {exc}") from exc
    log("metadata: yt-dlp probe finished")
    return meta


def platform_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "xiaohongshu"
    if "bilibili.com" in host or "b23.tv" in host:
        return "bilibili"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    return re.sub(r"[^a-z0-9]+", "-", host).strip("-") or "media"


def stable_id(meta: dict[str, Any], url: str) -> str:
    for key in ("id", "display_id", "webpage_url_basename"):
        value = str(meta.get(key) or "").strip()
        if value:
            return clean_slug(value)
    return uuid.uuid5(uuid.NAMESPACE_URL, url).hex[:12]


def clean_slug(value: str, fallback: str = "media") -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug[:80] or fallback


def safe_format(fmt: dict[str, Any]) -> dict[str, Any]:
    keep = [
        "format_id",
        "format",
        "ext",
        "resolution",
        "width",
        "height",
        "fps",
        "filesize",
        "filesize_approx",
        "duration",
        "tbr",
        "abr",
        "vbr",
        "vcodec",
        "acodec",
        "protocol",
    ]
    return {key: fmt.get(key) for key in keep if fmt.get(key) is not None}


def safe_metadata(meta: dict[str, Any], url: str) -> dict[str, Any]:
    safe = {
        "source_url": url,
        "platform": platform_from_url(url),
        "extractor": meta.get("extractor") or meta.get("extractor_key"),
        "id": meta.get("id"),
        "display_id": meta.get("display_id"),
        "title": meta.get("title") or meta.get("fulltitle"),
        "description": meta.get("description"),
        "duration": meta.get("duration"),
        "uploader": meta.get("uploader"),
        "uploader_id": meta.get("uploader_id"),
        "upload_date": meta.get("upload_date"),
        "webpage_url": meta.get("webpage_url") or url,
        "original_url": meta.get("original_url") or url,
        "tags": meta.get("tags") or [],
        "subtitles": sorted((meta.get("subtitles") or {}).keys()),
        "automatic_captions": sorted((meta.get("automatic_captions") or {}).keys()),
        "format_count": len(meta.get("formats") or []),
        "formats": [safe_format(fmt) for fmt in (meta.get("formats") or [])],
    }
    return {key: value for key, value in safe.items() if value not in (None, "", [])}


def source_dir_for(out_root: Path, meta: dict[str, Any], url: str) -> Path:
    platform = platform_from_url(url)
    if meta.get("extractor_key") == "BiliBili":
        platform = "bilibili"
    if meta.get("extractor_key") == "XiaoHongShu":
        platform = "xiaohongshu"
    return out_root / f"{platform}-{stable_id(meta, url)}"


def write_json(path: Path, data: Any) -> None:
    """Atomic JSON write: temp file in the same directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BriefError(f"Cannot read packet {path}: {exc}") from exc


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def existing_transcript(source_dir: Path) -> Path | None:
    return first_existing(
        [
            source_dir / "transcript.srt",
            source_dir / "transcript.vtt",
            source_dir / "transcript.txt",
        ]
    )


def copy_transcript(src: Path, source_dir: Path) -> Path:
    if not src.exists():
        raise BriefError(f"Transcript file not found: {src}")
    suffix = src.suffix.lower() or ".txt"
    dst = source_dir / f"transcript{suffix}"
    if src.resolve() != dst.resolve():
        shutil.copyfile(src, dst)
    return dst


def subtitle_candidates(meta: dict[str, Any]) -> list[tuple[str, str]]:
    manual = set((meta.get("subtitles") or {}).keys())
    automatic = set((meta.get("automatic_captions") or {}).keys())
    candidates: list[tuple[str, str]] = []

    for language in SUBTITLE_LANG_PRIORITY:
        if language in manual:
            candidates.append((language, "manual"))

    original_auto = [language for language in automatic if language.endswith("-orig")]
    for language in sorted(original_auto):
        if (language, "automatic") not in candidates:
            candidates.append((language, "automatic"))

    for language in SUBTITLE_LANG_PRIORITY:
        if language in automatic and (language, "automatic") not in candidates:
            candidates.append((language, "automatic"))

    return candidates


def try_download_subtitles(
    url: str,
    source_dir: Path,
    cookies_from_browser: str | None,
    meta: dict[str, Any],
) -> Path | None:
    candidates = subtitle_candidates(meta)
    if not candidates:
        log("subtitle: platform reports no supported subtitles")
        return None
    log("subtitle: candidates=" + ",".join(f"{language}:{kind}" for language, kind in candidates))
    yt_dlp = tool_path("yt-dlp")
    platform = platform_from_url(url)
    for language, kind in candidates:
        output_template = source_dir / f"subtitle-{language}.%(ext)s"
        cmd = [
            yt_dlp,
            "--skip-download",
            "--write-sub" if kind == "manual" else "--write-auto-sub",
            "--sub-langs",
            language,
            "--sub-format",
            "vtt",
            "-o",
            str(output_template),
        ]
        add_platform_args(cmd, platform)
        add_cookie_args(cmd, cookies_from_browser)
        cmd.append(url)
        result = run_command(cmd, capture=True, check=False)
        files = sorted(source_dir.glob(f"subtitle-{language}*.vtt"))
        if result.returncode != 0 or not files:
            detail = (result.stderr or result.stdout or "unknown yt-dlp error").strip().splitlines()[-1]
            log(f"subtitle: {language} failed: {detail}")
            continue
        dst = source_dir / "transcript.vtt"
        shutil.copyfile(files[0], dst)
        log(f"subtitle: selected {language}:{kind}; saved {dst}")
        return dst
    log("subtitle: all candidates failed")
    return None


def download_video(url: str, media_dir: Path, cookies_from_browser: str | None) -> Path:
    existing = sorted(media_dir.glob("video.*"))
    if existing:
        log(f"video: using cached file {existing[0]} ({human_size(existing[0])})")
        return existing[0]
    log("video: downloading with yt-dlp")
    yt_dlp = tool_path("yt-dlp")
    cmd = [
        yt_dlp,
        "-f",
        "bv*+ba/best",
        "--merge-output-format",
        "mp4",
        "-o",
        str(media_dir / "video.%(ext)s"),
    ]
    add_platform_args(cmd, platform_from_url(url))
    add_cookie_args(cmd, cookies_from_browser)
    cmd.append(url)
    run_command(cmd, capture=False)
    created = sorted(media_dir.glob("video.*"))
    if not created:
        raise BriefError("yt-dlp finished but no video file was created")
    log(f"video: saved {created[0]} ({human_size(created[0])})")
    return created[0]


def ensure_video_file(path: Path) -> Path:
    if not path.exists():
        raise BriefError(f"Video file not found: {path}")
    resolved = path.resolve()
    log(f"video: using local file {resolved} ({human_size(resolved)})")
    return resolved


def extract_audio(video_file: Path, media_dir: Path) -> Path:
    audio = media_dir / "audio.m4a"
    if audio.exists() and audio.stat().st_size > 0:
        log(f"audio: using cached file {audio} ({human_size(audio)})")
        return audio
    log("audio: extracting with ffmpeg")
    ffmpeg = tool_path("ffmpeg")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(video_file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "64k",
        str(audio),
    ]
    run_command(cmd, capture=True)
    if not audio.exists() or audio.stat().st_size == 0:
        raise BriefError("ffmpeg finished but no audio file was created")
    log(f"audio: saved {audio} ({human_size(audio)})")
    return audio


def resolve_asr_provider(choice: str) -> str:
    if choice != "auto":
        return choice
    if shutil.which("whisper"):
        return "whisper"
    return "none"


def transcribe(audio_file: Path, media_dir: Path, provider: str, model: str) -> Path:
    provider = resolve_asr_provider(provider)
    if provider == "none":
        raise BriefError(
            "No transcript source available. Pass --transcript, --no-download with existing text, or install the whisper CLI."
        )
    if provider == "whisper":
        log(f"asr: whisper started model={model}")
        whisper = tool_path("whisper")
        cmd = [
            whisper,
            str(audio_file),
            "--model",
            model,
            "--language",
            "Chinese",
            "--output_format",
            "srt",
            "--output_dir",
            str(media_dir),
        ]
        run_command(cmd, capture=False)
        generated = media_dir / f"{audio_file.stem}.srt"
        if not generated.exists():
            raise BriefError("whisper finished but no transcript file was created")
        dst = media_dir / "transcript.srt"
        if generated.resolve() != dst.resolve():
            shutil.copyfile(generated, dst)
        log(f"asr: transcript saved {dst}")
        return dst
    raise BriefError(f"Unsupported ASR provider: {provider}")


def transcript_to_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".srt":
        text = parse_srt(raw)
    elif suffix == ".vtt":
        text = parse_vtt(raw)
    else:
        text = raw.strip()
    return remove_known_hallucinations(text)


def hallucination_pattern(phrase: str) -> str:
    parts = []
    for char in phrase:
        variants = TRADITIONAL_CHAR_VARIANTS.get(char)
        parts.append(f"[{char}{variants}]" if variants else re.escape(char))
    return r"[\s,，、]*".join(parts)


def remove_known_hallucinations(text: str) -> str:
    for phrase in KNOWN_HALLUCINATION_PHRASES:
        text = re.sub(hallucination_pattern(phrase), " ", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def parse_captions_time(value: str) -> float | None:
    value = value.strip()
    match = re.fullmatch(r"(\d+):(\d{1,2}):(\d{1,2})[.,](\d{1,3})", value)
    if match:
        hours, minutes, seconds, millis = (int(part) for part in match.groups())
        return hours * 3600 + minutes * 60 + seconds + millis / (10 ** len(match.group(4)))
    match = re.fullmatch(r"(\d{1,2}):(\d{1,2})[.,](\d{1,3})", value)
    if match:
        minutes, seconds, millis = (int(part) for part in match.groups())
        return minutes * 60 + seconds + millis / (10 ** len(match.group(3)))
    return None


def raw_caption_blocks(raw: str) -> list[tuple[float, float, str]]:
    """Per-cue (start, end, text) blocks without rolling-caption merging."""
    blocks: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n").strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        timing = next((line for line in lines if "-->" in line), None)
        if not timing:
            continue
        raw_start, _, raw_end = timing.partition("-->")
        start = parse_captions_time(raw_start.split()[0] if raw_start.split() else raw_start)
        end = parse_captions_time(raw_end.split()[0] if raw_end.split() else raw_end)
        if start is None or end is None:
            continue
        text_lines = [line for line in lines if "-->" not in line]
        text = " ".join(clean_caption_text(line) for line in text_lines).strip()
        if text:
            blocks.append((start, end, text))
    return blocks


def build_segments(transcript_path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Return (segments, reason). Segments only exist for timed caption sources."""
    raw = transcript_path.read_text(encoding="utf-8", errors="replace")
    suffix = transcript_path.suffix.lower()
    if suffix == ".srt":
        blocks = raw_caption_blocks(raw)
    elif suffix == ".vtt":
        cleaned = raw.replace("\r\n", "\n")
        cleaned = re.sub(r"^WEBVTT[^\n]*\n", "", cleaned)
        cleaned = re.sub(r"^(?:Kind|Language):[^\n]*\n", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\nNOTE .*?(?=\n\n|\Z)", "\n", cleaned, flags=re.DOTALL)
        blocks = raw_caption_blocks(cleaned)
    else:
        return None, "plain-text transcript without timing; no segments were inferred"
    if not blocks:
        return None, f"{suffix.strip('.')} source contained no parsable timed cues"
    segments = [
        {"start": round(start, 3), "end": round(end, 3), "text": text}
        for start, end, text in blocks
    ]
    return segments, None


def parse_srt(raw: str) -> str:
    entries: list[str] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n").strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].isdigit():
            lines = lines[1:]
        if not lines:
            continue
        text_lines = lines[1:]
        if "-->" not in lines[0]:
            text_lines = lines
        text = " ".join(clean_caption_text(line) for line in text_lines).strip()
        if text:
            entries.append(text)
    return merge_rolling_captions(entries)


def parse_vtt(raw: str) -> str:
    cleaned = raw.replace("\r\n", "\n")
    cleaned = re.sub(r"^WEBVTT[^\n]*\n", "", cleaned)
    cleaned = re.sub(r"^(?:Kind|Language):[^\n]*\n", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\nNOTE .*?(?=\n\n|\Z)", "\n", cleaned, flags=re.DOTALL)
    return parse_srt(cleaned)


def clean_caption_text(line: str) -> str:
    line = re.sub(r"<\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?>", "", line)
    line = re.sub(r"<[^>]+>", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def merge_rolling_captions(cues: list[str]) -> str:
    emitted: list[str] = []
    for cue in cues:
        tokens = cue.split()
        if not tokens:
            continue
        comparable_emitted = [token.casefold() for token in emitted]
        comparable_tokens = [token.casefold() for token in tokens]
        max_overlap = min(len(emitted), len(tokens))
        overlap = 0
        for size in range(max_overlap, 0, -1):
            if comparable_emitted[-size:] == comparable_tokens[:size]:
                overlap = size
                break
        emitted.extend(tokens[overlap:])
    text = " ".join(emitted).strip()
    if not text:
        raise BriefError("Subtitle normalization produced empty text")
    return text


def remove_environment_cues(text: str) -> str:
    alternatives = "|".join(re.escape(cue) for cue in ENVIRONMENT_CUES)
    pattern = rf"(?:\[\s*(?:{alternatives})\s*\]|【\s*(?:{alternatives})\s*】)"
    cleaned = re.sub(pattern, "", text, flags=re.IGNORECASE)
    lines = []
    for line in cleaned.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        line = re.sub(r"\s+([,.;:!?，。；：！？])", r"\1", line)
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    shortened = value[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return shortened or value[:limit]


def format_yt_date(value: str) -> str:
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def readable_path_for(root: Path, metadata: dict[str, Any]) -> Path:
    title = str(metadata.get("title") or metadata.get("id") or "Readable Transcript")
    filename = re.sub(r'[<>:"/\\|?*\n]+', "-", title)
    filename = re.sub(r"-\s+", " ", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .-")[:120] or "Readable Transcript"
    return root / f"{filename}.md"


def write_media_marker(media_dir: Path, packet_path: Path, run_dir: Path) -> None:
    """Ownership marker: finalize may only clean media it can prove it owns."""
    media_dir.mkdir(parents=True, exist_ok=True)
    write_json(media_dir / MEDIA_MARKER, {
        "packet": str(packet_path.resolve()),
        "run_dir": str(run_dir.resolve()),
    })


def media_owned_by(media_dir: Path, packet_path: Path) -> bool:
    marker = media_dir / MEDIA_MARKER
    if not marker.exists():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("packet") == str(packet_path.resolve())


def print_probe(safe: dict[str, Any]) -> None:
    print(f"platform: {safe.get('platform', 'unknown')}")
    print(f"extractor: {safe.get('extractor', 'unknown')}")
    print(f"id: {safe.get('id') or safe.get('display_id') or 'unknown'}")
    print(f"title: {safe.get('title', 'untitled')}")
    if safe.get("duration") is not None:
        print(f"duration: {safe['duration']} seconds")
    print(f"formats: {safe.get('format_count', 0)}")
    subtitles = safe.get("subtitles") or []
    auto = safe.get("automatic_captions") or []
    print(f"subtitles: {', '.join(subtitles) if subtitles else 'none'}")
    print(f"automatic_captions: {', '.join(auto) if auto else 'none'}")
    best = safe.get("formats", [])[-1] if safe.get("formats") else None
    if best:
        print(f"best_seen_format: {best.get('format') or best.get('format_id')} {best.get('resolution', '')}".strip())


def run_probe(args: argparse.Namespace) -> int:
    meta = dump_metadata(args.url, args.cookies_from_browser)
    safe = safe_metadata(meta, args.url)
    log(
        "probe: "
        f"platform={safe.get('platform', 'unknown')} "
        f"extractor={safe.get('extractor', 'unknown')} "
        f"id={safe.get('id') or safe.get('display_id') or 'unknown'}"
    )
    if args.json:
        print(json.dumps(safe, ensure_ascii=False, indent=2))
    else:
        print_probe(safe)
    return 0


def run_brief(args: argparse.Namespace) -> int:
    read_intent: str | None = None
    if args.read is not None:
        read_intent = args.read.strip()
        if not read_intent:
            raise BriefError(
                "--read received a blank reading purpose. Either pass the flag alone for the default purpose, "
                'or provide a real purpose, for example: python3 <skill-dir>/scripts/vsum.py run <url> --read "整理成中文文章，重点解释演示流程"'
            )
    read_pending = read_intent is not None
    if read_pending and not READABLE_INSTRUCTIONS.is_file():
        raise BriefError(f"Writing instructions missing: {READABLE_INSTRUCTIONS}. Install the complete skill directory.")

    out_root = args.out_dir.resolve()
    log("run: started")
    try:
        meta = dump_metadata(args.url, args.cookies_from_browser)
    except BriefError as exc:
        if not args.video_file:
            raise
        log(f"metadata: yt-dlp probe unsupported for this URL ({exc}); using --video-file without remote metadata")
        meta = {}
    safe = safe_metadata(meta, args.url)
    source_dir = source_dir_for(out_root, meta, args.url)
    # Per-run media directory: parallel runs never share or delete each other's media.
    media_dir = args.tmp_dir / f"{platform_from_url(args.url)}-{stable_id(meta, args.url)}-{now_stamp()}-{uuid.uuid4().hex[:6]}"
    run_dir = source_dir / "runs" / f"{now_stamp()}-{uuid.uuid4().hex[:6]}"
    source_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    log(
        "source: "
        f"platform={safe.get('platform', 'unknown')} "
        f"title={safe.get('title', 'untitled')}"
    )
    log(f"output: source_dir={source_dir}")
    log(f"output: run_dir={run_dir}")
    log(f"output: media_dir={media_dir}")

    write_json(source_dir / "metadata.json", safe)
    log(f"metadata: saved {source_dir / 'metadata.json'}")
    if args.keep_raw_metadata:
        write_json(source_dir / "raw-yt-dlp-metadata.json", meta)
        log(f"metadata: raw saved {source_dir / 'raw-yt-dlp-metadata.json'}")

    transcript_path: Path | None = None
    transcript_source = "missing"
    video_file: Path | None = None
    audio_file: Path | None = None
    asr_provider: str | None = None
    video_error: str | None = None

    if args.transcript:
        transcript_path = copy_transcript(args.transcript, source_dir)
        transcript_source = "provided"
        log(f"transcript: using provided file {transcript_path}")
    else:
        transcript_path = existing_transcript(source_dir)
        if transcript_path:
            transcript_source = "cached"
            log(f"transcript: using cached file {transcript_path}")
        else:
            transcript_path = try_download_subtitles(args.url, source_dir, args.cookies_from_browser, meta)
            if transcript_path:
                transcript_source = "subtitle"
                log(f"transcript: using subtitle file {transcript_path}")

    # Video acquisition is independent of the transcript path: default is to
    # fetch the video so article illustration can pull frames from it.
    if args.video_file:
        video_file = ensure_video_file(args.video_file)
    elif not args.no_download:
        media_dir.mkdir(parents=True, exist_ok=True)
        try:
            video_file = download_video(args.url, media_dir, args.cookies_from_browser)
        except BriefError as exc:
            video_error = str(exc)
            log(f"video: DOWNLOAD FAILED: {exc}")
            log("video: keeping subtitle/transcript artifacts already obtained; packet records the failure")

    if transcript_path is None:
        log("transcript: unavailable before ASR")
        if video_file is None:
            if args.no_download:
                raise BriefError(
                    "No transcript and --no-download skips video download, so there is no ASR source. "
                    "Pass --transcript, provide --video-file, or drop --no-download."
                )
            raise BriefError(
                f"Video download failed and no subtitles were available, so there is no ASR source. {video_error}"
            )
        media_dir.mkdir(parents=True, exist_ok=True)
        audio_file = extract_audio(video_file, media_dir)
        asr_provider = resolve_asr_provider(args.asr)
        transcript_path = transcribe(audio_file, media_dir, args.asr, args.whisper_model)
        transcript_source = f"asr:{asr_provider}"
        transcript_srt = source_dir / "transcript.srt"
        if transcript_path.resolve() != transcript_srt.resolve():
            shutil.copyfile(transcript_path, transcript_srt)
        transcript_path = transcript_srt

    transcript_text = transcript_to_text(transcript_path)
    transcript_txt = source_dir / "transcript.txt"
    transcript_txt.write_text(transcript_text.strip() + "\n", encoding="utf-8")
    log(f"transcript: normalized {transcript_txt} ({transcript_stats(transcript_text)})")

    segments, segments_note = build_segments(transcript_path)
    segments_path: Path | None = None
    if segments is not None:
        segments_path = source_dir / "segments.json"
        write_json(segments_path, segments)
        log(f"segments: saved {segments_path} ({len(segments)} cues)")
    else:
        log(f"segments: unavailable ({segments_note})")

    article_path = readable_path_for(args.readable_out_dir.resolve(), safe)
    run_id = uuid.uuid4().hex
    read_obj: dict[str, Any] | None = None
    if read_pending:
        assets_dir = article_path.parent / "images" / source_dir.name / run_dir.name
        read_obj = {
            "status": "pending",
            "intent": read_intent,
            "input": str(transcript_txt.resolve()),
            "segments": str(segments_path.resolve()) if segments_path else None,
            "segments_note": segments_note,
            "output": str(article_path),
            "assets": str(assets_dir),
            "instructions": str(READABLE_INSTRUCTIONS.resolve()),
        }

    packet: dict[str, Any] = {
        "schema_version": "0.3",
        "run_id": run_id,
        "created_at": iso_now(),
        "source": safe,
        "artifacts": {
            "source_dir": str(source_dir.resolve()),
            "run_dir": str(run_dir.resolve()),
            "media_dir": str(media_dir) if media_dir.exists() else None,
            "metadata": str((source_dir / "metadata.json").resolve()),
            "transcript": str(transcript_path.resolve()),
            "transcript_text": str(transcript_txt.resolve()),
            "segments": str(segments_path.resolve()) if segments_path else None,
            "video_file": str(video_file) if video_file else None,
            "audio_file": str(audio_file) if audio_file else None,
        },
        "pipeline": {
            "transcript_source": transcript_source,
            "asr_provider": asr_provider,
            "whisper_model": args.whisper_model if asr_provider == "whisper" else None,
            "video_download": "skipped" if args.no_download else ("failed" if video_error else "ok"),
            "tmp_dir": str(args.tmp_dir),
        },
    }
    if read_obj is not None:
        # read.output is the expected target only; the article is not an artifact yet.
        packet["read"] = read_obj
    packet["artifacts"] = {key: value for key, value in packet["artifacts"].items() if value}
    packet["pipeline"] = {key: value for key, value in packet["pipeline"].items() if value is not None}
    packet_path = run_dir / "packet.json"
    if media_dir.exists():
        write_media_marker(media_dir, packet_path, run_dir)
    write_json(packet_path, packet)
    latest = source_dir / "latest-packet.json"
    write_json(latest, packet)
    log(f"packet: saved {packet_path}")

    media_status = "none"
    if media_dir.exists():
        if args.keep_media:
            media_status = "kept_by_flag"
        elif read_pending:
            # A pending read task keeps the video so the agent can pull frames.
            media_status = "kept_for_read"
            log(f"tmp: media kept for pending read task: {media_dir}")
        else:
            shutil.rmtree(media_dir, ignore_errors=False)
            media_status = "cleaned"
            log(f"tmp: cleaned {media_dir}")
    packet["media"] = {"dir": str(media_dir) if media_dir.exists() else None, "status": media_status}
    if video_error:
        packet["media"]["error"] = video_error
    write_json(packet_path, packet)
    write_json(latest, packet)
    log("run: finished")

    print(f"packet: {packet_path}")
    print(f"transcript: {transcript_txt}")
    if read_pending:
        print("read: pending (transcript materials ready; the article has NOT been generated)")
        print(f"read output target: {article_path}")
        print(f"read assets dir: {read_obj['assets']}")
        print(
            "next: read packet.json and references/READABLE.md, write the article to the target, "
            f"then run: {shlex.join([sys.executable, str(Path(__file__).resolve()), 'finalize', str(packet_path)])}"
        )
    else:
        print("read: not requested (pass --read [purpose] to create an article task)")
    if video_error:
        print(f"video: FAILED ({video_error}); transcript artifacts were kept and the failure is recorded in the packet")
        return 1
    return 0


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks and inline code spans so examples are not parsed as images."""
    lines = []
    fence = None
    for line in text.splitlines():
        if fence:
            if line.strip().startswith(fence):
                fence = None
            continue
        open_fence = line.strip()
        if open_fence.startswith("```") or open_fence.startswith("~~~"):
            fence = open_fence[:3]
            continue
        lines.append(line)
    no_fences = "\n".join(lines)
    return re.sub(r"`[^`\n]*`", "", no_fences)


def collect_reference_defs(text: str) -> dict[str, str]:
    """Markdown reference definitions: [label]: target "title" (full and collapsed forms)."""
    defs: dict[str, str] = {}
    pattern = re.compile(
        r"^[ \t]{0,3}\[([^\]\[]+)\]:\s*(?:<([^>\n]*)>|([^`\s]+))(?:\s+[\"'(]([^\")']*)[\"')])?[ \t]*$",
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        target = (match.group(2) or match.group(3) or "").strip()
        if target:
            defs[match.group(1).strip().casefold()] = target
    return defs


REMOTE_TARGET_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def inline_image_target(inner: str) -> str | None:
    inner = inner.strip()
    if not inner:
        return None
    if inner.startswith("<"):
        end = inner.find(">")
        if end == -1:
            return None
        return inner[1:end].strip()
    if inner.startswith(('"', "'")):
        quote = inner[0]
        end = inner.find(quote, 1)
        if end == -1:
            return None
        return inner[1:end].strip()
    # bare target, optionally followed by a quoted title
    match = re.match(r"^(\S+)(?:\s+[\"'](.*?)[\"'])?[ \t]*$", inner)
    if not match:
        return None
    return match.group(1).strip("\"'")


def extract_local_image_targets(text: str) -> list[str]:
    """Local targets of every real markdown image: inline, full/collapsed/shortcut reference.

    Raises BriefError on image syntax that cannot be resolved, instead of skipping it.
    Remote (scheme-qualified) targets and plain anchors are skipped.
    """
    working = strip_code_blocks(text)
    defs = collect_reference_defs(working)
    targets: list[str] = []
    image_scan = re.compile(
        r"!\[([^\]]*)\]"
        r"(\(\s*<[^>\n]*>[ \t]*(?:[\"'][^\"'\n]*[\"'])?[ \t]*\)|\([^)\n]*\)|\[[^\]\n]*\])?"
    )
    for match in image_scan.finditer(working):
        alt = match.group(1)
        tail = (match.group(2) or "").strip()
        if tail.startswith("("):
            target = inline_image_target(tail[1:-1])
            if target is None:
                raise BriefError(
                    f"Cannot parse inline image syntax near: {match.group(0)[:80]!r}. "
                    "Use ![alt](<path>) or ![alt](path \"title\") form."
                )
        elif tail.startswith("[") and tail.endswith("]"):
            label = tail[1:-1].strip() or alt
            key = label.casefold()
            if key not in defs:
                raise BriefError(
                    f"Image reference {match.group(0)[:60]!r} has no matching definition "
                    f"[{label}]: <path>. Add the definition or fix the label."
                )
            target = defs[key]
        else:
            key = alt.strip().casefold()
            if not key or key not in defs:
                raise BriefError(
                    f"Image syntax {match.group(0)[:60]!r} cannot be resolved: no inline target "
                    "and no matching reference definition. Write ![alt](path) or define [alt]: <path>."
                )
            target = defs[key]
        if not target:
            continue
        if REMOTE_TARGET_RE.match(target) or target.startswith("#"):
            continue
        targets.append(urllib.parse.unquote(target))
    return targets


def is_path_within(path: Path, ancestor: Path) -> bool:
    """True if path is ancestor itself or lives underneath it (symlinks already resolved)."""
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def parse_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
    """Minimal frontmatter parser: scalars plus flat lists. Returns (data, body)."""
    match = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)(.*)\Z", text, re.DOTALL)
    if not match:
        return None, text
    data: dict[str, Any] = {}
    current_list: str | None = None
    for line in match.group(1).splitlines():
        if re.match(r"^[ \t]+-[ \t]+", line):
            if current_list:
                item = re.sub(r"^[ \t]+-[ \t]+", "", line).strip().strip("\"'")
                data[current_list].append(item)
            continue
        key_match = re.match(r"^([A-Za-z_][\w-]*)[ \t]*:[ \t]*(.*)$", line)
        if not key_match:
            continue
        key = key_match.group(1).lower()
        value = key_match.group(2).strip()
        if value == "":
            data[key] = []
            current_list = key
        else:
            data[key] = value.strip("\"'")
            current_list = None
    return data, match.group(2)


def has_substantive_body(body: str) -> bool:
    """Body text exists beyond frontmatter, headings, comments, images, and reference definitions."""
    cleaned = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
    kept: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # reference definitions are metadata, not body text
        if re.match(r"\[[^\]\[]+\]:", stripped):
            continue
        # drop lines that are only one or more images
        without_images = re.sub(r"!\[[^\]]*\]\([^)]*\)|!\[[^\]]*\]\[[^\]]*\]", "", stripped)
        without_images = re.sub(r"!\[[^\]]*\]", "", without_images)
        if without_images.strip():
            kept.append(without_images)
    return any(re.search(r"[A-Za-z0-9\u4e00-\u9fff]", line) for line in kept)


def validate_article_against_packet(article_text: str, packet: dict[str, Any]) -> None:
    """Minimum deterministic acceptance per READABLE.md output contract."""
    frontmatter, body = parse_frontmatter(article_text)
    if frontmatter is None:
        raise BriefError("Article has no frontmatter block (--- ... ---). READABLE.md requires one.")
    tags = frontmatter.get("tags")
    if not isinstance(tags, list) or "clippings" not in tags:
        raise BriefError("Article frontmatter tags must include 'clippings'.")

    source = packet.get("source") or {}
    expected_url = str(source.get("webpage_url") or source.get("source_url") or "").strip()
    article_url = str(frontmatter.get("source") or "").strip()
    if expected_url:
        if not article_url:
            raise BriefError(f"Article frontmatter has no source, but the packet knows one: {expected_url}")
        if article_url != expected_url:
            raise BriefError(
                f"Article source {article_url!r} does not match the packet source {expected_url!r}."
            )
    expected_date = format_yt_date(str(source.get("upload_date") or ""))
    article_date = str(frontmatter.get("published") or "").strip()
    if expected_date and article_date and article_date != expected_date:
        raise BriefError(
            f"Article published date {article_date!r} does not match the packet upload date {expected_date!r}."
        )
    expected_author = str(source.get("uploader") or "").strip()
    authors = frontmatter.get("author")
    author_list = authors if isinstance(authors, list) else ([authors] if authors else [])
    if expected_author and author_list and expected_author not in author_list:
        raise BriefError(
            f"Article author {author_list} does not mention the known uploader {expected_author!r}."
        )
    if not has_substantive_body(body):
        raise BriefError(
            "Article has no substantive body text after removing frontmatter, headings, comments, "
            "and images. A title or picture-only file is not a finished article."
        )


def sync_latest_mirror(source_dir: Path, packet: dict[str, Any], packet_path: Path) -> str:
    """Sync latest-packet.json only while it still points at this run. Never clobbers newer runs."""
    latest = source_dir / "latest-packet.json"
    run_id = packet.get("run_id")
    if not latest.exists():
        log(f"latest: mirror missing at {latest}; leaving it absent (only the run operation creates it)")
        return "missing"
    try:
        latest_data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log(f"latest: WARNING mirror unreadable, not overwriting unknown state ({exc}): {latest}")
        return "corrupt"
    if latest_data.get("run_id") != run_id:
        log(
            "latest: mirror points at a newer run "
            f"({latest_data.get('run_id')!r} != {run_id!r}); not overwriting it with this packet"
        )
        return "superseded"
    # Narrow the check-then-write race: re-read immediately before the atomic replace.
    try:
        reread = json.loads(latest.read_text(encoding="utf-8"))
        if reread.get("run_id") != run_id:
            log("latest: mirror changed during finalize; not overwriting it with this packet")
            return "superseded"
    except (OSError, json.JSONDecodeError):
        log("latest: mirror changed during finalize and is now unreadable; not overwriting it")
        return "corrupt"
    write_json(latest, packet)
    return "synced"


def run_finalize(args: argparse.Namespace) -> int:
    packet_path = args.packet.resolve()
    packet = load_json(packet_path)
    read = packet.get("read")
    if not isinstance(read, dict):
        raise BriefError(f"This packet has no read task (no --read was used): {packet_path}")
    if read.get("status") != "pending":
        raise BriefError(f"Read task is not pending (status={read.get('status')!r}); nothing to finalize.")

    article_path = Path(read["output"])
    if not article_path.exists():
        raise BriefError(f"Article not found at the expected target: {article_path}. The read task is still pending.")
    article_text = article_path.read_text(encoding="utf-8", errors="replace")
    if not article_text.strip():
        raise BriefError(f"Article at {article_path} is empty; finalize refuses to mark it done.")
    validate_article_against_packet(article_text, packet)

    media = packet.get("media") or {}
    media_dir = media.get("dir")
    media_to_clean: Path | None = None
    if (
        media_dir
        and media.get("status") == "kept_for_read"
        and Path(media_dir).exists()
        and media_owned_by(Path(media_dir), packet_path)
    ):
        media_to_clean = Path(media_dir).resolve()
    assets_raw = read.get("assets")
    assets_dir = Path(assets_raw).resolve() if assets_raw else None

    bad_refs: list[str] = []
    pending_images: list[Path] = []
    for ref in extract_local_image_targets(article_text):
        resolved = (article_path.parent / ref).resolve()
        if not resolved.exists() or resolved.stat().st_size == 0:
            bad_refs.append(ref)
            continue
        if media_to_clean and is_path_within(resolved, media_to_clean):
            destination = f"{assets_dir}/" if assets_dir else "a persistent assets directory"
            raise BriefError(
                f"Article references {ref!r}, which lives inside the temp media directory "
                f"{media_to_clean} that finalize would delete. Move the image to {destination} "
                "(see packet read.assets), update the reference, then finalize again."
            )
        if assets_dir and not is_path_within(resolved, assets_dir):
            raise BriefError(
                f"Article references {ref!r}, which is outside the persistent assets directory "
                f"{assets_dir} (packet read.assets). Keep formal images under it so the article "
                "and its resources stay together."
            )
        pending_images.append(resolved)
    if bad_refs:
        raise BriefError(
            "Article references missing or empty local images: "
            + "; ".join(bad_refs)
            + ". Fix or remove them before finalize."
        )

    packet["read"]["status"] = "done"
    packet["read"]["completed_at"] = iso_now()
    packet.setdefault("artifacts", {})
    packet["artifacts"]["article"] = str(article_path.resolve())
    if pending_images:
        packet["artifacts"]["article_images"] = [str(path) for path in pending_images]

    if media_to_clean:
        try:
            shutil.rmtree(media_to_clean)
            packet["media"]["status"] = "cleaned"
            packet["media"]["dir"] = None
            log(f"tmp: cleaned {media_to_clean}")
        except OSError as exc:
            packet["media"]["status"] = "cleanup_failed"
            packet["media"]["error"] = str(exc)
            log(f"tmp: WARNING cleanup failed for {media_to_clean}: {exc}")

    # Post-cleanup guarantee: every referenced image still exists and is non-empty.
    vanished = [str(path) for path in pending_images if not (path.exists() and path.stat().st_size > 0)]
    if vanished:
        raise BriefError(
            "After media cleanup these referenced images are missing or empty: "
            + "; ".join(vanished)
            + ". The packet was NOT marked done."
        )

    write_json(packet_path, packet)
    mirror_state = "no-source-dir"
    source_dir = packet.get("artifacts", {}).get("source_dir")
    if source_dir:
        mirror_state = sync_latest_mirror(Path(source_dir), packet, packet_path)

    print(f"finalize: article accepted {article_path}")
    print(f"finalize: images kept: {len(pending_images)}")
    print(f"finalize: latest-packet mirror: {mirror_state}")
    print(f"finalize: read status=done, packet updated {packet_path}")
    return 0


def probe_video_duration(video_file: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(video_file)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def run_frame(args: argparse.Namespace) -> int:
    packet_path = args.packet.resolve()
    packet = load_json(packet_path)
    artifacts = packet.get("artifacts") or {}
    video_ref = artifacts.get("video_file")
    if not video_ref:
        raise BriefError(f"Packet has no video_file artifact; nothing to extract frames from: {packet_path}")
    video_file = Path(video_ref)
    if not video_file.exists():
        raise BriefError(f"Video file recorded in the packet is missing: {video_file}")
    if args.at < 0:
        raise BriefError(f"--at must be non-negative, got {args.at}")
    duration = probe_video_duration(video_file)
    if duration is not None and args.at >= duration:
        raise BriefError(f"--at {args.at}s is beyond the video duration ({duration:.2f}s): {video_file}")

    media_dir = (packet.get("media") or {}).get("dir")
    if args.out:
        out_path = args.out.resolve()
    else:
        base = Path(media_dir) if media_dir and Path(media_dir).exists() else Path(artifacts["run_dir"])
        out_path = base / "frames" / f"frame-{args.at:.2f}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = tool_path("ffmpeg")
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        f"{args.at:.3f}",
        "-i",
        str(video_file),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(out_path),
    ]
    run_command(cmd, capture=True)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise BriefError(f"ffmpeg finished but no frame was written to {out_path}")

    frames_log = Path(artifacts["run_dir"]) / "frames.json"
    try:
        records = json.loads(frames_log.read_text(encoding="utf-8")) if frames_log.exists() else []
    except json.JSONDecodeError:
        records = []
    records.append({
        "created_at": iso_now(),
        "packet": str(packet_path),
        "video": str(video_file),
        "at": args.at,
        "image": str(out_path),
    })
    write_json(frames_log, records)

    print(f"frame: {out_path}")
    print(f"frame source: {video_file} @ {args.at:.3f}s")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vsum.py",
        description=(
            "Probe Bilibili, Xiaohongshu, and YouTube URLs, download the video by default, "
            "and build reusable transcript packets. --read creates a pending article task "
            "for the calling agent, which writes the article per references/READABLE.md and "
            "finishes with this script's finalize operation."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local dependencies and configuration without network access.")
    doctor.set_defaults(func=run_doctor)
    init = subparsers.add_parser("init", help="Create the skill-local .env; existing configuration is never overwritten.")
    for key, attr in CONFIG_FLAGS.items():
        init.add_argument("--" + attr.replace("_", "-"), default=CONFIG_DEFAULTS[key])
    init.set_defaults(func=run_init)

    probe = subparsers.add_parser("probe", help="Read public metadata without downloading media.")
    probe.add_argument("url")
    probe.add_argument("--cookies-from-browser", metavar="BROWSER", help="Use browser cookies, for example chrome.")
    probe.add_argument("--json", action="store_true", help="Print sanitized metadata JSON.")
    probe.set_defaults(func=run_probe)

    run = subparsers.add_parser("run", help="Build transcript packets; pass --read [purpose] to create an article task.")
    run.add_argument("url")
    run.add_argument(
        "--read",
        nargs="?",
        const=DEFAULT_READ_INTENT,
        default=None,
        metavar="PURPOSE",
        help=(
            "Create a pending article task for the calling agent. Bare --read uses the default purpose; "
            '--read "..." records your purpose verbatim. Put the URL before --read so the optional '
            "value is not swallowed."
        ),
    )
    run.add_argument("--video-file", type=Path, help="Local video file; reused instead of downloading.")
    run.add_argument("--transcript", type=Path, help="Existing transcript file: txt, srt, or vtt.")
    run.add_argument(
        "--no-download",
        action="store_true",
        help="Skip video download; metadata and subtitles may still use the network.",
    )
    run.add_argument("--cookies-from-browser", metavar="BROWSER", help="Use browser cookies, for example chrome.")
    run.add_argument("--out-dir", type=Path, default=None)
    run.add_argument(
        "--readable-out-dir",
        type=Path,
        default=None,
        help="Where the agent-written article is expected to land. Defaults to the workspace's wiki/Clippings/.",
    )
    run.add_argument(
        "--tmp-dir",
        type=Path,
        default=None,
        help="Where intermediate media (video, audio, ASR output) lives while processing. Defaults to the global system temp dir; cleaned after finalize unless --keep-media or a read task is pending.",
    )
    run.add_argument(
        "--keep-media",
        action="store_true",
        help="Keep intermediate media in --tmp-dir after the run instead of cleaning it.",
    )
    run.add_argument("--asr", choices=["auto", "whisper", "none"], default="auto")
    run.add_argument("--whisper-model", default=None)
    run.add_argument("--keep-raw-metadata", action="store_true", help="Also save raw yt-dlp JSON, including direct media URLs.")
    run.set_defaults(func=run_brief)

    finalize = subparsers.add_parser(
        "finalize",
        help="Accept a finished article, verify it and its local images, then update the packet.",
    )
    finalize.add_argument("packet", type=Path, help="Path to the packet.json with a pending read task.")
    finalize.set_defaults(func=run_finalize)

    frame = subparsers.add_parser(
        "frame",
        help="Extract one frame from the packet's local video for article illustration.",
    )
    frame.add_argument("packet", type=Path, help="Path to the packet.json with a video_file artifact.")
    frame.add_argument("--at", type=float, required=True, help="Timestamp in seconds.")
    frame.add_argument("--out", type=Path, help="Output image path. Defaults to a frames/ dir next to the run media.")
    frame.set_defaults(func=run_frame)
    return parser


def migration_check(argv: list[str]) -> list[str]:
    """Reject removed flags with migration hints; downgrade --download to a no-op warning."""
    remaining: list[str] = []
    for arg in argv:
        flag = arg.split("=", 1)[0]
        if flag in REMOVED_FLAGS:
            raise BriefError(f"{flag} has been removed. Migration: {REMOVED_FLAGS[flag]}")
        if flag == "--download":
            log("--download is a no-op now: video download is the default. Use --no-download to skip it.")
            continue
        remaining.append(arg)
    return remaining


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        argv = migration_check(argv)
        parser = build_parser()
        args = parser.parse_args(argv)
        if args.command == "run":
            configure_run(args)
        return int(args.func(args) or 0)
    except BriefError as exc:
        eprint(f"vsum: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
