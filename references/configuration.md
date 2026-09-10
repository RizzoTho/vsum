# Configuration

The script loads only `.env` beside the root `SKILL.md`. It does not search parent directories or read the calling project's `.env`.

Precedence: explicit run arguments, process environment, skill-local `.env`, built-in defaults. Relative paths resolve from the calling workspace; absolute paths stay fixed; `~` expands to the user's home directory. Keep the task workspace as the working directory when invoking the script.

| Setting | Run/init argument | Default |
|---|---|---|
| `VSUM_OUT_ROOT` | `--out-dir` | `outputs/vsum` |
| `VSUM_READABLE_ROOT` | `--readable-out-dir` | `wiki/Clippings` |
| `VSUM_TMP_DIR` | `--tmp-dir` | System temporary directory, under `vsum` |
| `VSUM_WHISPER_MODEL` | `--whisper-model` | `small` |

`init` writes these four preferences to a new `.env`. It does not copy process-environment overrides into the file and never overwrites an existing file. To change installed preferences, edit that file explicitly, then run `doctor` from the intended workspace to inspect effective values. `.env.example` is a template, not a second configuration source.

The file supports one `KEY=value` per line, blank lines, comments starting with `#`, and single- or double-quoted values. Quote paths containing spaces or `#`. Unknown keys, duplicates, blank values, and malformed quoting fail explicitly. Values are literal data: no shell execution, variable interpolation, or `export` statements. Do not store API keys or browser cookies here; this skill needs neither for initialization.

`doctor` checks executable availability for `yt-dlp`, `ffmpeg`, and `whisper`, checks required skill resources, and displays resolved paths. Missing `yt-dlp` or required resources produces a nonzero exit code. Missing optional tools are reported without failing the check. It does not test network access, platform authentication, or model availability, and does not install anything.

Article tasks keep temporary media until finalization. `--keep-media`, `--no-download`, `--asr`, and cookie access are task-specific arguments rather than persistent installation defaults.
