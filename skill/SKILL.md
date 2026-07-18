---
name: vsum
description: "Use when Codex needs to inspect a Bilibili, Xiaohongshu, YouTube, or public video URL and turn it into local transcript artifacts with the `vsum` CLI: probe metadata, prefer platform subtitles, connect a local video, run Whisper ASR, or produce `transcript.txt` plus `transcript-readable.md`. Not for Heptabase writes, short summaries, login/paywall/DRM bypass, or bulk media downloads."
---

# Vsum

`vsum` turns one public video URL plus a reading intent into local transcript artifacts. The shared pipeline is subtitle-first, then local media or an explicitly approved CLI download.

## Output Contract

```text
packet.json                 machine-readable run record
transcript.txt              normalized raw transcript
<title>.md                  readable transcript, not a summary
```

Raw and diagnostic outputs normally live under the current workspace's `outputs/vsum/`. Readable output lands in the same per-run directory by default; `VSUM_READABLE_ROOT` or `--readable-out-dir` can redirect it to a note vault. Never claim a Heptabase write.

## Workflow

1. Probe an unfamiliar URL:

```bash
vsum probe "<url>"
```

2. Run with a clear reading purpose. `vsum` tries manual subtitles, original automatic captions, then translated captions:

```bash
vsum run "<url>" --intent "整理成可直接阅读的中文转写稿"
```

3. If subtitles are unavailable, prefer a user-provided transcript or Downie video:

```bash
vsum run "<url>" --intent "<purpose>" --transcript "<file>"
vsum run "<url>" --intent "<purpose>" --video-file "<video.mp4>"
```

4. Use `--download` only when the user explicitly approves CLI media download. Browser cookies are session material; explain the access and obtain explicit approval before `--cookies-from-browser chrome`.

Read [Platform Playbook](references/platform-playbook.md) only when choosing platform fallbacks or non-default flags.

## Decision Rules

- YouTube: prefer native tracks such as `en-orig`; one rate-limited language must not hide another usable caption. Strip cue timestamps and merge rolling automatic-caption overlap before any readable provider runs.
- Bilibili: send a browser User-Agent and Bilibili Referer. Fall back to local ASR when subtitles are absent.
- Xiaohongshu: accept `xiaohongshu.com` and `xhslink.com`. Expect no official transcript; probe first, then use an approved cookie path, local file, or approved download.
- Never bypass login, paywalls, DRM, private content, or platform restrictions.
- Fail visibly when no transcript path succeeds. Do not silently downgrade or claim missing artifacts.

## Verification

After a successful run, verify all reported artifacts:

```bash
test -s "<transcript.txt path>"
test -s "<transcript-readable.md path>"
python3 -m json.tool "<packet.json path>" >/dev/null
```

Report the three printed paths. If `readable: skipped`, say only the raw transcript was produced.
