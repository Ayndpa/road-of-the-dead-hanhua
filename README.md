# Road of the Dead — 中文语音字幕 + UI 汉化

给 Flash 游戏 **Road of the Dead**（Evil-Dog / SickDeathFiend, 2011）加中文字幕和中文 UI 的完整工具链。

所有改动都是**对原始 SWF 做无损结构修改**：没有动源码逻辑（除少量字符串），没有替换美术资源，随时可以从原版重新构建。

---

## 成果

| 内容 | 状态 |
|---|---|
| 中文字幕（246 条对白） | ✅ 已内嵌 |
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
  paratranz/           翻译数据（ParaTranz 平台格式，构建直接读取）
    voice.csv            对白字幕（SND_* 类名 → 中文）
    stream.csv           开场流式音轨字幕（stream_NN → 中文）
    ui.csv               烘焙 UI 文本（DefineText id → 中文）
    as3.csv              运行时文本（文件名 → {英文 → 中文}）
    menu.csv             主菜单矢量按钮标签文本
  stream_timing.json   开场流式音轨逐段起止时间（结构数据，非翻译）
  stream_segments.json 流式音轨的逐段 ASR（含时间戳）
  asr_all.json         全部语音的 ASR 缓存（时长 / 语音分段）
  voice_lines.json/.tsv  ASR 出的英文原始台词（来源）
  ui_segments.json     烘焙 UI 文本的分段结构（来源）
  as3_strings.json     AS3 里的候选用户可见字符串（来源）
  orig_texts/          SWF 导出的原始 UI 文本（224 个）
  fonts/               中文字体（RoadOfTheDeadCN.ttf 等，构建时裁子集）
tools/               第三方工具（FFDec / whisper.cpp(Vulkan)，用 pipeline/fetch-tools.ps1、fetch-whisper.ps1 获取）
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

# AMD GPU：whisper.cpp + Vulkan（全部走国内镜像，见 pipeline/fetch-whisper.ps1）
pwsh -File pipeline/fetch-whisper.ps1    # 编译 whisper-cli(Vulkan) + 下载 ggml-large-v3
uv run python pipeline/asr_vulkan.py --voice-only

# 清理幻觉 / 非对白（输出 <out>_clean.json / .tsv / .dropped.json）
uv run python pipeline/clean_asr.py --asr work/asr_gpu.json
```

---

## 重新构建

```powershell
uv run python pipeline/build.py
```

依次执行：FFDec 导出 → 生成带字幕的 `DTSound.as` → 生成汉化后的玩法脚本 → 生成汉化 UI 文本 + 两个中文字体子集（展示体 RoadOfTheDeadCN + 正文思源宋体）→ 合并回 SWF。

---

## 翻译平台（ParaTranz）

所有中文翻译都放在 **ParaTranz** 项目里，仓库只保留平台导出的 CSV（`data/paratranz/*.csv`），构建**直接读取**这些文件 —— 源码里不再内嵌任何翻译（没有 `ui_text.py` / `patch_as3.py` 里的中英对照表，也没有单独的 `subtitles.json`）。

- 项目地址：<https://paratranz.cn/projects/20958>
- 平台 CSV 格式：`key,original,translation,context`（无表头），与上传 / 下载的文件完全一致。

工作流：

1. 在 ParaTranz 上翻译 / 校对；
2. 从平台下载文件（或导出的压缩包），把 `voice.csv`、`stream.csv`、`ui.csv`、`as3.csv`、`menu.csv` 放回 `data/paratranz/`（也可用环境变量 `ROT_TRANSLATIONS` 指向导出目录，不动仓库里的文件）；
3. `uv run python pipeline/build.py` 重新构建 —— 字幕、UI、运行时文本、主菜单矢量标签都会按平台内容更新。

| 文件 | 对应内容 | key | 原文列 |
|---|---|---|---|
| `voice.csv` | 语音字幕（`DTSound.Play` 查表） | `SND_*` 声音类名 | 英文台词 |
| `stream.csv` | 开场流式音轨字幕 | `stream_NN` | 英文原文（时间来自 `stream_timing.json`） |
| `ui.csv` | 烘焙 `DefineText`（多段用换行分隔，段数须与原版一致） | `ui_<DefineText id>` | 原英文 |
| `as3.csv` | 成就 / 提示 / 关卡等运行时文本 | `as3_<文件>_<序号>` | FFDec 反编译出的字面量 |
| `menu.csv` | 主菜单手绘按钮标签 | 标签名（如 `StoryMode`） | 按钮英文 |

> `ui.csv` 里一条词条就是整段 UI 文本，多段用换行分隔，翻译时**段数必须与原版一致**（对应下文 `--- RECORDSEPARATOR ---`）。

---

## 原理速览

### 1. 语音字幕
游戏**所有音效/语音都只经过 `DTSound.Play()`**（621 个 `StartSound` 只是放在 `MC_MCWithAllSounds` 里预载，不参与播放）。因此钩子放在 `DTSound.Play()`：

```as3
m_SoundChannel = m_Sound.play(...);
SubtitleOnPlay(this);          // 用 getQualifiedClassName(m_SoundClass) 查表
```

- 字幕表以 `\uXXXX` 纯 ASCII 形式编译进 ABC，避免编译器编码问题。
- 长台词按句子拆分、分段显示：优先用 `data/asr_all.json` 的**真实语音分段**（每段的 start/end）做时间对齐 —— 中文按各段英文长度分配、拉伸到该段的实际时长，因此字幕只会说一句显一句、不会在静音里提前/空转；没有 ASR 分段时才退回按整段时间比例均分。
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
成就、提示框、关卡介绍、地点名等在 AS3 字符串里，用 `pipeline/patch_as3.py` 按**字面量精确替换**（用词法扫描提取，避免正则把代码当成字符串）。中英对照表来自 `data/paratranz/as3.csv`（`context` 列即文件名），只替换在反编译源码里实际存在的字面量，对不上的条目会打印告警而不是改坏代码。

---

### 6. 对齐
英文换中文后字变短，FFDec 导入文本时会**在原标签的左原点重新左对齐**，于是原本居中或右对齐的行都会偏离原来的位置：选项面板的设置标题（建筑 / 画质 / 存档数据 …）和大标题（操作 / 选项）会左偏，操作列表（左转 / 右转 / 加速 / 刹车 …）则会参差不齐。

`pipeline/align_controls.py` 只改静态 `DefineText` 标签（动态文本框自带 `align`，不动），用 FFDec 的 SVG 导出**实测原版英文与新中文的实际墨迹轴**（不受存储 `xmin/xmax` 比字形宽、字体不同、FFDec 给中文加的字距对的影响），再重写 `translatex`：

- `TARGET_IDS`（选项面板各标签、两个大标题、警告标题）—— 让中文墨迹中心落在**原英文墨迹中心**上；原版标签的存储框比字形宽，框中心并不等于视觉中心，所以不能直接用框中心。
- `LIST_CENTER_IDS`（操作列表）—— 原版英文是**右对齐**在同一右边界，中文更短时会贴在按键列上、左边空一大片；按需求改成**统一列居中**：以原版英文标签整体的左边界到公共右边界的**中轴**为轴，各行按自己在 sprite 内的摆放矩阵分别居中（各行的摆放矩阵不同）。
- `RIGHT_ALIGN_IDS`（SKIP 按钮、车库升级列表）—— 保持右对齐，按墨迹右缘对齐。
- **裁剪框**：Flash 会把静态 `DefineText` 裁到标签的 `xmin/xmax/ymin/ymax`。原版英文的框紧贴英文，英文短的行（喇叭 / 画质 / 雨刷 / 攻击 / 刹车）框的左边界很靠右；居中后中文会伸到 `xmin` 左边被切掉半个字。因此移动过的标签一律把裁剪框放宽到**新墨迹范围 + 20twips**。
- 改 `translatex` 都以标签**当前**值为锚点，所以这一步可重复执行（幂等）。

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
| `align_controls.py` | 按原版墨迹轴重排静态标签：选项面板与标题居中、操作列表统一列居中、SKIP/车库右对齐 |
| `collect_menu_shapes.py` | 导出菜单 Shape 供重绘 |
| `multiget.py` | 多线程分段下载（模型/大文件） |

---

## 说明

- 仅用于个人学习与汉化交流；游戏版权归 Evil-Dog / SickDeathFiend 所有，仓库不包含原始游戏文件。
- 中文字体为 `data/fonts/RoadOfTheDeadCN.ttf`（Dirty Ego 风格中文游戏字体）与 `data/fonts/NotoSerifSC-SemiBold.ttf`（思源宋体，SIL OFL 1.1）；公开发布前请自行确认授权。
