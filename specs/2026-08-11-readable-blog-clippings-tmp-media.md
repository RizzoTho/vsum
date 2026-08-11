# Vsum readable blog style, Clippings default, and global temp media

## Goal

Three behavior changes from Riza's workflow feedback after processing a Xiaohongshu video:

1. The readable Markdown should be a blog-style structured article, not a verbatim transcript.
2. Readable output defaults to the current workspace's `wiki/Clippings/`, matching the OKF clipping owner already documented in the earlier readable design.
3. Intermediate media (downloaded video, extracted audio, ASR output) moves to a global temp dir so the workspace never accumulates large files, and is cleaned after each run.

## Changes

### Readable blog style

- OpenAI readable prompt now asks for a structured article: `##`/`###` topic sections, lists and blockquotes where useful, written prose, ASR typo fixes, no timestamps, no summary paragraph, no action advice. Chunked runs: the first chunk opens with a lead-in, later chunks continue sections without repeating the lead-in.
- `basic` fallback still merges the transcript into paragraphs without restructuring; it cannot produce topic sections without a model.
- `agent` mode writes no readable file; the executing agent turns the raw transcript into the blog-style article itself.
- Frontmatter tags now keep `clippings` plus cleaned hashtags scraped from the source description (deduped, max 6 tags). Source `tags` metadata is merged in too.

### Clippings default

- `DEFAULT_READABLE_ROOT` is now `<workspace>/wiki/Clippings/` (cwd-relative), not the per-run source dir. `VSUM_READABLE_ROOT` or `--readable-out-dir` still overrides it.
- Input spelling `wiki/clippings/` is normalized to `wiki/Clippings/` to avoid case-dependent duplicate owners.

### Global temp media

- New `--tmp-dir` flag and `VSUM_TMP_DIR` env var; default is `tempfile.gettempdir()/vsum`.
- Download, audio extraction, and ASR output write into `<tmp-dir>/<platform>-<id>/`.
- The normalized `transcript.srt` is copied back into the source dir; `transcript.txt`, `metadata.json`, and `packet.json` stay in the workspace.
- After a successful run the temp media dir is removed unless `--keep-media` is set. `packet.json` records `media_dir` and `tmp_dir` for debugging.

## Verification

- `python3 -m py_compile bin/vsum`.
- End-to-end run against a local Xiaohongshu video with `--video-file`, isolated `--out-dir`/`--readable-out-dir`/`--tmp-dir`: readable lands in the clips dir with `clippings` plus description hashtags; temp media dir exists during the run and is gone after it; source dir keeps `transcript.srt`, `transcript.txt`, `metadata.json`, `packet.json`.
