# 主菜单矢量重绘

主菜单的按钮文字（`THE GREAT ESCAPE` / `HIGHWAY TO HELL` / 各模式与面板标签）是
**手绘 `DefineShape` 矢量图形**，不是文本，字体替换碰不到它们 —— 这就是
「换了字体但主菜单没变」的原因。

## 定位

主时间轴第 6265 帧 / `Menu`：

| 实例名 | 按钮 id | 常态 shape | 悬停 shape | 原文 |
|---|---|---|---|---|
| `StoryMode` | 4310 | 4307 | 4308 | THE GREAT ESCAPE |
| `StoryHardcoreMode` | 4306 | 4303 | 4304 | HIGHWAY TO HELL |
| `MilitaryMode` | 4298 | 4295 | 4296 | MILITARY MODE |
| `TimeMode` | 4302 | 4299 | 4300 | TIME MODE |
| `Options` | 4314 | 4311 | 4312 | OPTIONS |
| `Achievements` | 4318 | 4315 | 4316 | ACHIEVEMENTS |
| `HighScores` | 4322 | 4319 | 4320 | HIGH SCORES |

`pipeline/ui/menu_labels.py` 把这些标签用**透视投影后**的中文字体轮廓生成矢量 SVG，
再让 FFDec 替换对应 shape。

## 逐标签透视

- 原版按钮文字是**手绘透视字**（像铺在路面上由近及远：上边窄、笔画后仰），不是简单斜体；
- **每个标签的透视都不一样**：越靠下（越近）左边越接近竖直（OPTIONS `L 0.00`、
  HIGH SCORES `0.01`），越靠上（越远）内收越强（POLICE STATE `0.15`）。
  因此程序逐标签取透视（`LABEL_NORM`，用 Theil–Sen 对原版逐行墨迹边界做稳健拟合），
  不再共用一套平均透视。

## 局部仿射

中文字形投影时**以单个字为单位**取局部仿射（`local_affine`）：整字按自己中心处的
仿射「盖章」，而不是逐点走完整单应 —— 否则一个被拉宽的字左右两侧的局部剪切角能差
几十度，逐点投影会把整字扭歪。

## 字号与字距

中文比英文紧凑得多（5 字顶 14 个字母）：

- 字形按标签高度放大后，再**横向加宽**（上限 `MAX_H_STRETCH = 2.5` 倍自然宽）去接近按钮宽度；
- 剩下的用**有上限的字距**（`MAX_GAP_RATIO = 0.6` × 高）补足并整体居中；
- 短词会占满按钮框，且不会把两个字甩到按钮两端。

## 关键约束

- **FFDec 会把替换 SVG 的 viewport 按原始 shape 的包围盒 1:1 映射**，
  所以 SVG 的 `width/height` 必须与原始 shape 完全一致；
- 保留每个状态原本的**颜色和透明度**（Story 是红色 `#cb0000`、其余白色；
  常态白色 alpha `0.40`、红色 `0.60`，悬停 `1.0`）；
- 纯矢量，缩放不糊。

品牌字样（Newgrounds / Evil-Dog / SickDeathFiend）保持原样。

用例：

```powershell
uv run python pipeline/ui/menu_labels.py --swf in.swf --out out.swf --orig 原版.swf
```
