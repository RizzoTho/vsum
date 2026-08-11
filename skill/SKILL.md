# Vsum

`vsum` turns one public video URL plus a reading intent into local transcript artifacts. The shared pipeline is subtitle-first, then local media or an explicitly approved CLI download.

## Output Contract

```text
packet.json                 machine-readable run record
transcript.txt              normalized raw transcript
<title>.md                  readable blog-style article (not a verbatim transcript)
```

Raw and diagnostic outputs live under the current workspace's `outputs/vsum/`. Readable output lands in the current workspace's `wiki/Clippings/` by default; `VSUM_READABLE_ROOT` or `--readable-out-dir` can redirect it to another note vault. Never claim a Heptabase write.

Intermediate media (downloaded video, extracted audio, ASR output) lives under a global temp dir, not in the workspace, and is cleaned after each run unless `--keep-media` is set. The workspace only keeps the transcript artifacts.

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
- Xiaohongshu: accept `xiaohongshu.com` and `xhslink.com` links. Expect no official transcript; probe first, then use an approved cookie path, local file, or approved download.
- Never bypass login, paywalls, DRM, private content, or platform restrictions.
- Fail visibly when no transcript path succeeds. Do not silently downgrade or claim missing artifacts.

## Readable Output Style

The readable Markdown is a blog-style article, not a verbatim transcript. With `--readable openai` the model structures the transcript into topic sections with `##` headings, lists, and blockquotes, fixes obvious ASR typos, and writes in a书面 style while keeping every core point and example. The `basic` fallback merges the transcript into paragraphs without restructuring. With `--readable agent` vsum writes no readable file: the raw transcript is ready and the executing agent turns it into the blog-style article itself, following the style rules above. Frontmatter keeps `clippings` plus cleaned hashtags from the source description.

## Verification

After a successful run, verify all reported artifacts:

```bash
test -s "<transcript.txt path>"
test -s "<transcript-readable.md path>"
python3 -m json.tool "<packet.json path>" >/dev/null
```

Report the three printed paths. If `readable: skipped`, say only the raw transcript was produced. If `readable: agent`, the raw transcript is ready and the agent itself writes the blog-style article.
