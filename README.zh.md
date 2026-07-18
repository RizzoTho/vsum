# vsum

English: [README.md](README.md)

给习惯从视频里学东西的人——B 站、YouTube、小红书——但更想读文字而不是拖进度条。从一个视频 URL 拿到一份干净可读的转写稿其实很麻烦：每个平台藏字幕的方式都不一样，ASR 在静默段会幻听，一半的工具还会悄悄下载你根本没要的视频文件。`vsum` 来自我自己的知识工作流：值得留下的产物是转写稿，不是视频文件。AI 不替你判断什么值得读，它只是让你更快拿到能读的文本。

`vsum` 把一个公开视频 URL 加一个阅读意图，变成本地转写产物：规范化的原始转写稿、可读的 Markdown 版本、机器可读的运行记录。管线是字幕优先——平台字幕不存在时才碰媒体文件，且只在你明确允许时才下载。

## 安装

需要 Python 3.10+ 和 PATH 里的 [yt-dlp](https://github.com/yt-dlp/yt-dlp)。以下可选，装了就自动启用：

- `ffmpeg` + `whisper` CLI——平台没有字幕时的本地 ASR 兜底
- `OPENAI_API_KEY`——用 OpenAI API 做可读稿清理（没有则跑离线基础清理）

```bash
git clone <this-repo> && cd vsum
ln -s "$PWD/bin/vsum" ~/.local/bin/vsum   # 或把 bin/ 加进 PATH
```

## 使用

```bash
# 先探测公开元数据，不下载
vsum probe "https://www.youtube.com/watch?v=..."

# 生成转写产物；--intent 说明你想从视频里得到什么
vsum run "https://www.bilibili.com/video/BV..." --intent "整理成可直接阅读的中文转写稿"
```

没有字幕时，可以提供自己的素材而不是下载：

```bash
vsum run "<url>" --intent "<目的>" --transcript notes.srt
vsum run "<url>" --intent "<目的>" --video-file local.mp4
vsum run "<url>" --intent "<目的>" --download          # 明确同意后才用 yt-dlp 下载
```

## 配置

输出位置和模型都可以通过 CLI 参数或环境变量配置：

| 设置项 | 参数 | 环境变量 | 默认值 |
|---|---|---|---|
| 原始产物（转写稿、packet、媒体） | `--out-dir` | `VSUM_OUT_ROOT` | `./outputs/vsum/` |
| 可读版 Markdown 输出 | `--readable-out-dir` | `VSUM_READABLE_ROOT` | 与原始产物同目录 |
| 本地 ASR 的 Whisper 模型 | `--whisper-model` | `VSUM_WHISPER_MODEL` | `small` |
| 可读稿清理模型 | `--readable-model` | `VSUM_READABLE_MODEL` | `gpt-4.1-mini` |

默认情况下可读版 Markdown 就放在原始转写稿旁边。如果你像我一样把可读稿收进笔记库，把 `VSUM_READABLE_ROOT` 指到那个目录一次，之后每次运行都会落到那里。

## 目录结构

```
bin/      vsum CLI（单文件 Python）
skill/    agent skill 封装（SKILL.md + 平台 playbook）
agents/   面向 agent runtime 的接口声明
scripts/  针对真实平台链接的每日冒烟测试
specs/    设计笔记
```

## 限制

- 不绕过登录、付费墙、DRM 或私有内容；小红书通常需要浏览器 cookies（`--cookies-from-browser`）或本地文件。
- 字幕质量取决于平台本身；滚动式自动字幕会做去重叠处理，但只有走 OpenAI 清理时才会重新断句。
- Whisper 兜底会过滤已知的中文幻听短语，但嘈杂音频上的 ASR 结果只能尽力而为。
- 所有转写路径都失败时会明确报错——不会静默返回残缺产物。

## License

[MIT](LICENSE)
