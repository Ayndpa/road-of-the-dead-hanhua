# Road of the Dead — 中文语音字幕 + UI 汉化

给 Flash 游戏 **Road of the Dead**（Evil-Dog / SickDeathFiend, 2011）加中文字幕和中文 UI 的完整工具链。

所有改动都是**对原始 SWF 做无损结构修改**：没有动源码逻辑（除少量字符串），没有替换美术资源，随时可以从原版重新构建。

---

## 成果

| 内容 | 状态 |
|---|---|
| 中文字幕（228 条对白） | ✅ 已内嵌 |
| 开场流式音轨字幕（紧急广播 + 电台混音，26 段） | ✅ 按主时间轴帧同步 |
| 多行堆叠字幕（电台与主角同时说话各占一行） | ✅ |
| F2 字幕开关（带屏幕提示） | ✅ |
| UI 文本汉化（224 个烘焙文本中的 174 个） | ✅ |
| 运行时文本汉化（成就 / 提示框 / 关卡介绍 / 地点 / 结算，233 处） | ✅ |
| 标题 logo、制作名单、数字保持原始字体设计 | ✅ 逐字节未改动 |
| 主菜单按钮（矢量图形文字） | ⏳ 待重绘，见下文 |

构建产物：`release/rotl-zh-full.swf`

---

## 目录结构

```
pipeline/            所有脚本（分析 + 构建）
data/                人工产物 / 缓存（可复用）
  subtitles.json       对白字幕（类名 → 中文）
  stream_subs.json     时间轴流式音轨字幕（起止秒 → 中文）
  stream_segments.json 流式音轨的逐段 ASR（含时间戳）
  asr_all.json         全部语音的 ASR 缓存
  voice_lines.json/.tsv  ASR 出的英文原始台词
  ui_segments.json     烘焙 UI 文本的分段结构
  as3_strings.json     AS3 里的候选用户可见字符串
  orig_texts/          SWF 导出的原始 UI 文本（224 个）
menu-shapes/         主菜单用到的 Shape（PNG，供人工重绘）
release/             构建产物
patch/               生成物（构建中间件，可重新生成）
```

`work/`、`dist/`、`tools/`、虚拟环境都在 `.gitignore` 里，属于过程文件。

---

## 环境

```powershell
uv sync                       # 主环境：FFDec 调用 / 导出分析 / 构建
pwsh -File pipeline/fetch-tools.ps1 -Proxy http://127.0.0.1:7897   # 下载 FFDec
```

需要原版游戏 SWF（默认路径 `D:\Dev\Codes\Test\road-of-the-dead.swf`，可用 `--orig` 指定）。

ASR 相关（可选，只在需要重新转写时用）：

```powershell
# CPU：faster-whisper
uv run python pipeline/asr.py --no-vad --voice-only

# AMD GPU：DirectML + openai-whisper（另建环境）
uv venv gpuenv && uv pip install --python gpuenv\.venv torch-directml openai-whisper av numba tiktoken more-itertools
```

---

## 重新构建

```powershell
uv run python pipeline/build.py
```

依次执行：FFDec 导出 → 生成带字幕的 `DTSound.as` → 生成汉化后的玩法脚本 → 生成汉化 UI 文本 + 中文字体子集 → 合并回 SWF。

---

## 原理速览

### 1. 语音字幕
游戏**所有音效/语音都只经过 `DTSound.Play()`**（621 个 `StartSound` 只是放在 `MC_MCWithAllSounds` 里预载，不参与播放）。因此钩子放在 `DTSound.Play()`：

```as3
m_SoundChannel = m_Sound.play(...);
SubtitleOnPlay(this);          // 用 getQualifiedClassName(m_SoundClass) 查表
```

- 字幕表以 `\uXXXX` 纯 ASCII 形式编译进 ABC，避免编译器编码问题。
- 长台词按句子拆分、按时长比例分段显示（`data/asr_all.json` 提供时长）。
- 多行堆叠：不同来源各占一行，同一来源重开一句只替换自己那行。
- 初始化挂在 `BasicGame.Init()`，否则开场（无对白音效）阶段系统不会启动。

### 2. 开场流式音轨
开场旁白在主时间轴的**流式音轨**（`-1.mp3`）里，不经过 `DTSound`。用 `Event.ENTER_FRAME` 把主时间轴帧号换算成音轨时间：

```
t = (currentFrame - 1) / frameRate - 1.58
```

`1.58s` 是实测偏移 —— `pipeline/stream_timing.py` 解析全部 `SoundStreamBlock` 的 MP3 帧头，算出每帧的真实音频时间，整条时间轴偏移恒定。

### 3. UI 文本
UI 文字是**烘焙的 `DefineText`**（没有运行时字符串）。

> 注意：FFDec 的 `-importText` 是**静默空操作**（不报错但什么都不改），必须用 `-replace <charId> <txt>`。

文本里 `--- RECORDSEPARATOR ---` 是记录分隔符，翻译时**段数必须一致**。

### 4. 字体
- 把 15 个内嵌字体替换成微软雅黑子集（粗体 / 常规两个），子集字符集 = UI 文本 ∪ AS3 运行时中文 ∪ ASCII。
- **font 20（"Dirty Ego"）保持原样不动**：标题 logo、制作名单、HUD 数字都用它。需要显示中文的那 34 条文本用 `pipeline/remap_font.py` 改指向空字体槽 88 再填充雅黑，其余 31 条连导入都不做，保持字节一致。

### 5. 运行时文本
成就、提示框、关卡介绍、地点名等在 AS3 字符串里，用 `pipeline/patch_as3.py` 按**字面量精确替换**（用词法扫描提取，避免正则把代码当成字符串）。

---

## 待办：主菜单按钮

主菜单面板（sprite 4291）里**只有 `DefineShape`，没有任何文本标签** —— 按钮文字是手绘矢量图形，无法用文本替换。

已导出到 `menu-shapes/`：

- `render_DefineSprite_4291.png` — 主菜单整屏渲染（参考）
- `render_DefineSprite_4358/4379/4431.png` — 成就 / 排行榜 / 选项面板
- `shape_<id>.png` × 36 — 主菜单用到的全部 Shape
- `manifest.csv` — charId / 类型 / 尺寸

**流程**：重绘后保持文件名不变放回该目录，然后注入：

```powershell
java -jar tools/ffdec/ffdec-cli.jar -replace release/rotl-zh-full.swf dist/out.swf `
     4240 menu-shapes/shape_4240.png lossless2        # 可一次带多组
```

FFDec 支持用 PNG 替换 Shape（已验证）。建议保持原尺寸、带透明通道。

---

## 分析与调试工具

| 脚本 | 用途 |
|---|---|
| `swf_labels.py` | 主时间轴帧标签 / 场景 / 流式音轨覆盖范围 |
| `stream_timing.py` | 帧 → 真实音频时间的精确换算 |
| `swf_text_fonts.py` | 每个 `DefineText` 用的字体 |
| `frame_chars.py` | 某一帧上放置了哪些 character |
| `walk_sprite.py` | 递归展开 sprite 结构 |
| `scan_strings.py` / `dump_as3_strings.py` | AS3 里用户可见字符串 |
| `remap_font.py` | 改文本指向的字体 id |
| `collect_menu_shapes.py` | 导出菜单 Shape 供重绘 |
| `multiget.py` | 多线程分段下载（模型/大文件） |

---

## 说明

- 仅用于个人学习与汉化交流；游戏版权归 Evil-Dog / SickDeathFiend 所有，仓库不包含原始游戏文件。
- 字体子集取自系统自带的微软雅黑；若要公开发布建议换成思源黑体（OFL）。
