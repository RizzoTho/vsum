---
name: vsum
description: Turn public Bilibili, YouTube, or Xiaohongshu videos into local transcripts or readable articles with video frames. Use when the user provides a video URL to transcribe, read, or keep as a clipping, or asks to initialize vsum.
---

# Vsum

This directory is the complete skill. Resolve `scripts/vsum.py` relative to this SKILL.md and invoke it with Python 3.10+ using its absolute path. In the examples, `VSUM_SCRIPT` means that resolved script path. Do not rely on a global `vsum` command or change into the installation directory: the working directory is the user's task workspace.

## First use and configuration

Run `python3 "$VSUM_SCRIPT" doctor` from the intended workspace on first use or when troubleshooting. It reports dependencies, resources, configuration sources, and resolved output paths without making network requests.

If the installation has no `.env`, guide initialization:

1. Check Python and `yt-dlp`. Explain any missing dependencies and help install them using the user's environment conventions. `ffmpeg` is needed for frames and audio extraction; the `whisper` executable is needed only for local ASR. Do not install Whisper or download models when subtitles suffice.
2. Infer the article destination from the current request or existing workspace instructions. Ask for a destination only when it is still unclear. Use a relative path for output in each calling workspace, or an absolute path for a fixed note vault. Keep transcript and temporary directory defaults unless the user needs otherwise.
3. Run `python3 "$VSUM_SCRIPT" init --readable-out-dir "<destination>"`, then `doctor` again. `init` creates the skill-local `.env` and refuses to overwrite an existing one. It writes preferences only; dependency readiness is checked by `doctor`.

For an existing installation, reuse its preferences. See [configuration.md](references/configuration.md) when changing them. Never source `.env` as shell code. Report initialization and dependency readiness separately if dependencies are missing.

## Process a video

Choose the task from the user's request. An article or clipping uses `--read`; a transcript-only request does not. The user need not supply command flags.

```bash
# Probe an unfamiliar URL without downloading video
python3 "$VSUM_SCRIPT" probe "<url>"

# Transcript materials
python3 "$VSUM_SCRIPT" run "<url>"

# Article; omit the optional purpose to use the default Chinese reading purpose
python3 "$VSUM_SCRIPT" run "<url>" --read "<reading purpose>"
```

Put the URL before `--read`. Video download is enabled by default to support frame extraction, even when subtitles are available. Use `--transcript <file>` for supplied text, `--video-file <file>` to reuse local video, and `--no-download` to skip video download (metadata and subtitles can still use the network). See [platform-playbook.md](references/platform-playbook.md) for platform-specific fallbacks.

Browser cookies are session material: obtain explicit authorization before using `--cookies-from-browser`. Never bypass login, paywalls, DRM, or private content. A failed video download can leave usable transcript materials; report the failure instead of claiming the entire run succeeded.

## Complete an article

A successful `run --read` creates a pending task, not an article. Read the exact packet path printed by the script.

1. Read the packet, the full transcript at `read.input`, and [READABLE.md](references/READABLE.md), the sole writing contract. Use `read.segments` when available; plain-text sources have no timeline.
2. Inspect frames where understanding depends on visuals: `python3 "$VSUM_SCRIPT" frame "<packet.json>" --at <seconds>`. Actually view the extracted images and adjust timestamps as needed.
3. Write the article to `read.output`. Save selected images under `read.assets` with relative article links; temporary frames are not permanent assets. Review the article against the transcript for accuracy and coverage.
4. Run `python3 "$VSUM_SCRIPT" finalize "<packet.json>"`. Fix reported validation failures and retry. Deterministic checks do not replace semantic review.

Pending tasks retain temporary media for frame extraction. Finalization cleans media owned by that run unless `--keep-media` was used. User-supplied video files are preserved.

## Delivery

Report the actual transcript and packet paths. For an article request, also report the article path after successful finalization and verify that the article and its referenced local images remain available. If the task is still pending, state what remains; do not report an intended output path as a completed artifact. Outputs are local files; do not claim an external note-app write.
