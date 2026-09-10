# vsum

English: [README.md](README.md)

`vsum` 是一个把公开视频整理成本地转写稿或带配图文章的 agent skill，支持 B 站、YouTube 和小红书。优先使用平台字幕，没有字幕时可通过本地 Whisper 转写。

给 agent 一个视频链接和阅读需求，它会获取材料、阅读转写稿、按需查看画面，再把文章和配图保存在本地。整个工作流由 [SKILL.md](SKILL.md) 定义，执行脚本和写作规范随 skill 一起安装。

## 安装与初始化

把完整仓库安装到你的 agent 所使用的 skills 目录，并将文件夹命名为 `vsum`。例如，使用 `~/.agents/skills/` 管理 skills 时：

```bash
git clone https://github.com/RizzoTho/vsum.git ~/.agents/skills/vsum
```

让 agent 加载安装目录里的 `SKILL.md`，然后告诉它：

> 初始化 vsum，文章保存在当前项目的 wiki/Clippings 目录。

Agent 会检查依赖和保存位置，调用初始化脚本，在 skill 安装目录生成本机 `.env`，再验证配置。已有配置不会被初始化覆盖。

需要 Python 3.10+ 和 PATH 中的 [yt-dlp](https://github.com/yt-dlp/yt-dlp)。抽帧需要 `ffmpeg`；没有字幕而需要本地转写时，还需要 `whisper` CLI。Agent 会按任务需要处理缺失依赖。

## 使用

在希望保存产物的项目中，向 agent 提出需求：

> 用 vsum 把这个视频整理成中文文章，重点解释演示流程和设计取舍：<视频链接>

> 提取这个视频的字幕，保留原始转写稿即可：<视频链接>

也可以提供本地视频或已有转写稿。视频默认下载用于抽帧；如果不希望下载视频，在请求中说明即可。元数据和字幕获取仍可能联网。

## 产物

| 文件 | 内容 |
|---|---|
| `transcript.txt` | 规范化转写稿，合并滚动字幕的重叠文本 |
| `segments.json` | 字幕文本与时间轴，适用于 SRT/VTT 来源 |
| `packet.json` | 来源信息、产物路径和成文任务状态 |
| `<title>.md` | 完成 `--read` 工作流后，由 agent 撰写的文章 |

配图保存在文章旁，由 packet 指定具体目录。纯文本转写稿不提供时间轴。

## 配置

长期偏好保存在安装目录的 `.env`，模板见 [.env.example](.env.example)。相对路径以当前任务项目为准；固定笔记库可使用绝对路径。

| 设置 | 默认值 |
|---|---|
| `VSUM_OUT_ROOT`：转写稿和运行记录 | `outputs/vsum` |
| `VSUM_READABLE_ROOT`：文章目录 | `wiki/Clippings` |
| `VSUM_TMP_DIR`：临时媒体目录 | 系统临时目录下的 `vsum` |
| `VSUM_WHISPER_MODEL`：本地转写模型 | `small` |

单次参数优先于环境变量，环境变量优先于 `.env`，未配置时采用默认值。临时媒体在成文任务完成后清理；仅收集材料时在运行结束后清理。需要保留可让 agent 使用 `--keep-media`。用户提供的源视频会保留。

具体格式、修改方式和依赖检查见 [配置说明](references/configuration.md)。

## 直接运行脚本

需要手动操作或排查问题时，从任务项目目录调用安装的脚本：

```bash
python3 "<skill-dir>/scripts/vsum.py" doctor
python3 "<skill-dir>/scripts/vsum.py" run "<url>" --read
python3 "<skill-dir>/scripts/vsum.py" run --help
```

`--read` 准备成文任务，文章由 agent 撰写并提交验收。完整工作流见 [SKILL.md](SKILL.md)，平台处理方式见 [platform playbook](references/platform-playbook.md)。

## 目录结构

```text
SKILL.md           agent 入口
scripts/vsum.py    初始化、依赖检查、材料获取、抽帧与验收
references/        写作规范、配置说明与平台处理方式
agents/            agent 界面元数据
.env               本机配置，由初始化生成，不入库
tests/             离线测试
```

## 限制

- 不绕过登录、付费墙、DRM 或私有内容；小红书通常需要浏览器 cookies（`--cookies-from-browser`）或本地文件。
- 转写质量取决于原字幕或 ASR，重要细节需要对照视频核实。
- 视频下载失败时，命令会明确报错，并保留已取得的转写材料。

## 更新记录

功能更新与设计理念见 [CHANGELOG.md](CHANGELOG.md)。

## License

[MIT](LICENSE)
