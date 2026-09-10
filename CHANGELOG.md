# Changelog

vsum is built around reading to learn from video. Keep the source material available, give an agent the context to write a useful article, and preserve the visuals that words alone cannot explain.

## Unreleased

### Turn a video into an article you can learn from

- **Agent-Guided Video Reading** gives people studying lectures, interviews, and tutorials a way to ask for an article around a specific reading purpose, such as understanding a software demo's design tradeoffs. The agent reads the full transcript and follows a shared writing contract to preserve arguments, examples, and qualifications. Material collection and article completion are separate steps, so a downloaded transcript is never presented as a finished article.
- **Timestamped Transcript Navigation** helps readers and agents return to the relevant moment when checking a technical explanation or choosing a screenshot. Original SRT and VTT caption timestamps are preserved separately from the cleaned transcript, so removing repeated captions does not shift the source timeline. Plain-text transcripts remain untimed rather than receiving guessed timestamps.
- **Video Frame Illustration** helps people learning visual workflows, such as interface design or software setup, keep the screen details alongside the explanation. Video is downloaded by default, or a supplied local video is reused. Timestamp-based frame extraction lets the agent inspect candidate images and choose the ones that clarify the article.

### Set up once, then work from your own projects

- **Agent-Guided Setup** helps first-time users prepare video transcription and article writing through a conversation with their agent. The agent checks local dependencies, confirms where articles should go, and saves reusable preferences. Local diagnostics distinguish required tools from optional frame-extraction and Whisper transcription tools, so setup can follow the work you actually need to do.
- **Workspace-Aware Output Preferences** supports people who keep research notes in several projects or collect every article in one note vault. Relative destinations follow the current workspace; absolute destinations stay fixed. Layered configuration lets a one-off task override saved preferences without changing where future articles go.

### Keep articles usable after the work is done

- **Article Finalization** helps people building a local video knowledge library catch incomplete submissions before treating them as finished notes. Deterministic validation checks source information, body text, and local image references. The agent still reviews meaning and coverage against the transcript; file checks alone cannot establish that an explanation is faithful to the video.
- **Persistent Article Images** keeps illustrated tutorial notes readable after temporary downloads are cleaned up. Selected images live in a dedicated asset directory for each task, and path validation prevents an article from depending on images scheduled for deletion. This also keeps screenshots from separate tasks from overwriting one another.
- **Transcript Recovery After Download Failure** helps users retain research material when subtitles are available but video retrieval fails. The workflow preserves the collected transcript and records the download error explicitly, making it possible to inspect the text and decide how to continue without mistaking a partial result for a successful run.
