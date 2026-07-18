# Vsum readable OKF and caption normalization

## Goal

Make subtitle-backed runs produce a clean, deduplicated `transcript.txt`, then write the readable artifact into the existing OKF clipping owner at `wiki/Clippings/`.

## Data flow

1. Fetch the highest-ranked manual or original automatic subtitle.
2. Parse VTT cues and remove cue timing, positioning, voice/class tags, and inline timestamp tags.
3. Merge rolling automatic-caption cues incrementally. Drop identical adjacent cues; when the next cue extends the previous cue, append only its novel suffix. Preserve deliberate word repetition inside a cue.
4. Write the normalized result to `outputs/vsum/<source>/transcript.txt`.
5. Pass the same normalized text to every `--readable` provider.
6. Write the readable Markdown to `wiki/Clippings/<sanitized-video-title>.md`, while packet and diagnostic artifacts remain in the run directory.

## Readable-only environment cue cleanup

Before either `basic` or `openai` readable processing, remove standalone non-speech caption cues through a small case-insensitive allowlist. Initial English cues are `Music`, `Background music`, `Applause`, `Laughter`, `Noise`, and `Silence`; Chinese equivalents cover `音乐`, `背景音乐`, `掌声`, `笑声`, `噪音`, and `静默`.

The caption track supplies these markers; `vsum` does not invent them. The raw normalized `transcript.txt` keeps the markers as source evidence. Only readable output removes them. Bracketed prose outside the allowlist remains untouched, and the implementation must not delete arbitrary square-bracket content.

## OKF contract

The readable file uses the current clipping fields:

```yaml
---
title: "<video title>"
source: "<canonical URL>"
author:
  - "<uploader when available>"
published: <YYYY-MM-DD when available>
created: <YYYY-MM-DD>
description: "<short source description when available>"
tags:
  - "clippings"
---
```

The existing `wiki/Clippings/` path is authoritative. Input spelling `wiki/clippings/` is normalized to it to avoid case-dependent duplicate owners.

## Error and overwrite behavior

- Missing required metadata becomes an empty YAML value; it is never fabricated.
- An existing clipping with the same sanitized title is replaced atomically by the latest successful run.
- Subtitle parsing fails visibly when normalization produces empty text.
- `--readable none` writes no wiki clipping.

## Verification

- Fixture covers inline timestamps, rolling cue overlap, identical adjacent cues, and deliberate repeated words.
- Unit assertions verify clean output and no duplicated rolling phrases.
- Readable cleanup assertions verify known English and Chinese environment cues are removed while ordinary bracketed prose remains.
- End-to-end run against `-UN9sNqQ0t4` verifies three outputs: packet JSON, clean transcript, and OKF clipping in `wiki/Clippings/`.
