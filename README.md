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
| 主菜单按钮（矢量图形文字） | ✅ 已用 Dirty Ego 风格中文矢量重绘 |

构建产物：`dist/rotl-zh-full.swf`

---

## 目录结构

```
dist/                游戏文件（统一放这里）
  Road-Of-The-Dead.swf 原版游戏
  rotl-zh-full.swf     汉化版（构建产物）
pipeline/            所有脚本（分析 + 构建）
data/                人工产物 / 缓存 / 翻译数据（可复用）
  subtitles.json       对白字幕（类名 → 中文）
  stream_subs.json     时间轴流式音轨字幕（起止秒 → 中文）
  stream_segments.json 流式音轨的逐段 ASR（含时间戳）
  asr_all.json         全部语音的 ASR 缓存
  voice_lines.json/.tsv  ASR 出的英文原始台词
  ui_segments.json     烘焙 UI 文本的分段结构
  as3_strings.json     AS3 里的候选用户可见字符串
  orig_texts/          SWF 导出的原始 UI 文本（224 个）
  fonts/               中文字体（RoadOfTheDeadCN.ttf 等，构建时裁子集）
tools/               第三方工具（FFDec，用 pipeline/fetch-tools.ps1 下载）
```

`work/`、`menu-labels/`、`patch/` 与虚拟环境是构建中间件，**可重新生成，默认不保留**；`dist/`、`tools/`、虚拟环境都在 `.gitignore` 里（仓库不包含游戏本体与第三方工具）。

---

## 环境

```powershell
uv sync                       # 主环境：FFDec 调用 / 导出分析 / 构建
pwsh -File pipeline/fetch-tools.ps1 -Proxy http://127.0.0.1:7897   # 下载 FFDec
```

需要原版游戏 SWF（默认路径 `dist/Road-Of-The-Dead.swf`，可用 `--orig` 指定）。

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

依次执行：FFDec 导出 → 生成带字幕的 `DTSound.as` → 生成汉化后的玩法脚本 → 生成汉化 UI 文本 + 两个中文字体子集（展示体 RoadOfTheDeadCN + 正文思源宋体）→ 合并回 SWF。

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

### 4. 字体（还原原版的两种字形）
原版 UI 用了两种字形，汉化也对应两种 —— 不是全用一种字体：

| 原版 | 用在哪 | 汉化字体 |
|---|---|---|
| **Dirty Ego**（font 20，手绘做旧） | 菜单 / HUD / 标题 / 提示 | `data/fonts/RoadOfTheDeadCN.ttf` |
| **Modern No. 20**（font 22，Didone 衬线） | 升级说明 / 操作·选项列表 / 成就等正文 | `data/fonts/NotoSerifSC-SemiBold.ttf`（思源宋体 SemiBold，OFL） |

两个字体都在构建时用 `pyftsubset` 裁成同一字符集（= UI 文本 ∪ AS3 运行时中文 ∪ ASCII）的子集，各嵌入一次：

- `pipeline/remap_font.py` 把**翻译过的 font-20 文本**改指到展示槽 **92**，其余用正文字体的文本统一改指到正文槽 **22**；
- 最后只替换槽 92（展示体）和槽 22（正文）两个字体，避免同一字体被嵌入十几份把 SWF 撑大；
- **槽必须自带 layout（advance）表**：FFDec 换字形时会保留原 `DefineFont` 的 `HasLayout` 标志，而 `DefineEditText` 靠它排版；用无 layout 的槽（如 88）会让运行时动态文本（车库的 "Drive To …"、提示框、HUD 计数）宽度塌成 0 而消失。92 原本是一个空闲、带 layout 的 Verdana 槽；
- **font 20（"Dirty Ego"）本身不动**：标题 logo、制作名单、HUD 数字等未被翻译的 text 保持字节一致。

### 5. 运行时文本
成就、提示框、关卡介绍、地点名等在 AS3 字符串里，用 `pipeline/patch_as3.py` 按**字面量精确替换**（用词法扫描提取，避免正则把代码当成字符串）。

---

### 6. 对齐
英文换中文后字变短，FFDec 导入文本时会**在原标签的左原点重新左对齐**，于是原本**右对齐**的行（操作列表：左转 / 右转 / 加速 / 刹车 …）会参差不齐。

`pipeline/align_controls.py` 处理这些静态 `DefineText` 标签：读取原标签的 `xmin/xmax/height`，按中文字形轮廓算出宽度，重写 `translatex`，让**中文居中**落在原英文所占的框内。动态文本框（自带 `align`）不动。

- 目标标签集中在 `TARGET_IDS`（操作 / 选项列表）。
- 线性关系 `rendered_left ≈ tx/20`、`rendered_right ≈ (0.9474*tx + k*ink)/20` 由原版实测标定。

---

## 主菜单按钮（矢量重绘）

主菜单的按钮文字（"THE GREAT ESCAPE" / "HIGHWAY TO HELL" / 各模式与面板标签）是**手绘 `DefineShape` 矢量图形**，不是文本，字体替换碰不到它们 —— 这就是「换了字体但主菜单没变」的原因。

定位结果（主时间轴第 6265 帧 / `Menu`）：

| 实例名 | 按钮 id | 常态 shape | 悬停 shape | 原文 |
|---|---|---|---|---|
| `StoryMode` | 4310 | 4307 | 4308 | THE GREAT ESCAPE |
| `StoryHardcoreMode` | 4306 | 4303 | 4304 | HIGHWAY TO HELL |
| `MilitaryMode` | 4298 | 4295 | 4296 | MILITARY MODE |
| `TimeMode` | 4302 | 4299 | 4300 | TIME MODE |
| `Options` | 4314 | 4311 | 4312 | OPTIONS |
| `Achievements` | 4318 | 4315 | 4316 | ACHIEVEMENTS |
| `HighScores` | 4322 | 4319 | 4320 | HIGH SCORES |

`pipeline/menu_labels.py` 把这些标签用**透视投影后**的中文字体轮廓生成矢量 SVG，再让 FFDec 替换对应 shape：

- 原版按钮文字是**手绘透视字**（像铺在路面上由近及远：上边窄、笔画后仰），不是简单斜体；
- **每个标签的透视都不一样**：按钮分布在路面不同位置，越靠下（越近）左边越接近竖直（OPTIONS `L 0.00`、HIGH SCORES `0.01`），越靠上（越远）内收越强（POLICE STATE `0.15`）。所以程序和原版一样**逐标签**取透视（`LABEL_NORM`，用 Theil–Sen 对原版逐行墨迹边界做稳健拟合），不再共用一套平均透视 —— 旧做法（单一 `SHARED_NORM`）会把下方短标签的左边过度倾斜，看起来比英文更「歪」；
- 每个标签的透视四角都落在 `0..1` 内，SVG viewport 边缘不会裁掉最外侧笔画；
- 中文字形投影时**以单个字为单位**取局部仿射（`local_affine`）：整字按自己中心处的仿射「盖章」，而不是逐点走完整单应 —— 一个被拉宽的字左右两侧的局部剪切角能差几十度，逐点投影会把整字扭歪；这样每个字只有一致的倾斜，和英文手绘字一样；
- 中文按该透视投影，字形轮廓**展平成折线**烘焙进 SVG；已核对所有标签「上窄下宽」一致；
- **字号**：中文比英文紧凑得多（5 字顶 14 个字母），若只按原字高绘制，标签只占按钮宽的 20–36%，看起来比英文小很多。现在**字形按标签高度放大后，再横向加宽（上限 `MAX_H_STRETCH = 2.5` 倍自然宽）**去接近按钮宽度，剩下的用**有上限的字距**（`MAX_GAP_RATIO = 0.6` × 高）补足并整体居中 —— 短词会占满按钮框，且不会把两个字甩到按钮两端（旧做法是「按墨迹盒子均分铺满整宽」，2 字标签会变成左右两个几乎贴边的小字，看起来是坏的）；
- **关键**：FFDec 会把替换 SVG 的 *viewport* 按原始 shape 的包围盒 1:1 映射，所以 SVG 的 `width/height` 必须与原始 shape 完全一致；已用实验验证；
- 保留每个状态原本的**颜色和透明度**（Story 是红色 `#cb0000`、其余白色；常态透明度直接取自原版 shape 的填充 alpha：白色 `0.40`、红色 `0.60`，悬停为 `1.0` —— 旧值偏暗，会让中文比旁边英文更淡）；
- 纯矢量，缩放不糊。用例：`python pipeline/menu_labels.py --swf in.swf --out out.swf --orig 原版.swf`

品牌字样（Newgrounds / Evil-Dog / SickDeathFiend）保持原样。

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
| `remap_font.py` | 改文本指向的字体 id（支持一次改多个旧 id → 一个槽） |
| `menu_labels.py` | 主菜单矢量按钮标签 → 中文矢量 SVG 并替换 shape |
| `align_controls.py` | 把操作/选项列表的中文居中回原英文所占的框 |
| `collect_menu_shapes.py` | 导出菜单 Shape 供重绘 |
| `multiget.py` | 多线程分段下载（模型/大文件） |

---

## 说明

- 仅用于个人学习与汉化交流；游戏版权归 Evil-Dog / SickDeathFiend 所有，仓库不包含原始游戏文件。
- 中文字体为 `data/fonts/RoadOfTheDeadCN.ttf`（Dirty Ego 风格中文游戏字体）与 `data/fonts/NotoSerifSC-SemiBold.ttf`（思源宋体，SIL OFL 1.1）；公开发布前请自行确认授权。
