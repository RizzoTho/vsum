# vsum

中文说明: [README.zh.md](README.zh.md)

For people who learn from video — Bilibili, YouTube, Xiaohongshu — and would rather read than scrub a timeline. Getting a clean, readable transcript out of a video URL is fiddly: every platform hides captions differently, ASR hallucinates on silence, and half the tools quietly download media you never asked for. `vsum` grew out of my own knowledge workflow, where the transcript — not the video file — is the artifact worth keeping. AI doesn't replace the judgment of what's worth reading; it just gets you to the readable text much faster.

`vsum` turns one public video URL plus a reading intent into local transcript artifacts: a normalized raw transcript, a readable Markdown version, and a machine-readable run record. The pipeline is subtitle-first — it only touches media when platform captions don't exist, and only downloads when you explicitly allow it.

## Install

Requires Python 3.10+ and [yt-dlp](https://github.com/yt-dlp/yt-dlp) on PATH. Optional, enabled when present:

- `ffmpeg` + `whisper` CLI — local ASR fallback when a platform has no captions
- `OPENAI_API_KEY` — readable-transcript cleanup via the OpenAI API (otherwise a basic offline cleanup runs)

```bash
git clone <this-repo> && cd vsum
ln -s "$PWD/bin/vsum" ~/.local/bin/vsum   # or add bin/ to PATH
```

## Usage

```bash
# Read public metadata first, no download
vsum probe "https://www.youtube.com/watch?v=..."

# Build transcript artifacts; --intent states what you want from the video
vsum run "https://www.bilibili.com/video/BV..." --intent "turn this into a readable Chinese transcript"
```

When no captions exist you can supply your own source instead of downloading:

```bash
vsum run "<url>" --intent "<purpose>" --transcript notes.srt
vsum run "<url>" --intent "<purpose>" --video-file local.mp4
vsum run "<url>" --intent "<purpose>" --download          # explicit opt-in to yt-dlp download
```

## Configuration

Output locations and models are configurable via CLI flags or environment variables:

| Setting | Flag | Env var | Default |
|---|---|---|---|
| Raw outputs (transcript, packet, media) | `--out-dir` | `VSUM_OUT_ROOT` | `./outputs/vsum/` |
| Readable Markdown output | `--readable-out-dir` | `VSUM_READABLE_ROOT` | `<workspace>/wiki/Clippings/` |
| Intermediate media temp dir | `--tmp-dir` | `VSUM_TMP_DIR` | system temp dir, cleaned after each run |
| Whisper model for local ASR | `--whisper-model` | `VSUM_WHISPER_MODEL` | `small` |
| Model for readable cleanup | `--readable-model` | `VSUM_READABLE_MODEL` | `gpt-4.1-mini` |

Readable output is a blog-style structured article and lands in the current workspace's `wiki/Clippings/` by default, matching a note vault that keeps one clipping per video. Point `VSUM_READABLE_ROOT` elsewhere once if you want a different vault. `--readable agent` writes no readable file and lets the executing agent turn the raw transcript into the blog-style article itself, which is useful when you want the agent's own writing rather than an API call. Intermediate media (downloaded video, extracted audio, ASR output) is written to a global temp dir and removed after each run, so the workspace never accumulates large media files; `--keep-media` keeps them for debugging.

## Layout

```
bin/      the vsum CLI (single-file Python)
skill/    agent skill wrapper (SKILL.md + platform playbook)
agents/   interface declaration for agent runtimes
scripts/  daily smoke test against live platform links
specs/    design notes
```

## Limitations

- Never bypasses logins, paywalls, DRM, or private content; Xiaohongshu usually needs browser cookies (`--cookies-from-browser`) or a local file.
- Subtitle quality is whatever the platform provides; rolling auto-captions are de-overlapped but not re-punctuated unless the OpenAI cleanup runs.
- Whisper fallback filters known Chinese hallucination phrases, but ASR output on noisy audio is best-effort.
- Fails visibly when no transcript path succeeds — it will not silently return partial artifacts.

## License

[MIT](LICENSE)
