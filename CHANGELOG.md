# Changelog

Changes and migration notes.

## Unreleased

### Skill packaging and initialization

- The repository root is now the installable skill: `SKILL.md` is at the root, the runtime moves from `bin/vsum` to `scripts/vsum.py`, and the writing contract lives in `references/READABLE.md`. Install the entire directory; copying only the former `skill/` directory is insufficient.
- Invoke the bundled script with Python from the task workspace. A global `vsum` executable is no longer required or shipped. Existing shell links to `bin/vsum` must be updated or removed by their owner.
- Added agent-guided initialization: `init` creates installation-local `.env` preferences without overwriting existing configuration; `doctor` reports local dependencies, required resources, effective settings, and their sources without network access. Dependency installation remains agent-guided.
- Configuration precedence is explicit run arguments, process environment, installation `.env`, then defaults. Relative paths resolve from the calling workspace; the script does not load unrelated workspace `.env` files or execute shell expressions.
- Replaced the custom `agents/interface.yaml` declaration with `agents/openai.yaml` UI metadata. Updated runtime callers, tests, and skill references to use the bundled script.
- Added `/SPEC/` and local `.env` to Git ignore rules, along with Python environment and test-cache directories. Existing tracked `specs/` history is retained.
- README files now introduce skill installation, initialization, and natural-language requests before direct script usage.

### Changed

- Article writing moves from the CLI to the calling agent. `run --read [PURPOSE]` creates a pending task; the agent follows `skill/READABLE.md`, then submits the article with `vsum finalize`. A successful `run` means materials are ready, not that the article is complete.
- Video download is enabled by default, independently of subtitle availability. `--video-file` reuses a local video; `--no-download` skips video download but still allows metadata and subtitle requests. Download failures produce a nonzero exit code and are recorded in the packet when transcript materials are available.
- Temporary media uses a separate directory for each run. Pending article tasks retain it for frame extraction; successful finalization or a materials-only run cleans owned media. `--keep-media` preserves it, and user-provided source videos are retained.

### Added

- Packet schema `0.3` includes a run ID and an optional `read` task with purpose, input, output, writing instructions, and asset paths. The expected article path becomes an artifact only after finalization.
- `segments.json` preserves SRT/VTT cue timestamps separately from normalized text. Plain-text sources have no fabricated timeline. `vsum frame <packet.json> --at <seconds>` extracts a video frame and records its source in `frames.json`.
- `vsum finalize` checks frontmatter, source metadata, body text, and local images before marking an article task done. These checks do not establish semantic fidelity to the video.
- Offline tests cover CLI migration, material acquisition, task handoff, timed captions, frame extraction, article validation, and media cleanup. The daily platform smoke test now checks transcript materials without video downloads or article generation.

### Fixed

- Finalization requires local article images to resolve inside `read.assets`, under `images/<source-id>/<run-id>/`, and rejects images in temporary media. This separates assets between runs and prevents cleanup from deleting accepted article images.
- Local image validation handles inline, full, collapsed, and shortcut Markdown references; unresolved image syntax fails explicitly. Article validation rejects missing required frontmatter, inconsistent source fields, and documents containing only headings or images.
- Finalizing an older run no longer overwrites a newer `latest-packet.json`. Missing or corrupt mirrors are left untouched. Tests obtain the current packet path from CLI output rather than filesystem traversal order.

### Migration

| Previous | Current |
|---|---|
| `--intent "purpose"` | `--read "purpose"`; put the URL first |
| `--readable auto\|openai\|basic\|agent\|none` | Use `--read` for an agent-written article; omit it for materials only |
| `--readable-model`, `--chunk-chars`, `--overlap-chars` | Removed with built-in article generation |
| `--download` | Download is the default; the flag emits a warning and has no effect |

The CLI no longer calls OpenAI for article generation. `OPENAI_API_KEY` and `VSUM_READABLE_MODEL` no longer select or configure an article-writing path. Removed flags fail with migration guidance; bare `--read` uses the default Chinese reading purpose, while a blank purpose is rejected.
