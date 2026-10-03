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
| F3 字幕设置面板（仅英文 / 仅中文 / 中英双语、字号小中大、背景显示/隐藏，自动保存） | ✅ |
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
pipeline/            所有脚本（按功能分包，见 pipeline/README.md）
  build.py             一代完整构建入口
  lib/                 共享库（翻译读取 / 字体重映射 / 标签对齐）
  asr/                 语音转写 / 清理 / 合并
  swf/                 SWF 只读分析工具
  ui/                  UI 汉化构建（字体 / 烘焙文本 / 主菜单 / 二代）
  runtime/             运行时 AS3 文本替换
  subtitles/           游戏内字幕生成（DTSound 补丁）
  paratranz/           ParaTranz 导入 / 回传
  tools/               第三方工具拉取脚本（fetch-*.ps1）
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
tools/               第三方工具（FFDec / whisper.cpp(Vulkan)，用 pipeline/tools/fetch-tools.ps1、pipeline/tools/fetch-whisper.ps1 获取）
```

`work/`、`menu-labels/`、`patch/` 与虚拟环境是构建中间件，**可重新生成，默认不保留**；`dist/`、`tools/`、虚拟环境都在 `.gitignore` 里（仓库不包含游戏本体与第三方工具）。

---

## 环境

```powershell
uv sync                       # 主环境：FFDec 调用 / 导出分析 / 构建
pwsh -File pipeline/tools/fetch-tools.ps1 -Proxy http://127.0.0.1:7897   # 下载 FFDec
```

需要原版游戏 SWF（默认路径 `dist/Road-Of-The-Dead.swf`，可用 `--orig` 指定）。

ASR 相关（可选，只在需要重新转写时用）：

```powershell
# AMD GPU：whisper.cpp + Vulkan（全部走国内镜像，见 pipeline/tools/fetch-whisper.ps1）
pwsh -File pipeline/tools/fetch-whisper.ps1    # 编译 whisper-server/cli(Vulkan) + 下载 ggml-large-v3

# 所有转写流程都常驻一个 whisper-server：模型只加载一次，请求并发跑
uv run python pipeline/asr/asr_vulkan.py --voice-only --concurrency 4
uv run python pipeline/asr/asr.py --no-vad --voice-only --concurrency 4

# 清理幻觉 / 非对白（输出 <out>_clean.json / .tsv / .dropped.json）
uv run python pipeline/asr/clean_asr.py --asr work/asr_gpu.json
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

反向同步（本地改了原文 / 译文后回传平台覆盖旧数据）：

```powershell
$env:PARATRANZ_TOKEN = "<ParaTranz API Token>"
uv run python pipeline/paratranz/push_translations.py                 # 一代 20958 + 二代 20962 全部文件
uv run python pipeline/paratranz/push_translations.py --project 20962 --file as3.csv   # 也可只推单个项目 / 文件
```

脚本会先把仓库里的 CSV 作为**源文件**重新上传（补上平台缺失的词条），再按 key 通过词条 API 覆盖译文；`--dry-run` 只打印不提交。

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
- 中英**两种语言都按各自句子拆分**：英文原文按 `.` / `!` / `?` 断句（中文按 `。！？`），分段数量取两者中切得更细的一方，另一方在多余的分段里保持同一句不跳动，因此不会再出现「中文切了、英文还是一整段」。英文断句会跳过小数点（`64.7`）和常见缩写（`U.S.`、`Mr.` 等），否则这些点会被当成句末、凭空多出几句英文，把中文整体挤后一句而与语音脱节（中文看起来「更慢」）。
- 多行堆叠：不同来源各占一行，同一来源重开一句只替换自己那行。
- 每条字幕同时带上英文原文与中文翻译（取自平台 CSV 的 `original` / `translation` 两列），运行时按设置只显示其中一种或上下两行全显示；长台词分段的每个小段也各自成对，保证中英逐句对齐。
- 初始化挂在 `BasicGame.Init()`，否则开场（无对白音效）阶段系统不会启动。

#### 字幕设置面板（F3）
字幕显示方式全部在运行时的 `DTSound` 覆盖层里绘制，不依赖原始 SWF 的菜单资源：

- 按 `F3`（或关闭时再次按 `F3` / `Esc`）开关面板；面板列出三行设置，鼠标点击该行即切换取值，键盘用 `↑↓` 选择行、`←→`（或回车）修改；
- **显示模式**：仅英文 / 仅中文 / 中英双语（默认仅中文，双语时英文在上、中文在下）；
- **字号**：小 / 中 / 大（默认中）；
- **背景**：显示 / 隐藏（默认显示，隐藏后仅保留描边发光，方便看画面）；背景框宽度按当前字幕实际渲染宽度自适应（居中、左右留白），不再是固定满宽；
- 打开面板时，底部会用**真正的字幕渲染路径**显示一条示例字幕（与游戏内字幕同一套字体、字号、描边与背景），随显示模式 / 字号 / 背景的改动立即变化，所见即所得；
- 设置写入 SharedObject `rotd_zh_subtitles`，下次启动自动恢复；`F2` 仍是总开关。

### 2. 开场流式音轨
开场旁白在主时间轴的**流式音轨**（`-1.mp3`）里，不经过 `DTSound`。用 `Event.ENTER_FRAME` 把主时间轴帧号换算成音轨时间：

```
t = (currentFrame - 1) / frameRate - 1.58
```

`1.58s` 是实测偏移 —— `pipeline/swf/stream_timing.py` 解析全部 `SoundStreamBlock` 的 MP3 帧头，算出每帧的真实音频时间，整条时间轴偏移恒定。

### 3. UI 文本
UI 文字是**烘焙的 `DefineText`**（没有运行时字符串）。

> 注意：FFDec 的 `-importText` 是**静默空操作**（不报错但什么都不改），必须用 `-replace <charId> <txt>`。

文本里 `--- RECORDSEPARATOR ---` 是记录分隔符，翻译时**段数必须一致**。

### 4. 字体（按原版字形逐个适配）
原版 UI 不止两种字形：15 个 `DefineFont` 标签、约 10 种字形名，其中**有译文**的就有 Dirty Ego、Modern No. 20、Arial（26/32/1758）、Arial Black（46/558）、Verdana（87/88/94）、Arial Narrow（4013）、FFF Calypso（1103）、FFF Business Bold（1106）。汉化按每个字形的视觉角色各配一套中文字形（`pipeline/ui/build_all.py` 的 `G1_FONT_MAP`）：

| 原版字形 | 用在哪 | 中文槽 | 汉化字体 |
|---|---|---|---|
| Dirty Ego（20，手绘做旧） | 菜单 / HUD / 标题 / 提示 | 92 | `data/fonts/RoadOfTheDeadCN.ttf` |
| Modern No. 20（22，Didone 衬线） | 升级说明 / 操作·选项列表 / 成就等正文 | 22 | `data/fonts/NotoSerifSC-SemiBold.ttf`（思源宋体，OFL） |
| Arial（26/32/1758）/ Verdana（87/88/94）/ Arial Narrow（4013） | NG 提示、勋章弹窗、更多游戏等 | 94 | Noto Sans SC |
| FFF Calypso（1103）/ FFF Business Bold（1106） | 排行榜标题 / 高分榜标签 | 1106 | Noto Sans SC Bold |
| Arial Black（46/558） | 制作名单标题 | 1758 | Noto Sans SC Black |

- 每个字体只包含**它自己那些标签会画到的字**（再加 ASCII 与 AS3 运行时可能赋给任意文本框的中文），用 `pyftsubset` 逐字体裁剪并丢弃 `GSUB/GPOS/GDEF` 等 SWF 用不到的表；
- **槽必须自带 layout（advance）表**：FFDec 换字形时会保留原 `DefineFont` 的 `HasLayout` 标志，而 `DefineEditText` 靠它排版；无 layout 的槽会让运行时动态文本（车库的 "Drive To …"、提示框、HUD 计数）宽度塌成 0 而消失。展示/正文/无衬线/粗体四个槽都带 layout；Arial Black 槽只承载静态文本；
- **font 20（"Dirty Ego"）本身不动**：标题 logo、制作名单、HUD 数字等未被翻译的 text 保持字节一致；
- 与二代相同的两个坑：FFDec 换字体时会按字符重映射已有 `DefineText` 的字形索引（原字体有无 Unicode 映射的字形时会越界崩溃），且新中文更短时会残留尾部空格，所以构建同样**先把静态标签截成空记录、再用 `text:formatted` 逐记录写回**；
- 成品最后 `compress_swf()` 重新 zlib 压缩成 CWS（中间步骤输出的是未压缩 FWS）：30.19MB → 27.43MB。

### 5. 运行时文本
成就、提示框、关卡介绍、地点名等在 AS3 字符串里，用 `pipeline/runtime/patch_as3.py` 按**字面量精确替换**（用词法扫描提取，避免正则把代码当成字符串）。中英对照表来自 `data/paratranz/as3.csv`（`context` 列即文件名），只替换在反编译源码里实际存在的字面量，对不上的条目会打印告警而不是改坏代码。

---

### 6. 对齐
英文换中文后字变短，FFDec 导入文本时会**在原标签的左原点重新左对齐**，于是原本居中或右对齐的行都会偏离原来的位置：选项面板的设置标题（建筑 / 画质 / 存档数据 …）和大标题（操作 / 选项）会左偏，操作列表（左转 / 右转 / 加速 / 刹车 …）则会参差不齐。

`pipeline/lib/align_controls.py` 只改静态 `DefineText` 标签（动态文本框自带 `align`，不动），用 FFDec 的 SVG 导出**实测原版英文与新中文的实际墨迹轴**（不受存储 `xmin/xmax` 比字形宽、字体不同、FFDec 给中文加的字距对的影响），再重写 `translatex`：

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

`pipeline/ui/menu_labels.py` 把这些标签用**透视投影后**的中文字体轮廓生成矢量 SVG，再让 FFDec 替换对应 shape：

- 原版按钮文字是**手绘透视字**（像铺在路面上由近及远：上边窄、笔画后仰），不是简单斜体；
- **每个标签的透视都不一样**：按钮分布在路面不同位置，越靠下（越近）左边越接近竖直（OPTIONS `L 0.00`、HIGH SCORES `0.01`），越靠上（越远）内收越强（POLICE STATE `0.15`）。所以程序和原版一样**逐标签**取透视（`LABEL_NORM`，用 Theil–Sen 对原版逐行墨迹边界做稳健拟合），不再共用一套平均透视 —— 旧做法（单一 `SHARED_NORM`）会把下方短标签的左边过度倾斜，看起来比英文更「歪」；
- 每个标签的透视四角都落在 `0..1` 内，SVG viewport 边缘不会裁掉最外侧笔画；
- 中文字形投影时**以单个字为单位**取局部仿射（`local_affine`）：整字按自己中心处的仿射「盖章」，而不是逐点走完整单应 —— 一个被拉宽的字左右两侧的局部剪切角能差几十度，逐点投影会把整字扭歪；这样每个字只有一致的倾斜，和英文手绘字一样；
- 中文按该透视投影，字形轮廓**展平成折线**烘焙进 SVG；已核对所有标签「上窄下宽」一致；
- **字号**：中文比英文紧凑得多（5 字顶 14 个字母），若只按原字高绘制，标签只占按钮宽的 20–36%，看起来比英文小很多。现在**字形按标签高度放大后，再横向加宽（上限 `MAX_H_STRETCH = 2.5` 倍自然宽）**去接近按钮宽度，剩下的用**有上限的字距**（`MAX_GAP_RATIO = 0.6` × 高）补足并整体居中 —— 短词会占满按钮框，且不会把两个字甩到按钮两端（旧做法是「按墨迹盒子均分铺满整宽」，2 字标签会变成左右两个几乎贴边的小字，看起来是坏的）；
- **关键**：FFDec 会把替换 SVG 的 *viewport* 按原始 shape 的包围盒 1:1 映射，所以 SVG 的 `width/height` 必须与原始 shape 完全一致；已用实验验证；
- 保留每个状态原本的**颜色和透明度**（Story 是红色 `#cb0000`、其余白色；常态透明度直接取自原版 shape 的填充 alpha：白色 `0.40`、红色 `0.60`，悬停为 `1.0` —— 旧值偏暗，会让中文比旁边英文更淡）；
- 纯矢量，缩放不糊。用例：`python pipeline/ui/menu_labels.py --swf in.swf --out out.swf --orig 原版.swf`

品牌字样（Newgrounds / Evil-Dog / SickDeathFiend）保持原样。

---

## 二代（ROTD2）多字体适配

一代 UI 的原版字形其实也不止两种（见上一节，已按 5 套中文字形适配），二代的 `DefineFont` 里更有 **12 种真实字形**（Arial 常规/粗体/黑体/斜体/粗斜体、Verdana、Typenoksidi、Euromode Bold、Dirty Ego、DESTRUCCION、DS-Digital）。二代按每个原版字形的**视觉角色**各配一套中文字形，不能像旧版那样把 Arial 正文塞进思源宋体、斜体新闻稿变正体。`pipeline/ui/build_rotd2_ui.py` 的映射：

| 原版字形 | 用在哪 | 中文槽 | 中文字体 |
|---|---|---|---|
| Dirty Ego (93) | 菜单 / HUD / 提示（占绝大多数） | 8705 | `RoadOfTheDeadCN.ttf`（展示体） |
| DESTRUCCION (10419) / DS-Digital (10315) | 制作名单 / 节日提示 | 8705 | 同上（做旧展示体） |
| Arial (95) / Verdana (134) | 加载 / 提示 / 帮助正文 | 10082 | Noto Sans SC（克隆 95 的 layout，见下） |
| Arial Black (1) | "Day N" 大标题 | 1 | Noto Sans SC Black |
| Arial Bold (3066, 10082) / Euromode Bold (8705) | 关卡名 / 帮助 | 3066 | Noto Sans SC Bold |
| Arial Italic (3) | 新闻稿正文 | 3 | Noto Sans SC + 合成斜体 |
| Arial Bold Italic (132) | 分数 / Page 1 | 132 | Noto Sans SC Bold + 合成斜体 |
| Typenoksidi (3099) | 生存手册正文 | 3099 | `NotoSerifSC-SemiBold.ttf`（思源宋体） |

- 每个槽都是原版一个**低占用**字形改指而来（二代没有空闲槽），构建时用 `pyftsubset` 逐字体裁剪，只嵌入一次；
- 每个字体只包含**它自己那些标签会画到的字**（再加 ASCII 与 AS3 运行时可能赋给任意文本框的中文），不再把整份字集塞进全部字体；同时丢弃 `GSUB/GPOS/GDEF/post` 等 SWF 用不到的表；
- 只有**翻译过的标签**才改指到中文槽；原版 Dirty Ego 的标题 logo / HUD 数字 / 制作名单保持字节一致；
- 斜体槽（3、132）**保留 italic 标志**，FFDec 会把中文字形烘焙成斜体，与被替换的英文斜体一致；其余槽清掉 bold/italic，避免叠加合成样式；
- 槽必须自带 layout（advance）表（`DefineEditText` 靠它排版）。原版 Arial（95）被保留给未翻译的标题/版本号（"Road of the Dead" / "v1.24.0"），正文改指到 **10082**，而 10082（11 字形 Arial Bold）原本 **没有 layout**；FFDec 导入字体时会保留这个 `HasLayout` 标志，于是中文字形也没有 advance，所有落在该槽上的动态 `DefineEditText` 宽度塌成 0、整页空白（选项 / 成就页）。因此构建在换字体前用 `remap_font.copy_font_layout(cur, ..., 10082, 95)` 把 95 的 `DefineFont` 标签体**克隆**到 10082（只改 FontID），让 FFDec 重新生成 advance 表。
- **字体名不能撞车（本体 FontName，不是 `DefineFontName` 标签）**：运行时文本框重排会走 `defaultTextFormat.font`（字符串名），`embedFonts` 下 Flash 按**名字**在嵌入字体里查找，而这个名字取自 **`DefineFont` 本体里的 `FontName`**（3/95/132/3066/10082 原版都叫 “Arial”）。把原版 Arial（95）保留后，它是唯一带拉丁字形的 “Arial”，于是 94 个作者期写死 `face="Arial"` 的选项/成就/帮助文本框全部命中它，中文变空白（拉丁快捷键字母却正常显示）。所以构建最后用 `remap_font.set_font_face(...)` 改**本体 FontName**、再用 `set_font_name(...)` 同步 `DefineFontName` 标签：`{95: "Arial Legacy", 10082: "Arial"}`，让 “Arial” 只命中中文字体。

**构建注意**：FFDec 换字体时会**按字符**把已有 `DefineText` 的字形索引重映射到新字体，遇到没有 Unicode 映射的字形（Dirty Ego 里有几个）会算出越界索引并让整个导入崩溃；新中文比英文短时还会在标签里留下多余的旧字形（显示为尾部空格）。因此构建先把静态标签**截成空记录（保留每条记录的样式与条数）**，再用 `-format text:formatted` 逐记录写回译文 —— 多行文本的分行原样保留。

**体积**：构建的中间步骤都用未压缩 SWF（FWS）读写，最后的 `compress_swf()` 会把成品重新 zlib 压缩成游戏原版的 CWS——这一步就把 57.6MB 降到 49.1MB，再叠加逐字体裁剪才算回到接近原版的体积；中文多字体本身仍会比英文原版多几 MB 的字形数据。

- 重新拉取字体：`pwsh -File pipeline/tools/fetch-fonts.ps1 -Proxy http://127.0.0.1:7897`（Noto Sans SC 可变字体，构建时实例化为 Regular/Bold/Black）。

---

## 分析与调试工具

| 脚本 | 用途 |
|---|---|
| `swf/swf_labels.py` | 主时间轴帧标签 / 场景 / 流式音轨覆盖范围 |
| `swf/stream_timing.py` | 帧 → 真实音频时间的精确换算 |
| `swf/swf_text_fonts.py` | 每个 `DefineText` 用的字体 |
| `swf/frame_chars.py` | 某一帧上放置了哪些 character |
| `swf/walk_sprite.py` | 递归展开 sprite 结构 |
| `swf/scan_strings.py` / `swf/dump_as3_strings.py` | AS3 里用户可见字符串 |
| `lib/remap_font.py` | 改文本指向的字体 id（支持一次改多个旧 id → 一个槽） |
| `ui/menu_labels.py` | 主菜单矢量按钮标签 → 中文矢量 SVG 并替换 shape |
| `lib/align_controls.py` | 按原版墨迹轴重排静态标签：选项面板与标题居中、操作列表统一列居中、SKIP/车库右对齐 |
| `swf/collect_menu_shapes.py` | 导出菜单 Shape 供重绘 |
| `paratranz/multiget.py` | 多线程分段下载（模型/大文件） |

---

## 说明

- 仅用于个人学习与汉化交流；游戏版权归 Evil-Dog / SickDeathFiend 所有，仓库不包含原始游戏文件。
- 中文字体为 `data/fonts/RoadOfTheDeadCN.ttf`（Dirty Ego 风格中文游戏字体）、`data/fonts/NotoSerifSC-SemiBold.ttf`（思源宋体，SIL OFL 1.1）与 `data/fonts/NotoSansSC-VF.ttf`（Noto Sans SC 可变字体，SIL OFL 1.1，二代用）；公开发布前请自行确认授权。
