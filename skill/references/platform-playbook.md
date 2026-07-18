# Platform Playbook

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
vsum run "<url>" --intent "<purpose>" --transcript "<file>" --readable openai

# Local media, normally from Downie
vsum run "<url>" --intent "<purpose>" --video-file "<video.mp4>"

# Explicitly approved CLI download
vsum run "<url>" --intent "<purpose>" --download

# Explicitly approved browser session access
vsum run "<url>" --intent "<purpose>" --cookies-from-browser chrome
```

## Useful flags

- `--asr auto|whisper|none`: `auto` uses Whisper when installed.
- `--whisper-model`: defaults to `small`; first use may download the model.
- `--readable auto|openai|basic|none`: `auto` uses OpenAI when credentials exist, otherwise basic cleanup.
- `--chunk-chars`: OpenAI cleanup chunk size, default `8000`.
- `--overlap-chars`: keep at `0` for transcript rewriting to avoid repeated paragraphs.
- `--out-dir`: override the current workspace's `outputs/vsum/` root.
- `--readable-out-dir`: override the existing `wiki/Clippings/` readable owner.
- `--keep-raw-metadata`: debugging only; saves direct media URLs and other raw metadata.

Use `--readable openai` for polished Chinese prose when credentials and model calls are acceptable. Use `basic` when local cleanup matters more than polish, and `none` when only raw transcript is requested.
