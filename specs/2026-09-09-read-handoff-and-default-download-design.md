# 2026-09-09 — read 交接合同与默认视频获取设计

## 背景

此前 `bin/vsum` 同时承担三件事：材料生产（字幕/ASR）、文章生成（OpenAI/basic 内置路径）、以及"下载需要显式 `--download` 许可"的保守默认。三者互相纠缠：`--readable auto` 依赖 `OPENAI_API_KEY` 静默切换行为，内置分块生成无法做全文统稿，显式下载许可又让配图无米下锅。

## 本次改动

1. **参数收缩**：`--readable auto|openai|basic|agent|none` 与必填 `--intent` 删除，替换为 `--read [目的]`。裸开关用默认目的，传字符串原样保存，空白目的报错。旧参数命中时给迁移提示，不做静默兼容；`--download` 降级为 no-op 警告。
2. **成文交给 agent**：CLI 不再调用任何模型。`--read` 在 packet 写入 `read` 对象（`status: pending`、`intent` 唯一权威、`input`/`segments`/`output`/`instructions` 绝对路径）。`read.output` 只是预期目标，不进 `artifacts`。唯一写作规范在 `skill/READABLE.md`，CLI 与 SKILL.md 都不复制 prompt。
3. **`vsum finalize`**：确定性验收（文章非空、本地图片引用存在且非空），通过后原子更新 packet（`status: done`、实际 artifact 路径）并镜像 `latest-packet.json`；同时清理本次运行拥有的临时媒体。媒体目录有 `vsum-run.json` ownership marker，finalize 只删自己能证明拥有的目录。
4. **默认下载视频**：`vsum run` 默认获取视频（已有 `--video-file` 时复用，`--no-download` 跳过），与字幕成功与否、是否 `--read` 解耦。下载失败明确报告并写进 packet、反映在退出码，已取得的字幕/转写产物保留。
5. **时间轴与抽帧**：新增 `segments.json`，逐条保存 SRT/VTT cue 的 `start/end/text`，不用去重后文本反推时间；纯文本来源记 `segments: null` 加原因。新增 `vsum frame <packet> --at <秒>`，用 ffmpeg 从 packet 关联视频抽帧并记录来源。
6. **媒体生命周期**：临时媒体改为每次运行独立子目录，并行运行互删风险消除；pending read 保留视频供抽帧，finalize/无任务时清理，`--keep-media` 覆盖，用户源视频永不删除，清理失败可观察。

## 边界

- finalize 的 done 只表示文章提交并通过确定性检查；语义忠实是 agent 的责任，CLI 不宣称能证明无遗漏或无曲解。
- 不自动读取浏览器 cookies，不绕过登录、付费墙、DRM、私有内容。
- adapter_targets 中的 `openai` 指 agent runtime 适配目标，与文章生成无关，保留。

## 验证

离线 pytest 套件（`tests/`，33 项）覆盖参数四态、迁移提示、pending packet 合同、OpenAI key 无效化、默认下载触发/复用/跳过/失败可见、SRT/VTT 解析、纯文本无时间轴、抽帧成功与失败、finalize 拒绝空文章和坏图、成功更新 packet、清理范围隔离。真实媒体验证：YouTube 19 秒视频全链路 `run --read` → `frame` → 实际看图 → 写文章 → `finalize`，媒体清理与 packet 状态均正确。

## 2026-09-09 修订：验收与资源隔离

同日审查发现并修复六项：

1. finalize 先验收后清理，但未检查图片是否位于待删除的临时媒体目录内。现在解析所有本地图片引用的真实路径（含 symlink），引用临时目录内图片时拒绝 finalize 并提示迁移到 `read.assets`；全部检查通过前 packet 保持 pending、媒体保留；成功清理后再次确认图片仍存在且非空。
2. finalize 无条件覆盖 `latest-packet.json`。现在 packet 携带 `run_id`，只有 latest 仍指向当前 run（写前二次确认，缩小竞争窗口）才同步；latest 缺失、损坏或已被更新 run 取代时不覆盖，明确记录。
3. 共享 `images/` 会因默认帧名（如 `frame-125.50.png`）互相覆盖。现在 `read.assets` 按来源与运行标识给出专属目录 `images/<source-dir>/<run-dir>/`，agent 按 packet 交接字段保存选用图片；finalize 拒绝资源目录约定之外的本地图片；候选帧留在临时目录。
4. 旧 `collect_local_image_refs` 只认内联图片。换成小解析器：先剥离 fenced code block 和行内代码，再收集引用定义，支持内联（尖括号/带标题/URL 编码）、完整、折叠、快捷引用；标签无法解析或语法无法处理时显式报错；远端（带 scheme）与锚点跳过。
5. 文章验收只查非空。现在解析 frontmatter，校验 `clippings` 标签、`source`/`published`/`author` 与 packet 元数据一致（元数据缺失允许留空）；去除 frontmatter、标题、注释、图片和引用定义后必须有实质正文；失败保持 pending、不清理媒体。
6. 测试辅助 `next(out.rglob("packet.json"))` 可能读到上一次运行的 packet。现在从 CLI stdout 的 `packet: <path>` 行取得本次 packet 路径，不依赖目录遍历顺序。
