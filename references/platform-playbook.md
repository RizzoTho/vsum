# Platform Playbook

`VSUM_SCRIPT` denotes the absolute path to this skill’s `scripts/vsum.py`, resolved from the root SKILL.md. Keep the calling workspace as the working directory.

Load this reference only after the default subtitle-first run needs a fallback or a non-default flag.

## Platform behavior

### YouTube

Prefer manual subtitles, then original automatic captions such as `en-orig`, then translated captions. Request candidates one at a time so a translated-caption HTTP 429 cannot terminate the whole subtitle path.

### Bilibili

Metadata, subtitle, and media requests use a browser User-Agent plus `Referer: https://www.bilibili.com/`. If the platform exposes no usable subtitle, use a local video and ASR. Do not assume higher-resolution member-only formats are available.

### Xiaohongshu

Both full URLs and `xhslink.com` short links route here. Public extraction may fail because of platform controls. Chrome cookies are opt-in session material. Without approval, ask for a Downie video or existing transcript. This skill handles video transcription only; image-note ingestion and content analysis stay out of scope.

## Input and fallback commands

```bash
# Existing transcript skips ASR
python3 "$VSUM_SCRIPT" run "<url>" --read "<purpose>" --transcript "<file>"

# Local media, normally from Downie
python3 "$VSUM_SCRIPT" run "<url>" --read "<purpose>" --video-file "<video.mp4>"

# Skip video download; metadata and subtitles still use the network
python3 "$VSUM_SCRIPT" run "<url>" --no-download

# Explicitly approved browser session access
python3 "$VSUM_SCRIPT" run "<url>" --read "<purpose>" --cookies-from-browser chrome
```

## Useful flags

- `--read [PURPOSE]`: create a pending article task. Bare `--read` uses the default purpose; the article is written by the calling agent per [READABLE.md](READABLE.md), then closed with `python3 "$VSUM_SCRIPT" finalize`.
- `--asr auto|whisper|none`: `auto` uses Whisper when installed.
- `--whisper-model`: defaults to `small`; first use may download the model.
- `--no-download`: skip video download; metadata and subtitles may still use the network. Video download is otherwise on by default.
- `--out-dir`: override the current workspace's `outputs/vsum/` root.
- `--readable-out-dir`: override the default `wiki/Clippings/` article target.
- `--tmp-dir`: where intermediate media lives while processing; defaults to the global system temp dir (`VSUM_TMP_DIR` env override), one subdirectory per run.
- `--keep-media`: keep intermediate media after finalize/run instead of cleaning it.
- `--keep-raw-metadata`: debugging only; saves direct media URLs and other raw metadata.

The script prepares materials; article writing belongs to the executing agent.
