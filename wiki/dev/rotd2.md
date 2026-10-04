# 二代多字体适配

一代 UI 的原版字形其实也不止两种（见[一代字体适配](/dev/fonts)，已按 5 套中文字形适配），
二代 `DefineFont` 里有 **12 种真实字形**，各配一套中文字形。

## 字形映射

`pipeline/ui/build_rotd2_ui.py` 的 `FONT_MAP`：

| 原版字形 | 用在哪 | 中文槽 | 中文字体 |
|---|---|---|---|
| Dirty Ego (93) | 菜单 / HUD / 提示（占绝大多数） | 8705 | `RoadOfTheDeadCN.ttf`（展示体） |
| DESTRUCCION (10419) / DS-Digital (10315) | 制作名单 / 节日提示 | 8705 | 同上 |
| Arial (95) / Verdana (134) | 加载 / 提示 / 帮助正文 | 10082 | Noto Sans SC |
| Arial Black (1) | "Day N" 大标题 | 1 | Noto Sans SC Black |
| Arial Bold (3066, 10082) / Euromode Bold (8705) | 关卡名 / 帮助 | 3066 | Noto Sans SC Bold |
| Arial Italic (3) | 新闻稿正文 | 3 | Noto Sans SC + 合成斜体 |
| Arial Bold Italic (132) | 分数 / Page 1 | 132 | Noto Sans SC Bold + 合成斜体 |
| Typenoksidi (3099) | 生存手册正文 | 3099 | `NotoSerifSC-SemiBold.ttf`（思源宋体） |

- 二代没有空闲槽，每个槽都是原版一个**低占用**字形改指而来；
- 每个字体只包含**它自己那些标签会画到的字**（再加 ASCII 与 AS3 运行时字符串）；
- 只有**翻译过的标签**才改指到中文槽；原版 Dirty Ego 的标题 logo / HUD 数字 /
  制作名单保持字节一致；
- 斜体槽（3、132）**保留 italic 标志**，FFDec 会把中文字形烘焙成斜体；
  其余槽清掉 bold/italic，避免叠加合成样式。

## 三个关键修复

### 1. layout 表克隆

槽必须自带 layout（advance）表。原版 Arial（95）被保留给未翻译的标题 / 版本号，
正文改指到 **10082**；而 10082（11 字形 Arial Bold）原本**没有 layout**。
FFDec 导入字体时会保留 `HasLayout` 标志，于是中文字形也没有 advance，
所有落在该槽上的动态 `DefineEditText` 宽度塌成 0、整页空白（选项 / 成就页）。

构建在换字体前用 `remap_font.copy_font_layout(cur, ..., 10082, 95)` 把 95 的
`DefineFont` 标签体**克隆**到 10082（只改 FontID），让 FFDec 重新生成 advance 表。

### 2. 字体名不能撞车

运行时文本框重排走 `defaultTextFormat.font`（字符串名），`embedFonts` 下 Flash 按
**名字**在嵌入字体里查找，而这个名字取自 **`DefineFont` 本体里的 `FontName`**
（3/95/132/3066/10082 原版都叫 "Arial"）。把原版 Arial（95）保留后，它是唯一带
拉丁字形的 "Arial"，于是 94 个作者期写死 `face="Arial"` 的选项 / 成就 / 帮助文本框
全部命中它，中文变空白（拉丁快捷键字母却正常显示）。

构建最后用 `remap_font.set_font_face(...)` 改**本体 FontName**、再用 `set_font_name(...)`
同步 `DefineFontName` 标签：`{95: "Arial Legacy", 10082: "Arial"}`，
让 "Arial" 只命中中文字体。

### 3. 游戏内选项栏基线

`MC_Hud.OptionsMenu`（sprite 8668）把静态标题（Full Screen / Sounds / Music / Quality）
与动态 `DefineEditText` 值配对。CJK 字形的 ascent 更高，EditText 首行比拉丁原版低约
3px，而移动 `DefineEditText` 标签的 bounds 不会移动文本，因此用
`shift_sprite_placements(..., 8668, {8652,8656,8660,8664}, -60)` 重写这四个值字段的
摆放矩阵，把它们抬回标题基线。

## 构建注意

FFDec 换字体时会**按字符**把已有 `DefineText` 的字形索引重映射到新字体，遇到没有
Unicode 映射的字形（Dirty Ego 里有几个）会算出越界索引并让整个导入崩溃；新中文比
英文短时还会在标签里留下多余的旧字形（显示为尾部空格）。因此构建先把静态标签
**截成空记录（保留每条记录的样式与条数）**，再用 `-format text:formatted` 逐记录写回译文。

## 体积

中间步骤都用未压缩 SWF（FWS）读写，最后的 `compress_swf()` 把成品重新 zlib 压缩成
CWS —— 57.6 MB 降到 49.1 MB，再叠加逐字体裁剪才算回到接近原版的体积。

重新拉取字体：

```powershell
pwsh -File pipeline/tools/fetch-fonts.ps1 -Proxy http://127.0.0.1:7897
```
